"""网页版机器人 —— 出站镜像

职责：
把抽屉上报的消息切片「镜像」一份到网页收件箱，让手机网页能拉到 AI 回复。

为什么单独成模块：
- 出站分流原本只服务 QQ（message_router），网页版是第二条去向；
- 把「存箱 + 语音落盘」集中在此，message_router 只需调一次，保持其精简。

去重：
- 抽屉每次上报全量切片，同一消息会被反复上报；
- 以抽屉的消息 id 作 source_id，交给 web_inbox.append_many 去重。

语音：
- AI 消息若含 {"type":"bridge-voice"} 块，合成 MP3 落到网页音频目录，
  网页拉到该消息时按 voice 字段自动播放。
- 合成只在「该消息首次入库」时做一次，避免重复上报反复合成。
"""
import os
import threading
import time

from . import web_inbox

# 后台合成占用集合：避免同一条被重复丢进线程。
_synth_inflight = set()
_synth_lock = threading.Lock()


def log(*args):
    """统一前缀打印。"""
    print("[web][mirror]", *args)


def _voice_text_of(m):
    """从消息 blocks 里取语音朗读文本（复用桥接侧同一约定）。

    识别规则以远程桥接模块的提取器为唯一来源，此处不再另存副本。
    远程桥接模块不可用时返回空串：语音是附加能力，不应影响镜像主流程。
    @param m 消息对象
    @returns 语音文本；无则空串
    """
    try:
        from remote_bridge.message_voice import extract_voice_from_blocks
        return extract_voice_from_blocks(m) or ""
    except Exception:
        return ""


def synthesize_voice(text):
    """按需把朗读文本合成为 MP3，落到网页音频目录，返回文件名。

    由网页点播时调用（在后台线程内执行），不在上报链路里跑，
    故不会阻塞服务。失败返回空串：语音是附加能力，合成不了不应影响主流程。
    @param text 待朗读文本
    @returns 音频文件名（相对音频目录）；失败空串
    """
    if not text:
        return ""
    try:
        import paths
        from remote_bridge import voice_tts
    except Exception as e:
        log("语音模块不可用：", e)
        return ""
    try:
        paths.WEB_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        fname = "out_" + str(int(time.time() * 1000)) + ".mp3"
        out_path = str(paths.WEB_AUDIO_DIR / fname)
        ok, err = voice_tts.text_to_voice(text, out_path)
        if not ok:
            log("语音合成失败：", err)
            return ""
        return fname
    except Exception as e:
        log("语音合成异常：", e)
        return ""


def _auto_synth(seq, text):
    """后台自动合成某条消息的语音，完成后回填文件名。

    在上报入库后异步触发，绝不阻塞上报请求；网页端无需任何点击，
    合成好后前端轮询即可自动接上播放。
    @param seq  消息序号
    @param text 待朗读文本
    """
    try:
        name = synthesize_voice(text)
        if name:
            web_inbox.set_voice(seq, name)
    except Exception as e:
        log("后台自动合成失败：", e)
    finally:
        with _synth_lock:
            _synth_inflight.discard(seq)


def schedule_auto_synth(added):
    """为刚入库、带朗读文本的 AI 消息启动后台自动合成。

    @param added web_inbox.append_many 返回的新增消息列表
    """
    for m in (added or []):
        seq = int(m.get("seq") or 0)
        text = str(m.get("voice_text") or "")
        if not seq or not text or m.get("voice"):
            continue
        with _synth_lock:
            if seq in _synth_inflight:
                continue
            _synth_inflight.add(seq)
        threading.Thread(target=_auto_synth, args=(seq, text), daemon=True).start()


def _extract_images(m):
    """从消息的 blocks 里提取图片并落盘，返回文件名列表。

    图片块（type=image）的 src 可能是 dataURL、http(s) 地址或 blob:。
    dataURL 与 http(s) 存到网页图片目录；blob: 后端无法访问，跳过。
    失败不抛异常：图片是附加内容，取不到不应阻断消息入库。
    @param m 消息对象
    @returns 文件名列表（相对网页图片目录）；无图返回空列表
    """
    names = []
    for b in (m.get("blocks") or []):
        if not b or b.get("type") != "image":
            continue
        src = str(b.get("src") or "")
        if not src.startswith("data:image/"):
            # http(s) 与 blob: 暂不在此处理：前者按需下载、后者后端不可达
            continue
        try:
            import screenshot_store
            saved = screenshot_store.save_web_image(src)
            if saved and saved.get("name"):
                names.append(saved["name"])
        except Exception as e:
            log("保存消息图片失败：", e)
    return names


