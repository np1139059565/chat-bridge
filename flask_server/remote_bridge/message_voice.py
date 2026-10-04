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


def _find_voice_json_in_text(text):
    """在纯文本里查找「裸 JSON」形态的语音块，返回朗读文本；无则空串。

    容错背景：语音块本应是带围栏的代码块，但生成侧可能漂移成裸 JSON，
    此时它不落在 blocks 的 code 块里，只存在于正文文本，需在此兜底捞取。
    为避免误判（正文恰好讨论该标记），要求 JSON 对象以 {"type":"bridge-voice"
    起头、大括号配平，且解析出的 type 必须确为 bridge-voice。
    @param text 待扫描文本
    @returns 语音文本；无则空串
    """
    import json
    if not text:
        return ""
    marker = '{"type":"bridge-voice"'
    start = text.find(marker)
    while start >= 0:
        # 从起头处做大括号配平扫描，切出完整 JSON 对象（尊重字符串与转义）
        depth = 0
        in_str = False
        esc = False
        end = -1
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > 0:
            try:
                obj = json.loads(text[start:end])
            except Exception:
                obj = None
            if isinstance(obj, dict) and obj.get("type") == "bridge-voice":
                return str(obj.get("text") or "").strip()
        # 未命中则继续找下一个可能位置
        start = text.find(marker, start + 1)
    return ""


def extract_voice_from_blocks(m):
    """从消息里取语音朗读文本（兼容两种形态）。

    与工具调用块同一机制——认 JSON 的 type 字段，不看代码块语言名：
    1) 标准形态：带围栏的代码块，内容为 {"type":"bridge-voice","text":...}；
    2) 兜底形态：语音块漂移成裸 JSON，此时从正文文本里捞取。
    @param m 消息对象
    @returns 语音文本；无则空串
    """
    import json
    # 1) 优先按「代码块」取：这是标准形态
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
    # 2) 兜底：语音块漂移成「裸 JSON」时，从正文文本里捞（md 优先，其次各文本块）
    texts = [str(m.get("md") or "")]
    for b in (m.get("blocks") or []):
        if not b:
            continue
        t = b.get("text") or b.get("content")
        if t:
            texts.append(str(t))
    for t in texts:
        got = _find_voice_json_in_text(t)
        if got:
            return got
    return ""


def strip_voice_blocks(text):
    """从正文文本里删除语音块，返回净化后的文本。

    语音块已由 voice 字段单独承载（网页播放器 / QQ 语音条），
    正文里不应再残留它的 JSON 文本（含围栏与裸两种形态），
    否则用户会在消息正文里看到一段无意义的 JSON。
    @param text 原始正文（Markdown 原文或块拼文本）
    @returns 删除语音块后的正文
    """
    if not text:
        return ""
    import re
    out = str(text)
    # 1) 带围栏的代码块：块内容含 bridge-voice 类型的 JSON 则整块删除
    def _drop_fenced(mo):
        inner = mo.group(1) or ""
        if re.search(r'"type"\s*:\s*"bridge-voice"', inner):
            return ""
        return mo.group(0)
    out = re.sub(r"```[^\n]*\n([\s\S]*?)```", _drop_fenced, out)
    # 2) 裸 JSON：以 {"type":"bridge-voice" 起头、大括号配平，整段删除
    marker = '{"type":"bridge-voice"'
    i = out.find(marker)
    while i >= 0:
        depth = 0
        in_str = False
        esc = False
        end = -1
        for j in range(i, len(out)):
            ch = out[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        if end > 0:
            out = out[:i] + out[end:]
        else:
            break
        i = out.find(marker)
    return out.strip()


# 合成文件名序号：同一毫秒内多条也不会撞名。
_synth_seq = [0]


def synthesize_voice(m):
    """从消息提取语音文本并合成为 MP3，返回本地路径；无语音或失败返回空串。

    只做合成、不推送：调用方在「锁外」预合成，再把音频与正文按序推送。
    合成是网络调用，绝不能在 _push_lock 内执行（否则在线服务一卡，
    锁被占死、线程堆满、服务器拒绝连接，必须重启才恢复）。
    @param m 消息对象
    @returns 音频文件绝对路径；无语音/失败空串
    """
    if not m:
        return ""
    voice_text = extract_voice_from_blocks(m)
    if not voice_text:
        return ""
    import os
    import paths
    from . import voice_tts
    os.makedirs(paths.VOICE_DIR, exist_ok=True)
    _synth_seq[0] += 1
    name = "out_%d_%d.mp3" % (int(time.time() * 1000), _synth_seq[0])
    out_path = str(paths.VOICE_DIR / name)
    ok, err = voice_tts.text_to_voice(voice_text, out_path)
    if not ok:
        log("语音合成失败：", err)
        return ""
    return out_path


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
