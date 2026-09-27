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


def _merge_nested_envelope(obj):
    """把嵌套信封的内层字段并入外层。

    obj 的 request 字段若是字符串且本身又是一段 JSON，说明这是两层结构；
    内层补 source / openid 等字段，外层字段优先（update 顺序即优先级）。
    穿透失败时原样返回 obj。
    """
    import json
    req = obj.get("request")
    if not (isinstance(req, str) and req.strip().startswith("{")):
        return obj
    try:
        inner = json.loads(req)
    except Exception:
        return obj
    if not isinstance(inner, dict):
        return obj
    merged = dict(inner)
    merged.update(obj)
    merged["request"] = inner.get("request", req)
    return merged


def _block_text_of(b):
    """取块的文本内容：优先 code 字段，其次 text 字段，均无则返回空串。"""
    b = b or {}
    src = b.get("code")
    if not src:
        src = b.get("text")
    return str(src or "").strip()


def _load_json_block(b):
    """取块的文本内容并尝试解析为 JSON 对象；不是 JSON 对象返回 None。"""
    import json
    src = _block_text_of(b)
    if not src or src[0] != "{":
        return None
    try:
        obj = json.loads(src)
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _parse_block_envelope(b):
    """尝试把单个消息块解析为外部调用信封；不是信封返回 None。"""
    obj = _load_json_block(b)
    if obj is None or obj.get("type") != "external-call":
        return None
    return _merge_nested_envelope(obj)


def _parse_envelope(m):
    """解析一条消息里的外部调用信封，穿透嵌套。

    为什么要穿透：抽屉的 sendExternalCard 会把卡片 content 放进信封的
    request 字段再发出，于是网页 AI 收到的结构是两层的——
    顶层 {type, nonce, request, page_url}，而我们的来源标记藏在 request
    这个字符串里。只看顶层会漏判。

    @param m 消息对象
    @returns 解析出的信封 dict；解析不出返回 None
    """
    for b in (m.get("blocks") or []):
        obj = _parse_block_envelope(b)
        if obj is not None:
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


# ---------- 单个消息块 → 文本 ----------
# 每种块类型一个处理函数，签名统一为 (block, push_thinking) → 文本片段；
# 返回空串表示该块不产出内容（由调用方过滤）。

def _block_thinking(b, push_thinking):
    """思考块：默认不推，push_thinking 为真时加 [思考] 前缀。"""
    if not push_thinking:
        return ""
    return "[思考] " + str(b.get("text") or "")


def _block_code(b, push_thinking):
    """代码块：工具调用只摘出工具名与参数，其余原样包裹在围栏里。"""
    import json
    code = str(b.get("code") or "")
    try:
        obj = json.loads(code.strip())
        if obj.get("type") == "bridge-chat-call":
            return "[工具调用] %s 参数=%s" % (
                obj.get("tool", ""), json.dumps(obj.get("parameters") or {}, ensure_ascii=False))
    except Exception:
        pass
    return "```\n" + code + "\n```"


def _block_text(b, push_thinking):
    """纯文本块：段落 / 标题 / 引用共用同一取文本方式。"""
    return str(b.get("text") or "")


def _block_list(b, push_thinking):
    """列表块：每个元素前置「- 」并换行拼接。"""
    items = b.get("items") or []
    return "\n".join("- " + str(x) for x in items)


def _block_table(b, push_thinking):
    """表格块：单元格以「 | 」相连，逐行换行拼接。"""
    rows = b.get("rows") or []
    return "\n".join(" | ".join(str(c) for c in row) for row in rows)


# 块类型 → 处理函数。新增块类型时在此登记即可，无需改动主流程。
# 未登记的类型不产出文本（与旧实现的「无匹配分支则不 append」语义一致）。
_BLOCK_HANDLERS = {
    "thinking": _block_thinking,
    "code": _block_code,
    "paragraph": _block_text,
    "heading": _block_text,
    "quote": _block_text,
    "list": _block_list,
    "table": _block_table,
}


def _blocks_to_text(m, push_thinking):
    """把一条消息的块合并成一段文本。

    粒度规则：
    - 思考过程：默认不推，push_thinking 为真时推
    - 正文（段落 / 标题 / 列表 / 引用 / 表格）：推
    - 代码块（含工具调用）：推；工具调用只推工具名与参数

    各类块的具体取法见 _BLOCK_HANDLERS 中的处理函数。
    """
    parts = []
    for b in (m.get("blocks") or []):
        if not b:
            continue
        fn = _BLOCK_HANDLERS.get(b.get("type"))
        if not fn:
            continue
        text = fn(b, push_thinking)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


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


def _unpushed_messages(messages, pushed):
    """从上报的全量消息里筛出尚未推送过的（有 id 且不在已推送集合中）。"""
    out = []
    for m in messages:
        mid = m.get("id") or ""
        if not mid or mid in pushed:
            continue
        out.append(m)
    return out


def _should_push(m, push):
    """判断一条消息是否应当推送：类型开关打开，且不是 QQ 自己发来的。"""
    kind = _classify(m)
    # 推送开关：三类（user / tool / ai）各自控制
    if not push.get(kind, True):
        return False
    # 去重：QQ 自己发来的消息不回推，避免把用户刚说的话复读回去
    return not _has_qq_source(m)


def _push_one(qq_client, openid, m, push):
    """推送一条消息到 QQ。成功返回 True，不满足推送条件或内容为空返回 False。"""
    if not _should_push(m, push):
        return False
    # 优先用 AI 回复的 Markdown 原文（由页面复制按钮采集而来），保格式；
    # 没有（未采集 / 非 AI 消息 / 采集失败）才退回 blocks 拼的纯文本。
    text = str(m.get("md") or "").strip()
    if not text:
        text = _blocks_to_text(m, push.get("thinking", False))
    if not text:
        return False
    kind = _classify(m)
    body = "%s\n%s" % (PREFIX.get(kind, kind), text)
    # seq 由 push_text 内部统一分配，不能在此自行编号：
    # 各轮上报都从 1 重数会导致 (msg_id, msg_seq) 重复、消息被 QQ 丢弃
    return push_text(qq_client, openid, body)


def _resolve_openid(payload):
    """确定推送目标 openid：优先用上报值，回退到「最近发消息的人」。"""
    return payload.get("openid") or _last_openid or ""


def _message_ids(messages):
    """取消息列表里全部有 id 的项，用于标记已推送。"""
    return [m.get("id") for m in messages if m.get("id")]


def handle_report(qq_client, payload):
    """处理抽屉上报：diff 出新增消息并推送。

    @param qq_client QQClient 实例
    @param payload   上报体：{ conversationId, messages:[{id, role, blocks}], openid }
    @returns 本次推送的消息条数
    """
    if not qq_client:
        return 0
    conv_id = payload.get("conversationId") or "__default__"
    openid = _resolve_openid(payload)
    messages = payload.get("messages") or []
    if not openid or not messages:
        return 0

    push = bridge_store.get_config().get("push") or {}
    newly = _unpushed_messages(messages, bridge_store.get_pushed_set(conv_id))
    sent = sum(1 for m in newly if _push_one(qq_client, openid, m, push))

    # 无论是否推送成功，都把本轮全部消息 id 记为已见，避免重复处理
    bridge_store.mark_pushed(conv_id, _message_ids(messages))
    return sent