def _import_parsers():
    """延迟导入解析器：避免模块导入期就拉起 remote_bridge 整包。

    @returns 解析函数字典；任一模块不可用时返回 None（调用方跳过镜像）
    """
    try:
        from remote_bridge.message_parse import (
            _classify, _blocks_to_text, _thinking_text_of, _parse_envelope,
        )
        from remote_bridge.message_voice import strip_voice_blocks
    except Exception as e:
        log("解析模块不可用，跳过镜像：", e)
        return None
    # 汇总为字典，供组装函数按名取用；_thinking_text_of 保持导入以维持
    # 与旧实现一致的「模块可用性判定」口径。
    return {
        "classify": _classify,
        "blocks_to_text": _blocks_to_text,
        "parse_envelope": _parse_envelope,
        "strip_voice_blocks": strip_voice_blocks,
    }


def _load_push():
    """读取推送开关：与 QQ 版同一份配置，保证两边「哪类消息推不推」一致。

    读不到时用空字典，各类默认放行（与 QQ 版 push.get(kind, True) 同义）。
    @returns 推送开关字典
    """
    try:
        from remote_bridge import bridge_store
        return bridge_store.get_config().get("push") or {}
    except Exception as e:
        log("读取推送开关失败，按全推处理：", e)
        return {}


def _compose_body(m, push, parsers):
    """组装一条消息的正文文本。

    统一交给 outbound.build_body：与 QQ 版共用同一套规则，网页版因此自动继承
    「思考内容」与「工具结果围栏」等能力；失败时退回块拼。
    @param m       消息对象
    @param push    推送开关字典
    @param parsers 解析函数字典
    @returns 正文文本
    """
    try:
        from remote_bridge.outbound import build_body
        built = build_body(m, push)
        return built.get("text") or ""
    except Exception as e:
        log("正文组装失败，退回块拼：", e)
        try:
            return str(m.get("md") or "").strip() or parsers["blocks_to_text"](m, False)
        except Exception:
            return str(m.get("md") or "").strip()


def _finalize_body(body, env, parsers):
    """对组装好的正文做后处理：信封取真实发言、剔除语音块。

    @param body    已组装的正文
    @param env     信封字典（无则 None）
    @param parsers 解析函数字典
    @returns 处理后的正文
    """
    # 外部卡片（external-call 信封）：正文应是信封里 request 承载的「真实发言」，
    # 而非整段 JSON。QQ 用户发来的消息即以信封形态上报，不取 request 会把
    # 用户的普通一句话显示成一段 JSON。
    if env:
        req = env.get("request")
        if isinstance(req, str) and req.strip():
            body = req.strip()
    # 剔除语音块：语音已由 voice 字段单独承载，正文不该再残留其 JSON 文本
    try:
        body = parsers["strip_voice_blocks"](body)
    except Exception:
        pass
    return body


def _prepare_fields(m, kind):
    """准备条目的附加字段：语音文本、图片、角色。

    @param m    消息对象
    @param kind 消息类别 user / tool / ai
    @returns (voice_text, image_value, role) 三元组
    """
    # 语音：仅 AI 消息提取「待朗读文本」，此处不合成。
    # 合成为在线网络调用（无超时），若放在上报链路里同步执行，
    # 会让每轮上报都阻塞在合成上、把服务拖垮。故只存文本，
    # 真正合成由网页点播时按需触发（见 routes/web.py 的 /api/web/voice-ensure）。
    voice_text = _voice_text_of(m) if kind == "ai" else ""
    # 图片块：消息里的 image 块（网页发图、AI 配图等）存到服务端，
    # 收件箱记文件名，前端与抽屉镜像据此用同一地址取图。
    images = _extract_images(m)
    # 单图存字符串、多图存列表；无图存空串
    image_value = images if len(images) > 1 else (images[0] if images else "")
    # 角色映射：tool 归到工具类，user/ai 原样
    role = kind if kind in ("user", "ai") else "tool"
    return voice_text, image_value, role


