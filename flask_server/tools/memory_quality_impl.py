"""AI 工具调用镜像插件 —— 记忆蒸馏质量管理工具

职责：让 AI 能抽检「过往记忆的蒸馏质量」并在发现偏差时主动修正。
这是把「记忆告警」从「确认 AI 记没记」升级为「把控蒸馏质量」的核心能力。

两个工具：
- memory_inspect：抽检。给节点 id（或范围），返回「原文 vs 蒸馏精华/关键词」，
  供 AI 对比判断蒸馏是否失真、关键词是否有效。
- memory_refine：修正。AI 判定蒸馏偏差过大时，直接改写该节点的精华与关键词。

为何以「直接修正」替代「调蒸馏参数」：
  蒸馏参数（截断长度等）是全局抽象值，调它既难界定又影响所有节点；
  而针对具体节点直接改写，精准、可控、可追溯，且存储层已支持（set_content）。

对外接口：
- t_memory_inspect(p)  抽检入口
- t_memory_refine(p)   修正入口

依赖：memory_nodes（节点读写）、memory_keywords（关键词提取，供原文对比）
"""
from tool_helpers import ToolParamError, require as _require

# 抽检返回的原文预览长度：够 AI 判断语义是否失真，又不至于塞爆上下文
_PREVIEW_LIMIT = 400
# 一次抽检最多返回节点数，防上下文爆炸
_MAX_INSPECT = 20


def _blocks_to_text(blocks):
    """把节点 blocks 抽成纯文本，供 AI 与蒸馏精华对比。"""
    parts = []
    for b in (blocks or []):
        if not isinstance(b, dict):
            continue
        t = b.get("text") or b.get("code") or ""
        if t:
            parts.append(str(t))
    return "\n".join(parts).strip()


def _preview(text, limit=_PREVIEW_LIMIT):
    """截断文本到预览长度，超出加省略标记。"""
    s = (text or "").strip()
    return s if len(s) <= limit else (s[:limit] + "…（已截断）")


def _node_view(node):
    """把节点整理成「原文 + 蒸馏」对照视图。"""
    raw = _blocks_to_text(node.get("blocks"))
    return {
        "node_id": node.get("id"),
        "source": node.get("source"),
        "created_at": node.get("created_at"),
        "raw_preview": _preview(raw),
        "raw_length": len(raw),
        "essence": node.get("essence") or "",
        "keywords": node.get("keywords") or [],
        "has_essence": bool((node.get("essence") or "").strip()),
    }


def _resolve_ids(p):
    """确定要抽检的节点 id 列表：显式给就用，否则取该会话最近若干节点。"""
    raw = p.get("node_ids")
    if isinstance(raw, list) and raw:
        ids = []
        for x in raw:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                raise ToolParamError("node_ids 必须是整数列表，收到非法值：%r" % (x,))
        return ids[:_MAX_INSPECT]
    # 未给：按 conv_id 取最近节点（默认取该会话），或全库最近
    import memory_nodes
    conv_id = str(p.get("conv_id") or "").strip()
    if conv_id:
        nodes = memory_nodes.list_by_conv(conv_id, None)
    else:
        nodes = memory_nodes.list_all()
    # 取最近若干（list_all 按 created_at 升序，取尾部）
    limit = p.get("limit")
    try:
        n = int(limit) if limit is not None else 5
    except (TypeError, ValueError):
        raise ToolParamError("limit 必须是整数，收到：%r" % (limit,))
    n = max(1, min(n, _MAX_INSPECT))
    return [x["id"] for x in nodes[-n:]]


def t_memory_inspect(p):
    """抽检蒸馏质量：返回「原文 vs 蒸馏精华/关键词」对照。

    用法：给 node_ids 精确抽检，或给 conv_id（+limit）抽检该会话最近节点。
    AI 应据返回判断：精华是否失真、关键词是否有效，偏差大则用 memory_refine 修正。

    @return { ok, items:[对照视图], count, note }
    """
    import memory_nodes
    ids = _resolve_ids(p)
    items = []
    for nid in ids:
        node = memory_nodes.get_node(nid)
        if node:
            items.append(_node_view(node))
    return {
        "ok": True,
        "items": items,
        "count": len(items),
        "note": ("抽检 %d 个节点。请对比 raw_preview 与 essence："
                 "若精华语义失真、遗漏要点，或关键词与实际内容不符，"
                 "用 memory_refine 修正该节点的 essence / keywords。" % len(items))
                if items else "未找到可抽检的节点。",
    }


def t_memory_refine(p):
    """修正某节点的蒸馏结果：改写精华与关键词。

    AI 抽检发现蒸馏失真时调用。只改蒸馏层字段（essence / keywords），
    不动原始 blocks——原文永久保留，修正可随时重来。

    @param p { node_id, essence?, keywords?, reason? }
    @return { ok, node_id, updated, essence, keywords }
    """
    _require(p, "node_id")
    try:
        nid = int(p.get("node_id"))
    except (TypeError, ValueError):
        raise ToolParamError("node_id 必须是整数，收到：%r" % (p.get("node_id"),))
    import memory_nodes
    node = memory_nodes.get_node(nid)
    if not node:
        raise ToolParamError("节点不存在：%d" % nid)
    essence = p.get("essence")
    keywords = p.get("keywords")
    # 至少要改一项，否则无意义
    if essence is None and keywords is None:
        raise ToolParamError("essence 与 keywords 至少要提供一个")
    if essence is not None:
        essence = str(essence).strip()
        if not essence:
            raise ToolParamError("essence 不能为空字符串")
    if keywords is not None:
        if not isinstance(keywords, list):
            raise ToolParamError("keywords 必须是字符串数组")
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
    # 更新蒸馏层字段（set_content 只改显式传入的项）
    memory_nodes.set_content(nid, essence=essence, keywords=keywords)
    # 若改了精华，同步刷新向量，保证检索第三路与最新精华一致
    if essence is not None:
        try:
            import memory_keywords as kw
            vec = kw.text_to_vector(essence)
            conn = memory_nodes.get_conn()
            conn.execute("UPDATE nodes SET vector=? WHERE id=?",
                         (memory_nodes.vec_to_blob(vec), nid))
            memory_nodes.maybe_commit(conn)
        except Exception:
            pass  # 向量刷新失败不影响精华修正本身
    updated = memory_nodes.get_node(nid)
    return {
        "ok": True,
        "node_id": nid,
        "updated": True,
        "essence": updated.get("essence") or "",
        "keywords": updated.get("keywords") or [],
        "note": "已修正该节点蒸馏结果（原始 blocks 未改动）。",
    }
