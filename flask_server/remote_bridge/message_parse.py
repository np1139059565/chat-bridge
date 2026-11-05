"""远程桥接 —— 消息解析与块文本组装

从 message_router.py 抽出，使该文件保持在行数上限内。

职责：
  1. 解析消息里的外部调用信封（external-call，含嵌套穿透）；
  2. 识别工具结果（bridge-chat-res）与 QQ 来源标记；
  3. 给消息分类（user / tool / ai）；
  4. 把内容块拼成纯文本（思考 / 代码 / 段落 / 列表 / 表格等）。

调用方是 message_router.py；本模块不反向引用它，依赖单向。

信封穿透逻辑统一走 core/envelope，与蒸馏模块共用一份实现。
"""
import envelope


def _merge_nested_envelope(obj):
    """把嵌套信封的内层字段并入外层（委托共享模块）。

    实现已上移到 core/envelope.py，与蒸馏模块共用同一份，避免两处维护。
    @param obj 外层信封字典
    @returns 合并后的字典（或原样返回）
    """
    return envelope.merge_nested_envelope(obj)


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


def _scan_json_by_type(text, want_type):
    """在纯文本里扫描第一个 type 等于 want_type 的 JSON 对象。

    容错背景（与语音提取同一根因）：带 type 的 JSON 载荷（工具调用、工具结果、
    外部信封、语音）标准形态是带围栏的代码块，但生成侧可能漂移成「裸 JSON」
    （无围栏）。裸 JSON 不落在 blocks 的 code 块里，只存在于正文文本，
    只看块字段会漏判。此函数专门兜住这种漂移。
    为避免误判（正文恰好讨论该标记），要求 JSON 以 { 起头、大括号配平，
    且解析出的 type 必须确为 want_type。
    @param text      待扫描文本
    @param want_type 目标 type 值
    @returns 匹配的 dict；无则 None
    """
    # 大括号配平扫描与「按 type 查找」统一走共享模块 json_scan，避免重复实现
    from . import json_scan
    return json_scan.find_json_by_type(text, want_type)


def _json_payload_of(m, want_type):
    """从一条消息里找 type 等于 want_type 的 JSON 载荷（兼容代码块与裸 JSON）。

    统一入口：工具结果、外部信封等所有「带 type 的 JSON 载荷」共用，
    避免各自只认代码块、漂移即失效。
    查找来源与优先级：
    1) blocks 各块的 code / text 字段（标准：带围栏代码块落在此处，整块即该 JSON）；
    2) blocks 各块文本里「嵌在更大文本中」的裸 JSON；
    3) md 字段（复制采集的 Markdown 原文，裸 JSON 常只在此处）。
    @param m         消息对象
    @param want_type 目标 type
    @returns 匹配的 dict；无则 None
    """
    # 1) 块字段精确解析：块整体就是该 JSON
    for b in (m.get("blocks") or []):
        obj = _load_json_block(b)
        if obj is not None and obj.get("type") == want_type:
            return obj
    # 2) 块文本里嵌着的裸 JSON
    for b in (m.get("blocks") or []):
        obj = _scan_json_by_type(_block_text_of(b), want_type)
        if obj is not None:
            return obj
    # 3) md 原文兜底：裸 JSON 往往只存在于 md
    return _scan_json_by_type(str(m.get("md") or ""), want_type)


