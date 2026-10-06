"""AI 工具调用镜像插件 —— memory_search 工具实现

职责：把记忆系统的「双接口防幻觉检索」包装成 AI 可直接调用的工具，
让 AI 能回查自己积累的历史记忆（此前记忆只写不读，闭环断裂）。

对设计文档《记忆机制改进方案》第六节的落地：
  接口 A（plan_submit）：把任务原文存为检索真值基准；
  接口 B（memory_search）：关键词须逐字出现在计划原文里，再走三路检索融合。
本工具把两步合成一次调用，降低 AI 的使用门槛：
  1. 以 query（当前任务/问题原文）作为计划基准；
  2. 未显式给 keywords 时，自动从 query 提取关键词；
  3. 调用底层 memory_search，返回命中节点。

对外接口：
- t_memory_search(p)   工具入口（签名与其它 t_xxx 一致）

依赖：memory_search（核心检索层）、memory_keywords（关键词提取）
"""
from tool_helpers import ToolParamError, require as _require

# 默认返回条数：不宜过多，避免一次塞满上下文
DEFAULT_TOP_K = 10
# 关键词自动提取条数上限
KEYWORD_TOPK = 8
# 允许的排序焦点：与 memory_search._rank 支持的值保持一致
_VALID_FOCUS = ("relevance", "time", "strength")


def _resolve_top_k(raw):
    """解析返回条数：未传用默认；非法或越界抛参数错误。"""
    if raw is None or (isinstance(raw, str) and str(raw).strip() == ""):
        return DEFAULT_TOP_K
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ToolParamError("top_k 必须是正整数，收到：%r" % (raw,))
    if value <= 0:
        raise ToolParamError("top_k 必须大于 0，收到：%d" % value)
    # 上限保护：一次最多 50 条，防上下文被塞爆
    return min(value, 50)


def _resolve_focus(raw):
    """解析排序焦点：未传用 relevance；非法值抛参数错误。"""
    if not raw:
        return "relevance"
    focus = str(raw).strip().lower()
    if focus not in _VALID_FOCUS:
        raise ToolParamError(
            "focus 非法：%s（可选：%s）" % (raw, " / ".join(_VALID_FOCUS)))
    return focus


def _resolve_keywords(p, query):
    """确定检索关键词：显式给了就用，否则从 query 自动提取。"""
    raw = p.get("keywords")
    if isinstance(raw, list) and raw:
        # 显式关键词：去空白、去空项，保持顺序
        return [str(k).strip() for k in raw if str(k).strip()]
    # 未给：从 query 自动提取，保证工具「开箱即用」
    try:
        import memory_keywords
        return memory_keywords.extract(query, top_k=KEYWORD_TOPK)
    except Exception:
        return []


def t_memory_search(p):
    """按查询文本检索历史记忆，返回命中的节点摘要。

    典型用法：AI 需要回忆「用户之前说过什么」「这个问题以前怎么解决的」时，
    把当前任务或问题原文传给 query，即可拿到相关历史节点。

    @param p 工具参数 { query, keywords?, focus?, top_k? }
    @return { ok, query, keywords, focus, hits:[...], rejected, plan_found }
    """
    _require(p, "query")
    query = str(p.get("query") or "").strip()
    if not query:
        raise ToolParamError("query 不能为空")
    focus = _resolve_focus(p.get("focus"))
    top_k = _resolve_top_k(p.get("top_k"))
    keywords = _resolve_keywords(p, query)
    if not keywords:
        # 提取不到关键词：无锚点可验证，按空结果返回并说明，不报错
        return {
            "ok": True, "query": query, "keywords": [], "focus": focus,
            "hits": [], "rejected": [], "plan_found": False,
            "note": "未能从 query 提取到关键词，请改用更具体的查询文本或显式给 keywords。",
        }
    # 延迟导入：核心模块已在 sys.path，避免工具加载期就拉起记忆整包
    import memory_search as _ms
    # 接口 A：以 query 作为计划真值基准
    plan_id = _ms.plan_submit(query)
    # 接口 B：验证式关联检索
    result = _ms.memory_search(plan_id, keywords, focus=focus, top_k=top_k)
    hits = result.get("hits") or []
    return {
        "ok": True, "query": query, "keywords": keywords, "focus": focus,
        "hits": hits,
        "rejected": result.get("rejected") or [],
        "plan_found": bool(result.get("plan_found")),
        "count": len(hits),
        "note": ("命中 %d 条相关记忆。" % len(hits)) if hits
                else "未命中相关记忆（可能确无记录，或关键词不在计划原文中）。",
    }
