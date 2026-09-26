"""远程桥接 —— 消息分流与推送

职责：
1. 处理来自抽屉的上报：拿全量消息切片与「已推送集合」比对，取差集
2. 按三类（用户 / 工具 / AI）给消息打标签
3. 过滤 QQ 来源，避免把用户自己发的话复读回去
4. 按推送开关与粒度规则，组装文本并通过被动回复窗口发到 QQ

消息 id 与消息树的口径一致：直接复用抽屉传来的消息 id（内容指纹）。
"""
import threading
import time

from . import bridge_store

# 被动回复窗口时长（秒）：官方为 60 分钟
WINDOW_SECONDS = 60 * 60

# 三类消息的展示前缀
PREFIX = {
    "user": "👤 用户",
    "tool": "🛠 工具",
    "ai": "🤖 AI",
}

_lock = threading.Lock()

# 当前活跃的被动回复窗口：{ openid: {"msg_id": ..., "expire": 时间戳} }
_windows = {}

# 最近一个发来消息的 openid。
# 抽屉上报时并不知道 openid（那是 QQ 侧的概念），因此回退用它——
# 单用户场景下，「最近跟我说话的人」就是推送目标。
_last_openid = ""


def _parse_envelope(m):
    """解析一条消息里的外部调用信封，穿透嵌套。

    为什么要穿透：抽屉的 sendExternalCard 会把卡片 content 放进信封的
    request 字段再发出，于是网页 AI 收到的结构是两层的——
    顶层 {type, nonce, request, page_url}，而我们的来源标记藏在 request
    这个字符串里。只看顶层会漏判。

    @param m 消息对象
    @returns 解析出的信封 dict；解析不出返回 None
    """
    import json
    for b in (m.get("blocks") or []):
        src = str((b or {}).get("code") or (b or {}).get("text") or "").strip()
        if not src or src[0] != "{":
            continue
        try:
            obj = json.loads(src)
        except Exception:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "external-call":
            continue
        # 内层：request 是字符串且本身又是一个 JSON，穿透解析
        req = obj.get("request")
        if isinstance(req, str) and req.strip().startswith("{"):
            try:
                inner = json.loads(req)
                if isinstance(inner, dict):
                    # 合并：外层字段优先，内层补充 source / openid 等
                    merged = dict(inner)
                    merged.update(obj)
                    merged["request"] = inner.get("request", req)
                    return merged
            except Exception:
                pass
        return obj
    return None


def _has_qq_source(m):
    """判断一条消息是否来自 QQ（即由本桥接层投递的外部卡片）。

    QQ 发来的消息会以 external-call 信封落在消息树里，来源标记 source:'qq'。
    信封可能是嵌套结构，故用 _parse_envelope 穿透解析。
    """
    obj = _parse_envelope(m)
    return bool(obj and obj.get("source") == "qq")


def _classify(m):
    """给一条消息定类：user / tool / ai。

    assistant 一律算 AI；user 角色里凡是 external-call 信封（不论来自 QQ
    还是调试扩展）都算工具消息；其余算用户消息。
    """
    if m.get("role") == "assistant":
        return "ai"
    if _parse_envelope(m):
        return "tool"
    return "user"


def _blocks_to_text(m, push_thinking):
    """把一条消息的块合并成一段文本。

    粒度规则：
    - 思考过程：默认不推，push_thinking 为真时推
    - 正文（段落 / 标题 / 列表 / 引用 / 表格）：推
    - 代码块（含工具调用）：推；工具调用只推工具名与参数
    """
    parts = []
    for b in (m.get("blocks") or []):
        if not b:
            continue
        t = b.get("type")
        if t == "thinking":
            if push_thinking:
                parts.append("[思考] " + str(b.get("text") or ""))
        elif t == "code":
            code = str(b.get("code") or "")
            # 工具调用块：只摘出工具名与参数，不推完整 JSON
            try:
                import json
                obj = json.loads(code.strip())
                if obj.get("type") == "bridge-chat-call":
                    parts.append("[工具调用] %s 参数=%s" % (
                        obj.get("tool", ""), json.dumps(obj.get("parameters") or {}, ensure_ascii=False)))
                    continue
            except Exception:
                pass
            parts.append("```\n" + code + "\n```")
        elif t in ("paragraph", "heading", "quote"):
            parts.append(str(b.get("text") or ""))
        elif t == "list":
            items = b.get("items") or []
            parts.append("\n".join("- " + str(x) for x in items))
        elif t == "table":
            rows = b.get("rows") or []
            parts.append("\n".join(" | ".join(str(c) for c in row) for row in rows))
    return "\n".join(p for p in parts if p).strip()