def _parse_envelope(m):
    """解析一条消息里的外部调用信封，穿透嵌套。

    为什么要穿透：抽屉的 sendExternalCard 会把卡片 content 放进信封的
    request 字段再发出，于是网页 AI 收到的结构是两层的——
    顶层 {type, nonce, request, page_url}，而我们的来源标记藏在 request
    这个字符串里。只看顶层会漏判。

    兼容形态：信封可能是带围栏的代码块，也可能是漂移后的裸 JSON，
    故统一走 _json_payload_of 查找。

    @param m 消息对象
    @returns 解析出的信封 dict；解析不出返回 None
    """
    obj = _json_payload_of(m, "external-call")
    if obj is None:
        return None
    return _merge_nested_envelope(obj)


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
    兼容形态：结果 JSON 可能是带围栏的代码块，也可能是漂移后的裸 JSON
    （常见于 md 原文），故统一走 _json_payload_of 查找。
    @param m 消息对象
    @returns 解析出的结果对象；不是工具结果返回 None
    """
    return _json_payload_of(m, "bridge-chat-res")


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


def _payload_summary(obj):
    """取桥接载荷的展示摘要；不是桥接载荷返回 None。

    三类载荷在手机上的处理原则一致：只留一行摘要，细节一律不推。

      - 工具调用：只报工具名。参数是 JSON，占满一屏且无阅读价值；
      - 工具结果：只报成败。完整 result 含 nonce、本机路径、命令输出，
        既是噪音，也可能泄露本机路径；
      - 语音：照常取朗读文本。语音消息可能合成失败，正文里的文字是兜底，
        用户至少还能读到这里。

    @param obj 解析出的 JSON 对象
    @returns 摘要文本；非桥接载荷返回 None
    """
    t = obj.get("type")
    if t == "bridge-chat-call":
        return "[工具调用] " + str(obj.get("tool") or "")
    if t == "bridge-chat-res":
        mark = "成功" if obj.get("success") else "失败"
        err = obj.get("error") or ""
        return "[工具结果] " + (mark + ("：" + str(err) if err else ""))
    if t == "bridge-voice":
        return "[语音] " + str(obj.get("text") or "").strip()
    return None


def _block_code(b, push_thinking):
    """代码块：桥接载荷摘成一行摘要，其余代码原样包裹。

    摘要统一用代码块包裹：平台没有折叠语法，代码块在手机上默认收起，
    是等效的「折叠」表达，也让 AI 正文与工具痕迹在视觉上分得开。
    """
    import json
    code = str(b.get("code") or "")
    try:
        obj = json.loads(code.strip())
        # 语音文字是正文兜底内容，与工具痕迹不同：不包代码块，按普通段落呈现
        if obj.get("type") == "bridge-voice":
            return str(obj.get("text") or "").strip()
        summary = _payload_summary(obj)
        if summary is not None:
            return "```\n" + summary + "\n```" if summary else ""
    except Exception:
        pass
    return "```\n" + code + "\n```"


def _scrub_traces(text):
    """清洗正文里混入的桥接痕迹，还原成一行摘要。

    痕迹的来源是采集侧把已渲染的正文又抓了一遍，形态如
    「[工具调用] search_content 参数={...}」。它出现在正文里会
    与推送侧的摘要重复，且把一大坨参数摊在手机上。

    处理原则：工具调用只留工具名并包代码块；工具结果只留成败；
    语音文字整行丢弃（朗读文本已由语音消息单独发出）。

    @param text 原始文本
    @returns 清洗后的文本
    """
    if not any(mark in text for mark in ("[工具调用]", "[工具结果]", "[语音]")):
        return text
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("[工具调用]"):
            # 只留工具名：参数是 JSON，手机上占满一屏且无阅读价值
            name = s[len("[工具调用]"):].split("参数=")[0].strip()
            out.append("```\n[工具调用] " + name + "\n```")
        elif s.startswith("[工具结果]"):
            out.append("```\n" + s + "\n```")
        elif s.startswith("[语音]"):
            # 语音文字保留、去掉前缀：语音合成可能失败，正文里的字是兜底
            out.append(s[len("[语音]"):].strip())
        else:
            out.append(line)
    return "\n".join(out).strip()


# 质检错误码 → 给用户看的简短说明。
# 完整告警文本是写给 AI 的整改指令，含 JSON 格式要求，不适合直接推给用户。
_ERROR_BRIEF = {
    "voice_missing": "缺少语音朗读内容",
    "code_only_reply": "只有代码没有文字说明",
    "thinking_english": "思考内容以英文为主",
    "multiple_tool_calls": "一次包含多个工具调用",
}


def quality_note(m):
    """取质检标注行；无标记返回空串。

    用户要求「被质检拦截的消息也该推过去，才能知道被拦截过」。
    故此处不拦截，只在正文前加一行说明。

    本函数是这条规则的唯一来源：企微（channel/text.py）与 QQ（outbound.py）
    都调用它，保证同一条回复在两条通道上的标注文案完全一致。

    @param m 消息对象
    @returns 标注行；无需标注返回空串
    """
    q = m.get("qualityIssue")
    if not isinstance(q, dict):
        return ""
    # 只取说明的第一句：完整说明是给 AI 看的整改指令（含 JSON 格式要求），
    # 原样推给用户既长又无意义。用户只需知道「哪里不对」。
    msg = str(q.get("message") or "").strip()
    reason = msg.split("。")[0].strip() if msg else ""
    if not reason:
        # 没有说明时退回错误码对应的中文短句
        reason = _ERROR_BRIEF.get(str(q.get("error") or ""), "内容不符合要求")
    return "⚠️ 本条未通过质检，后续将补发修正版。原因：" + reason


def _block_text(b, push_thinking):
    """纯文本块：段落 / 标题 / 引用共用同一取文本方式。"""
    return _scrub_traces(str(b.get("text") or ""))


def _block_list(b, push_thinking):
    """列表块：每个元素前置「- 」并换行拼接。"""
    items = b.get("items") or []
    return "\n".join("- " + str(x) for x in items)


def _block_table(b, push_thinking):
    """表格块：转成纯文本列表，避开竖线在手机端读成碎句的问题。

    首行按表头处理，每条数据行输出为「- 列名：值；列名：值」。
    列数与表头对不上时退回「；」直接连接，保证内容不丢。
    """
    rows = [r for r in (b.get("rows") or []) if r]
    if not rows:
        return ""
    # 单元格统一转字符串并去掉换行，避免一条列表项被撑成多行
    norm = [[str(c).replace("\n", " ").strip() for c in row] for row in rows]
    header, body = (norm[0], norm[1:]) if len(norm) > 1 else ([], norm)
    lines = []
    for row in body:
        # 列数与表头一致时按「列名：值」组织，否则退回简单连接
        if header and len(header) == len(row):
            cells = ["%s：%s" % (header[i], row[i]) for i in range(len(row))]
        else:
            cells = row
        lines.append("- " + "；".join(cells))
    return "\n".join(lines)


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
