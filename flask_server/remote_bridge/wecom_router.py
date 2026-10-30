"""远程桥接 —— 企业微信推送路由

职责：
1. 处理抽屉上报，把新增消息推回企业微信
2. **发送图片与文件**（这是换用企业微信的核心理由）
3. 持久化 chatid，支持主动推送

与微信 ClawBot 推送的差异：
  ClawBot —— 配额紧张（每条用户消息约 10 条），必须整批合并；
             且图片发送未实现，截图只能回路径。
  企业微信 —— 主动推送无配额压力，可逐条发送；
             图片与文件都能真正发出去。

  但合并仍有价值：一轮对话里用户消息 + AI 回复 + 工具调用，
  逐条推会在手机上刷出很多条。故默认仍合并文本，
  但图片单独发（合并进文本就看不到图了）。
"""
import json
import os
import threading
import time

from . import bridge_store, bridge_log
from .message_parse import _classify


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][wecom]", *args)


# 会话键后缀：与 QQ / 微信的已推集合隔离，避免互相压制
CONV_SUFFIX = "@wecom"
# 单条消息最多发送的字符数
MAX_TEXT_CHARS = 3500
# 合并多条消息时的分隔线
SEP = "\n\n———\n\n"
# 各类消息的展示前缀
PREFIX = {"user": "👤 用户", "tool": "🛠 工具", "ai": "🤖 AI"}

# 推送串行锁：同一会话的「读已推集合 → 发送 → 写回」必须整体串行
_lock = threading.RLock()

# 最近活跃的会话：{chatid: {chat_type, user, ts}}，供主动推送定位
_chats = {}
# 待回复的请求 id：{chatid: req_id}。只存内存——它绑定那一条消息，
# 重启后即失效，落盘会在下次推送时用到过期 id 而被服务端拒绝。
_last_req_id = {}


def note_chat(chatid, chat_type=1, user="", req_id=""):
    """记录一个活跃会话，并持久化。

    企业微信的主动推送依赖 chatid；只存内存的话服务重启后就推不出去了。
    req_id 也要记：推送时必须用它走 respond，客户端才停止转圈。
    只存内存、不落盘——它绑定的是那一条消息，重启后即失效，
    落盘反而会在下次推送时用到过期的 id。

    @param chatid    会话 id
    @param chat_type 1 单聊 / 2 群聊
    @param user      发送者
    @param req_id    本条消息的请求 id
    """
    if not chatid:
        return
    with _lock:
        _chats[chatid] = {"chat_type": int(chat_type or 1),
                          "user": user or "", "ts": int(time.time())}
        if req_id:
            _last_req_id[chatid] = req_id
        snapshot = {k: dict(v) for k, v in _chats.items()}
    try:
        bridge_store.save_wecom_chats(snapshot)
    except Exception as e:
        log("持久化会话失败（不影响本次推送）：", e)


def take_req_id(chatid):
    """取出并消费某会话待回复的 req_id。

    取完即清：一个 req_id 只能用于回复一条消息，重复使用会被服务端拒绝。

    @param chatid 会话 id
    @returns 请求 id；无则空串
    """
    with _lock:
        return _last_req_id.pop(chatid, "")


def _load_chats():
    """从磁盘恢复会话表（惰性，避免启动期读盘依赖）。

    @returns 会话表字典
    """
    global _chats
    with _lock:
        if _chats:
            return dict(_chats)
    try:
        data = bridge_store.load_wecom_chats() or {}
    except Exception as e:
        log("恢复会话失败：", e)
        data = {}
    with _lock:
        _chats.update(data)
        return dict(_chats)


def last_chat():
    """取最近活跃的会话：优先用持久化表，其次回退到最近用户。

    @returns (chatid, chat_type)；无则 ("", 1)
    """
    chats = _load_chats()
    if chats:
        # 按时间戳取最新
        cid = max(chats.items(), key=lambda kv: kv[1].get("ts", 0))[0]
        return cid, int(chats[cid].get("chat_type", 1))
    uid = bridge_store.load_last_wecom_user() or ""
    return uid, 1


