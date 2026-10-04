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
        from remote_bridge.message_parse import _classify, _blocks_to_text, _thinking_text_of
    except Exception as e:
        log("解析模块不可用，跳过镜像：", e)
        return 0
    items = []
    for m in messages:
        mid = (m or {}).get("id") or ""
        if not mid:
            continue
        # 已入库的不再重复处理（含语音合成这种重活）
        if web_inbox.is_seen(mid):
            continue
        try:
            kind = _classify(m)          # user / tool / ai
        except Exception:
            kind = "ai"
        # 正文：优先 md 原文（保 Markdown 格式），退回 blocks 拼纯文本
        raw_md = str(m.get("md") or "").strip()
        try:
            body = raw_md or _blocks_to_text(m, False)
        except Exception:
            body = raw_md
        # 工具结果（bridge-chat-res）：本体是一段 JSON，裸文本既不渲染为代码块、
        # 又会因无空格断行而撑破气泡。此处包上 json 围栏，交前端按代码块渲染。
        try:
            from remote_bridge.message_parse import _tool_result_of
            tr = _tool_result_of(m)
        except Exception:
            tr = None
        if tr is not None:
            import json as _json
            body = "```json\n" + _json.dumps(tr, ensure_ascii=False, indent=2) + "\n```"
        # 语音：仅 AI 消息提取并合成
        voice = ""
        if kind == "ai":
            vtext = _voice_text_of(m)
            if vtext:
                voice = _synthesize_voice(vtext)
        # 角色映射：tool 归到工具类，user/ai 原样
        role = kind if kind in ("user", "ai") else "tool"
        items.append({
            "source_id": mid,
            "role": role,
            "text": body,
            "voice": voice,
            "kind": "",
        })
    if not items:
        return 0
    added = web_inbox.append_many(items)
    if added:
        log("镜像入库", len(added), "条")
    return len(added)