def _parse_env_kind(m, parsers):
    """解析消息的信封与类别，两者都容错（失败时给安全默认）。

    @param m       消息对象
    @param parsers 解析函数字典
    @returns (env, kind)：env 为信封字典或 None；kind 为 user / tool / ai
    """
    try:
        env = parsers["parse_envelope"](m)
    except Exception:
        env = None
    try:
        kind = parsers["classify"](m)
    except Exception:
        kind = "ai"
    return env, kind


def _gate(m, push, parsers):
    """判断一条消息是否应入箱；应跳过时返回 None。

    跳过条件：无 id / 已入库 / 网页自发信封 / 推送开关关闭。
    @param m       消息对象
    @param push    推送开关字典
    @param parsers 解析函数字典
    @returns (mid, env, kind) 三元组；应跳过时返回 None
    """
    mid = (m or {}).get("id") or ""
    if not mid:
        return None
    # 已入库的不再重复处理（含语音合成这种重活）
    if web_inbox.is_seen(mid):
        return None
    # 解析信封与类别（各自内部吞异常）
    env, kind = _parse_env_kind(m, parsers)
    # 网页自发消息：网页发消息时已按纯文本记过一次（见 routes/web.py），
    # 抽屉上报回来的却是 external-call 信封原文（source=web）。若在此再镜像，
    # 就会同一句话记两条、且第二条显示为整段 JSON。故跳过网页自发的信封。
    if env and env.get("source") == "web":
        return None
    # 推送开关过滤：与 QQ 版同一套配置（push.user / tool / ai）。
    # 关掉某类推送时，网页版也一并跳过，保持两边设定一致。
    if not push.get(kind, True):
        return None
    return mid, env, kind


def _build_item(m, push, parsers):
    """把一条上报消息组装成收件箱条目；无需入箱时返回 None。

    @param m       消息对象
    @param push    推送开关字典
    @param parsers 解析函数字典
    @returns 条目字典；跳过（无 id / 已入库 / 网页自发 / 开关关闭）返回 None
    """
    # 前置判断：无 id / 已入库 / 网页自发 / 开关关闭 都跳过
    gated = _gate(m, push, parsers)
    if gated is None:
        return None
    mid, env, kind = gated
    # 正文组装 + 后处理（信封取真实发言、剔除语音块）
    body = _finalize_body(_compose_body(m, push, parsers), env, parsers)
    # 语音文本、图片、角色：一并准备好，供下方组装条目
    voice_text, image_value, role = _prepare_fields(m, kind)
    return {
        "source_id": mid,
        "role": role,
        "text": body,
        "voice": "",
        "voice_text": voice_text,
        "image": image_value,
        "kind": "",
        # key：消息在抽屉消息树里的 key（pid-id 格式），供网页版逐条
        # 核对消息块是否完整、有无缺块。缺失时为空串。
        "key": str((m or {}).get("key") or ""),
    }


def mirror_report(messages):
    """把一批上报消息镜像进网页收件箱，返回新增条数。

    入参就是 message_router 处理的那份切片；本函数自行分类与拼文本，
    不依赖 message_router 的中间结果，保持两侧解耦。
    逐条组装委托 _build_item，本函数只负责编排「准备 → 遍历 → 入库」。
    @param messages 消息对象列表
    @returns 新增入库的消息条数
    """
    if not messages:
        return 0
    # 准备阶段：解析器与推送开关，任一不可用即安全退出
    parsers = _import_parsers()
    if parsers is None:
        return 0
    push = _load_push()
    # 遍历阶段：逐条组装，跳过无需入箱的消息
    items = [it for it in (_build_item(m, push, parsers) for m in messages) if it]
    if not items:
        return 0
    # 入库阶段：批量写入，成功则触发后台语音合成
    added = web_inbox.append_many(items)
    if added:
        log("镜像入库", len(added), "条")
        # 入库后立刻在后台自动合成语音：不阻塞上报、网页无需点击即自动连播。
        schedule_auto_synth(added)
    return len(added)
