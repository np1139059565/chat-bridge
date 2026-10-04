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
import time

from . import web_inbox


def log(*args):
    """统一前缀打印。"""
    print("[web][mirror]", *args)


def _voice_text_of(m):
    """从消息 blocks 里取语音朗读文本（复用桥接侧同一约定）。

    认内容为 {"type":"bridge-voice","text":...} 的块；
    优先用远程桥接模块的提取器，取不到则就地解析，保证互不阻断。
    @returns 语音文本；无则空串
    """
    try:
        from remote_bridge.message_voice import extract_voice_from_blocks
        return extract_voice_from_blocks(m) or ""
    except Exception:
        pass
    # 兜底：就地解析代码块里的 JSON
    import json
    for b in (m.get("blocks") or []):
        if not b or b.get("type") != "code":
            continue
        src = str(b.get("code") or "").strip()
        if not src.startswith("{"):
            continue
        try:
            obj = json.loads(src)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("type") == "bridge-voice":
            return str(obj.get("text") or "").strip()
    return ""


def _synthesize_voice(text):
    """把朗读文本合成为 MP3，落到网页音频目录，返回文件名。

    失败返回空串：语音是附加能力，合成不了不应影响消息入库。
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


def mirror_report(messages):
    """把一批上报消息镜像进网页收件箱，返回新增条数。

    入参就是 message_router 处理的那份切片；本函数自行分类与拼文本，
    不依赖 message_router 的中间结果，保持两侧解耦。
    @param messages 消息对象列表
    @returns 新增入库的消息条数
    """
    if not messages:
        return 0
    # 延迟导入解析器：避免模块导入期就拉起 remote_bridge 整包
    try:
        from remote_bridge.message_parse import (
            _classify, _blocks_to_text, _thinking_text_of, _parse_envelope,
        )
        from remote_bridge.message_voice import strip_voice_blocks
    except Exception as e:
        log("解析模块不可用，跳过镜像：", e)
        return 0
    # 读取推送开关：与 QQ 版同一份配置，保证两边「哪类消息推不推」一致。
    # 读不到时用空字典，各类默认放行（与 QQ 版 push.get(kind, True) 同义）。
    try:
        from remote_bridge import bridge_store
        push = bridge_store.get_config().get("push") or {}
    except Exception as e:
        log("读取推送开关失败，按全推处理：", e)
        push = {}
    items = []
    for m in messages:
        mid = (m or {}).get("id") or ""
        if not mid:
            continue
        # 已入库的不再重复处理（含语音合成这种重活）
        if web_inbox.is_seen(mid):
            continue
        # 网页自发消息：网页发消息时已按纯文本记过一次（见 routes/web.py），
        # 抽屉上报回来的却是 external-call 信封原文（source=web）。若在此再镜像，
        # 就会同一句话记两条、且第二条显示为整段 JSON。故跳过网页自发的信封。
        try:
            env = _parse_envelope(m)
        except Exception:
            env = None
        if env and env.get("source") == "web":
            continue
        try:
            kind = _classify(m)          # user / tool / ai
        except Exception:
            kind = "ai"
        # 推送开关过滤：与 QQ 版同一套配置（push.user / tool / ai）。
        # 关掉某类推送时，网页版也一并跳过，保持两边设定一致。
        if not push.get(kind, True):
            continue
        # 正文组装统一交给 outbound.build_body：与 QQ 版共用同一套规则，
        # 网页版因此自动继承「思考内容」与「工具结果围栏」等能力。
        body = ""
        is_tool_result = False
        try:
            from remote_bridge.outbound import build_body
            built = build_body(m, push)
            body = built.get("text") or ""
            is_tool_result = bool(built.get("is_tool_result"))
        except Exception as e:
            log("正文组装失败，退回块拼：", e)
            try:
                body = str(m.get("md") or "").strip() or _blocks_to_text(m, False)
            except Exception:
                body = str(m.get("md") or "").strip()
        # 外部卡片（external-call 信封）：正文应是信封里 request 承载的「真实发言」，
        # 而非整段 JSON。QQ 用户发来的消息即以信封形态上报，不取 request 会把
        # 用户的普通一句话显示成一段 JSON。
        if env:
            req = env.get("request")
            if isinstance(req, str) and req.strip():
                body = req.strip()
        # 剔除语音块：语音已由 voice 字段单独承载，正文不该再残留其 JSON 文本
        try:
            body = strip_voice_blocks(body)
        except Exception:
            pass
        # 语音：仅 AI 消息提取并合成
        voice = ""
        if kind == "ai":
            vtext = _voice_text_of(m)
            if vtext:
                voice = _synthesize_voice(vtext)
        # 图片块：消息里的 image 块（网页发图、AI 配图等）存到服务端，
        # 收件箱记文件名，前端与抽屉镜像据此用同一地址取图。
        images = _extract_images(m)
        # 角色映射：tool 归到工具类，user/ai 原样
        role = kind if kind in ("user", "ai") else "tool"
        items.append({
            "source_id": mid,
            "role": role,
            "text": body,
            "voice": voice,
            "image": (images if len(images) > 1 else (images[0] if images else "")),
            "kind": "",
            # key：消息在抽屉消息树里的 key（pid-id 格式），供网页版逐条
            # 核对消息块是否完整、有无缺块。缺失时为空串。
            "key": str((m or {}).get("key") or ""),
        })
    if not items:
        return 0
    added = web_inbox.append_many(items)
    if added:
        log("镜像入库", len(added), "条")
    return len(added)
