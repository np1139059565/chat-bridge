"""远程桥接 —— 出向语音：从消息提取语音文本、合成并推送

从 message_router.py 抽出，使该文件保持在行数上限内。

职责：
- extract_voice_from_blocks：从消息 blocks 里取出 {"type":"bridge-voice","text":...} 的文本
- push_voice：把本地音频经被动回复窗口推到 QQ
- maybe_push_voice：语音开关开着且消息含语音块时，合成并推送

依赖单向：message_router 引用本模块，本模块不反向引用它。
next_seq（被动回复窗口的序号分配）通过延迟导入 message_router 获取，
避免导入期循环依赖。
"""
import time

from . import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][voice]", *args)


def extract_voice_from_blocks(m):
    """从消息的 blocks 里取语音朗读文本。

    与工具调用块同一机制——认代码块内容里的 JSON type 字段，不看语言名：
    找内容为 {"type":"bridge-voice","text":"..."} 的块，取其 text。
    @param m 消息对象
    @returns 语音文本；无则空串
    """
    import json
    for b in (m.get("blocks") or []):
        if not b or b.get("type") != "code":
            continue
        src = str(b.get("code") or "").strip()
        if not src or src[0] != "{":
            continue
        try:
            obj = json.loads(src)
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("type") == "bridge-voice":
            return str(obj.get("text") or "").strip()
    return ""


def push_voice(qq_client, openid, path):
    """把一段本地音频推送到 QQ（与图片推送同路，走被动回复窗口）。

    窗口关闭时静默跳过（等用户下次发消息再唤醒），与文本 / 图片一致。
    @param qq_client QQClient 实例
    @param openid 目标用户
    @param path 本地音频文件绝对路径
    @returns 是否发送成功
    """
    if not qq_client or not openid or not path:
        return False
    # 延迟导入：next_seq 由 message_router 统一维护，避免导入期循环依赖
    from .message_router import next_seq
    msg_id, seq = next_seq(openid)
    if not msg_id:
        log("窗口已关闭，暂不推送语音")
        return False
    ok, data = qq_client.send_c2c_voice(openid, path, msg_id=msg_id, msg_seq=seq)
    if not ok:
        log("推送语音失败：", data)
    return ok


def maybe_push_voice(qq_client, openid, m, text, push):
    """AI 回复若含语音朗读块且语音开关开着，则合成语音并推送。

    从消息 blocks 里认 {"type":"bridge-voice","text":...} 块并取其 text。
    @param m AI 消息对象（用于从 blocks 提取语音文本）
    @param text AI 回复的完整文本（当前未使用，保留签名兼容）
    @param push 推送开关字典
    @returns 是否真的推送了语音
    """
    # 语音识别开关未打开则不合成（与入向同一开关，语义统一为「语音功能总开关」）
    if not push.get("voice"):
        return False
    voice_text = extract_voice_from_blocks(m)
    if not voice_text:
        return False
    import os
    import paths
    from . import voice_tts
    os.makedirs(paths.VOICE_DIR, exist_ok=True)
    out_path = str(paths.VOICE_DIR / ("out_" + str(int(time.time() * 1000)) + ".mp3"))
    ok, err = voice_tts.text_to_voice(voice_text, out_path)
    if not ok:
        log("语音合成失败：", err)
        return False
    sent = push_voice(qq_client, openid, out_path)
    # 音频文件用完即删，不留垃圾（无论发送成败）
    try:
        os.remove(out_path)
    except OSError:
        pass
    return sent