def _remember_window(openid, msg_id):
    """记录 / 刷新某用户的被动回复窗口。

    seq 绑定在 msg_id 上：同一 msg_id 内必须唯一且递增，
    换新 msg_id（用户又发了消息）时归零重新计数。
    """
    global _last_openid
    with _lock:
        _last_openid = openid
        old = _windows.get(openid)
        # 同一 msg_id 保留既有计数继续递增；换了 msg_id 则从 0 重新开始
        seq = 0
        if old and old.get("msg_id") == msg_id:
            seq = old.get("seq", 0)
        _windows[openid] = {
            "msg_id": msg_id,
            "expire": time.time() + WINDOW_SECONDS,
            "seq": seq,
        }


def get_window(openid):
    """取某用户当前的窗口信息；无或已过期返回 None。"""
    with _lock:
        w = _windows.get(openid)
        if not w:
            return None
        if time.time() >= w["expire"]:
            return None
        return dict(w)


def next_seq(openid):
    """取当前窗口下一个可用的 msg_seq，并自增。

    QQ 规定 msg_seq 在同一 msg_id 内必须唯一：重复的 (msg_id, msg_seq)
    会被判为「消息被去重」（错误码 40054005）而丢弃。
    因此所有发送路径都必须共用这一个计数器，不能各自从 1 重数。
    返回 (msg_id, seq)；窗口不存在时返回 (None, 0)。
    """
    with _lock:
        w = _windows.get(openid)
        if not w or time.time() >= w["expire"]:
            return None, 0
        w["seq"] = w.get("seq", 0) + 1
        return w["msg_id"], w["seq"]


def note_incoming(openid, msg_id):
    """收到用户新消息时调用：刷新窗口（用户发消息即续期）。"""
    _remember_window(openid, msg_id)


def push_text(qq_client, openid, text):
    """把一段文本推送到 QQ。使用当前窗口的最新 msg_id 作被动回复。

    msg_seq 由 next_seq 统一分配：同一 msg_id 内唯一递增，
    避免 (msg_id, msg_seq) 重复导致消息被 QQ 判重丢弃。
    """
    msg_id, seq = next_seq(openid)
    if not msg_id:
        # 窗口关闭：无处可推，静默丢弃（设计上等待用户下次发消息唤醒）
        print("[bridge][router] 窗口已关闭，暂不推送")
        return False
    ok, data = qq_client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq)
    if not ok:
        print("[bridge][router] 推送失败：", data)
    return ok


def handle_report(qq_client, payload):
    """处理抽屉上报：diff 出新增消息并推送。

    @param qq_client QQClient 实例
    @param payload   上报体：{ conversationId, messages:[{id, role, blocks}], openid }
    @returns 本次推送的消息条数
    """
    if not qq_client:
        return 0
    conv_id = payload.get("conversationId") or "__default__"
    # openid 优先用上报值；抽屉不知道它，回退到「最近发消息的人」
    openid = payload.get("openid") or _last_openid or ""
    messages = payload.get("messages") or []
    if not openid or not messages:
        return 0

    cfg = bridge_store.get_config()
    push = cfg.get("push") or {}
    pushed = bridge_store.get_pushed_set(conv_id)

    sent = 0
    newly = []
    for m in messages:
        mid = m.get("id") or ""
        if not mid or mid in pushed:
            continue
        newly.append(m)

    for m in newly:
        kind = _classify(m)
        # 推送开关：三类各自控制
        if not push.get(kind, True):
            continue
        # 去重：QQ 自己发来的消息不回推
        if _has_qq_source(m):
            continue
        text = _blocks_to_text(m, push.get("thinking", False))
        if not text:
            continue
        body = "%s\n%s" % (PREFIX.get(kind, kind), text)
        # seq 由 push_text 内部统一分配，不能在此自行编号：
        # 各轮上报都从 1 重数会导致 (msg_id, msg_seq) 重复、消息被 QQ 丢弃
        if push_text(qq_client, openid, body):
            sent += 1

    # 无论是否推送成功，都把本轮全部消息 id 记为已见，避免重复处理
    all_ids = [m.get("id") for m in messages if m.get("id")]
    bridge_store.mark_pushed(conv_id, all_ids)
    return sent