def _is_from_wecom(m):
    """判断消息是否来自企业微信（本层投出去的外部卡片）。

    @param m 消息对象
    @returns 来自企业微信返回 True
    """
    from .message_parse import _parse_envelope
    obj = _parse_envelope(m)
    return bool(obj and obj.get("source") == "wecom")


def _is_pure_tool_call(m):
    """判断是否只含工具调用、没有可读正文。

    内部工作过程对用户是噪音，不推。但带正文的消息照常推。
    @param m 消息对象
    @returns 纯工具调用返回 True
    """
    from .message_parse import _block_text_of, _load_json_block
    has_tool = False
    for b in (m.get("blocks") or []):
        if not b:
            continue
        btype = b.get("type")
        if btype == "thinking":
            continue
        if btype == "code":
            obj = _load_json_block(b)
            if obj and obj.get("type") == "bridge-chat-call":
                has_tool = True
                continue
        if _block_text_of(b).strip():
            return False
    return has_tool


def _should_push(m, push):
    """判断一条消息是否应当推送到企业微信。"""
    kind = _classify(m)
    if not push.get(kind, True):
        return False
    if _is_from_wecom(m):
        return False
    if _is_pure_tool_call(m):
        return False
    return True


def _extract_text(m, push):
    """提取给企业微信看的正文：保留自然语言与普通代码，剔除工具调用。

    @param m    消息对象
    @param push 推送开关
    @returns 正文文本；无可用内容返回空串
    """
    from .message_parse import _BLOCK_HANDLERS, _load_json_block
    parts = []
    for b in (m.get("blocks") or []):
        if not b:
            continue
        btype = b.get("type")
        if btype == "code":
            obj = _load_json_block(b)
            if obj and obj.get("type") in ("bridge-chat-call", "bridge-chat-res", "bridge-voice"):
                continue
            code = str(b.get("code") or "").strip()
            if code:
                parts.append("```\n" + code + "\n```")
            continue
        fn = _BLOCK_HANDLERS.get(btype)
        if not fn:
            continue
        text = fn(b, bool(push.get("thinking")))
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _body_of(m, push):
    """取一条消息要推送的正文，带类型前缀。"""
    if not _should_push(m, push):
        return ""
    text = _extract_text(m, push)
    if not text:
        return ""
    kind = _classify(m)
    return "%s\n%s" % (PREFIX.get(kind, kind), text)


def _truncate(text):
    """按上限截断文本，保留首尾。"""
    if len(text) <= MAX_TEXT_CHARS:
        return text
    head = MAX_TEXT_CHARS * 2 // 3
    tail = MAX_TEXT_CHARS - head - 20
    return text[:head] + "\n\n…（中间省略）…\n\n" + text[-tail:]


def _collect_images(m):
    """取出消息里的图片块（dataURL 或 http 地址）。

    这是企业微信通道的核心能力：图片能真正发出去，不再只回路径。
    @param m 消息对象
    @returns 本地路径列表
    """
    out = []
    for b in (m.get("blocks") or []):
        if not b or b.get("type") != "image":
            continue
        src = str(b.get("src") or "")
        if not src:
            continue
        path = _materialize_image(src)
        if path:
            out.append(path)
    return out


def _materialize_image(src):
    """把图片地址落成本地文件，返回路径；失败返回空串。

    @param src dataURL 或 http(s) 地址
    @returns 本地路径
    """
    import urllib.request
    import uuid
    import paths
    try:
        os.makedirs(str(paths.WECOM_MEDIA_DIR), exist_ok=True)
    except OSError:
        return ""
    name = "out_" + uuid.uuid4().hex[:12]
    if src.startswith("data:image/"):
        try:
            head, _, b64part = src.partition(",")
            ext = ".png"
            if "jpeg" in head or "jpg" in head:
                ext = ".jpg"
            elif "gif" in head:
                ext = ".gif"
            elif "webp" in head:
                ext = ".webp"
            import base64 as _b64
            data = _b64.b64decode(b64part)
            path = str(paths.WECOM_MEDIA_DIR / (name + ext))
            with open(path, "wb") as f:
                f.write(data)
            return path
        except Exception as e:
            log("dataURL 落盘失败：", e)
            return ""
    if src.startswith(("http://", "https://")):
        try:
            ext = ".png"
            low = src.lower().split("?")[0]
            for e in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
                if low.endswith(e):
                    ext = e
                    break
            path = str(paths.WECOM_MEDIA_DIR / (name + ext))
            with urllib.request.urlopen(src, timeout=30) as r, open(path, "wb") as f:
                f.write(r.read())
            return path
        except Exception as e:
            log("图片下载失败：", e)
            return ""
    return ""


