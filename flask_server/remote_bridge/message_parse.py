"""远程桥接 —— 消息解析与块文本组装

从 message_router.py 抽出，使该文件保持在行数上限内。

职责：
  1. 解析消息里的外部调用信封（external-call，含嵌套穿透）；
  2. 识别工具结果（bridge-chat-res）与 QQ 来源标记；
  3. 给消息分类（user / tool / ai）；
  4. 把内容块拼成纯文本（思考 / 代码 / 段落 / 列表 / 表格等）。

调用方是 message_router.py；本模块不反向引用它，依赖单向。
"""


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


def _tool_result_of(m):
    """判断一条消息是否为工具结果回传（bridge-chat-res）。

    工具结果经「回传网页 AI → 成为一条消息 → 镜像抓取」到达这里。
    它是 JSON 文本，不加处理会以纯文本推送、代码块不渲染，
    故此处识别出来，交由推送环节按 Markdown 代码块发送。
    @param m 消息对象
    @returns 解析出的结果对象；不是工具结果返回 None
    """
    for b in (m.get("blocks") or []):
        obj = _load_json_block(b)
        if obj and obj.get("type") == "bridge-chat-res":
            return obj
    return None


def _classify(m):
    """给一条消息定类：user / tool / ai。

    优先读抽屉传来的来源标记 source（user / assistant / tool）——它是
    「第三方角色」的落点，把工具结果与真人发言彻底分开，无需扫字符串反推。
    缺字段时回退旧逻辑：assistant 算 AI；user 角色里带 external-call 信封的
    算工具消息；其余算用户消息。
    """
    src = m.get("source") or ""
    if src == "assistant":
        return "ai"
    if src == "tool":
        return "tool"
    if src == "user":
        return "user"
    # 回退：旧数据无 source 字段，按内容判定
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
    """代码块：工具调用摘出工具名与参数，语音块渲染成 voice 围栏，其余原样包裹。"""
    import json
    code = str(b.get("code") or "")
    try:
        obj = json.loads(code.strip())
        if obj.get("type") == "bridge-chat-call":
            return "[工具调用] %s 参数=%s" % (
                obj.get("tool", ""), json.dumps(obj.get("parameters") or {}, ensure_ascii=False))
        if obj.get("type") == "bridge-voice":
            return "```voice\n" + str(obj.get("text") or "").strip() + "\n```"
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


def _thinking_text_of(m):
    """单独提取一条消息里的思考文本（拼接全部 thinking 块）。

    为什么要单独取：AI 回复的 md 字段是「复制按钮」采集的 Markdown 原文，
    复制内容不含思考过程；推送若只用 md，思考就被整段绕过。故思考不能
    依附 md，需从 blocks 里独立提取，再由推送环节自行拼装。
    @param m 消息对象
    @returns 思考文本；没有思考块返回空串
    """
    parts = []
    for b in (m.get("blocks") or []):
        if b and b.get("type") == "thinking":
            t = str(b.get("text") or "").strip()
            if t:
                parts.append(t)
    return "\n\n".join(parts)


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