def handle_report(client, payload):
    """处理抽屉上报：文本合并成一条，图片逐张单独发送。

    为什么文本合并、图片分开：
      合并能避免手机被大量短消息刷屏；
      但图片若塞进文本就丢失了图片形态，必须单独发。

    @param client  WecomClient 实例
    @param payload 上报体
    @returns 发送的消息条数
    """
    if not client:
        return 0
    conv_id = (payload.get("conversationId") or "__default__") + CONV_SUFFIX
    chatid, chat_type = _resolve_target(payload)
    messages = payload.get("messages") or []
    if not chatid or not messages:
        return 0
    push = bridge_store.get_config().get("push") or {}
    with _lock:
        fresh = _collect_fresh(conv_id, messages)
        if not fresh:
            return 0
        bodies = []
        images = []
        for m in fresh:
            b = _body_of(m, push)
            if b:
                bodies.append(b)
            images.extend(_collect_images(m))
        if not bodies and not images:
            _mark_all(conv_id, fresh)
            return 0
        # 取本条消息的 req_id：有它才能走「回复」，客户端才会停止转圈。
        # 取完即清，一个 id 只用于回复一条消息。
        req_id = take_req_id(chatid)
        sent = 0
        if bodies:
            text = _truncate(SEP.join(bodies))
            if req_id:
                ok, data = client.respond_to(req_id, chatid, text, chat_type)
                # 回复已消费掉这个 req_id，后续图片只能用主动推送
                req_id = ""
                # 单独记一条：区分「走回复」与「走主动推送」，排障时一眼可辨
                log("已发送回复 %d 条消息，长度 %d，ok=%s" % (len(bodies), len(text), ok))
            else:
                ok, data = client.send_markdown(chatid, text, chat_type)
                log("已发送推送 %d 条消息，长度 %d，ok=%s（无 req_id）"
                    % (len(bodies), len(text), ok))
            if ok:
                sent += 1
            else:
                log("文本发送失败（下轮重试）：", str(data)[:200])
                return sent
        for path in images:
            if req_id:
                # 带 req_id 走回复通道：msg_item 直传 base64，无需素材上传
                ok, data = client.respond_image(req_id, chatid, path, chat_type)
                req_id = ""
            else:
                # 无 req_id 时主动推送发不了图（官方限制），明确记日志而非假装成功
                log("图片跳过：无 req_id，主动推送不支持图片")
                continue
            if ok:
                sent += 1
                log("已发送图片：", os.path.basename(path))
            else:
                log("图片发送失败：", str(data)[:200])
        _mark_all(conv_id, fresh)
        return sent


def _resolve_target(payload):
    """确定推送目标：优先上报体里的企业微信会话，回退到最近活跃会话。

    @param payload 上报体
    @returns (chatid, chat_type)
    """
    cid = payload.get("wecom_chatid") or ""
    if cid:
        ct = payload.get("wecom_chat_type") or 1
        return cid, int(ct)
    return last_chat()


def _collect_fresh(conv_id, messages):
    """筛出尚未推送过的消息。"""
    pushed = bridge_store.get_pushed_set(conv_id)
    return [m for m in messages if (m.get("id") or "") and m.get("id") not in pushed]


def _mark_all(conv_id, fresh):
    """把一批消息记为已推送。"""
    bridge_store.mark_pushed(conv_id, [m.get("id") for m in fresh])
