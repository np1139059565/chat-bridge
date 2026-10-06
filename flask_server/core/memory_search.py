"""AI 工具调用镜像插件 —— 记忆系统：检索层（双接口防幻觉）

职责（方案第六节）：
  接口 A（plan_submit）：把任务计划原文存入 plans 表，作为检索的真值基准。
  接口 B（memory_search）：验证式关联搜索，三步固定顺序——
    1. 锚定验证：关键词必须逐字出现在计划原文里，否则拒绝；
    2. 三路检索：关键词 LIKE 子串匹配 + 向量近邻 + 以关键词路结果为种子的图遍历；
    3. 交叉验证 + RRF 融合，再乘关键词交集置信度，按 focus 排序。

依赖：memory_db、memory_nodes、memory_edges、uuid、time
"""
import time
import uuid

from memory_db import get_conn, cosine_topk, blob_to_vec
import memory_nodes
import memory_edges
import memory_keywords


def plan_submit(plan_text, session_id=""):
    """接口 A：暂存任务计划原文，返回 plan_id。纯写入，不检索。"""
    pid = uuid.uuid4().hex[:16]
    conn = get_conn()
    conn.execute(
        "INSERT INTO plans (plan_id, session_id, text, created_at) VALUES (?,?,?,?)",
        (pid, session_id, plan_text or "", int(time.time())),
    )
    conn.commit()
    return pid


def get_plan(plan_id):
    """取计划原文；不存在返回 None。"""
    row = get_conn().execute(
        "SELECT * FROM plans WHERE plan_id=?", (plan_id,)
    ).fetchone()
    return dict(row) if row else None


def memory_search(plan_id, keywords, focus="relevance", top_k=10):
    """接口 B：验证式关联搜索。

    @return dict { hits: [...], rejected: [...], plan_found: bool }
    """
    plan = get_plan(plan_id)
    plan_text = (plan or {}).get("text", "")
    # 第 1 步：锚定验证——逐字比对
    valid, rejected = [], []
    for kw in (keywords or []):
        if kw and kw in plan_text:
            valid.append(kw)
        else:
            rejected.append(kw)
    if not valid:
        return {"hits": [], "rejected": rejected, "plan_found": bool(plan)}
    # 第 2 步：三路并行检索
    fts_hits = _fts_search(valid, top_k * 3)
    vec_hits = _vector_search(valid, top_k * 3)
    graph_hits = _graph_search([h[0] for h in fts_hits[:3]], top_k * 3)
    # 第 3 步：RRF 融合 + 关键词交集置信度
    scores = _rrf_fuse([fts_hits, vec_hits, graph_hits])
    hits = _rank(scores, valid, focus, top_k)
    return {"hits": hits, "rejected": rejected, "plan_found": bool(plan)}


def _vector_search(keywords, limit):
    """向量语义近邻检索：用关键词拼成查询向量，暴力余弦取近邻。

    这是方案第六节的第三路。查询向量由有效关键词拼接后哈希生成，
    与蒸馏时对节点生成的向量同源同法，保证可比。无向量节点时返回空。
    @return [(node_id, rank)]
    """
    if not keywords:
        return []
    try:
        q = memory_keywords.text_to_vector(" ".join(keywords))
        scored = memory_nodes.search_vectors(q, limit)
    except Exception:
        return []
    return [(nid, i) for i, (nid, _sim) in enumerate(scored)]


def _fts_search(keywords, limit):
    """关键词检索：子串匹配（LIKE），返回 [(node_id, rank)]。

    为何不用 FTS5 MATCH：FTS5 的默认分词器把整段连续汉字当成一个词元，
    「网页版机器人语音」匹配不上「网页版机器人语音要自动播放」，中文检索失效。
    改用 LIKE 子串匹配，命中率更符合中文短语场景；语料量小，性能足够。
    """
    conn = get_conn()
    scores = {}
    for kw in keywords:
        like = "%" + kw + "%"
        rows = conn.execute(
            "SELECT id FROM nodes WHERE (essence LIKE ? OR keywords LIKE ?) AND deleted=0 LIMIT ?",
            (like, like, limit),
        ).fetchall()
        for r in rows:
            # 命中关键词越多，排序越靠前（用负命中数当 rank）
            scores[r["id"]] = scores.get(r["id"], 0) + 1
    # 按命中数降序，转成 (node_id, rank)
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(nid, i) for i, (nid, _) in enumerate(ordered[:limit])]


def _graph_search(seed_ids, limit):
    """图遍历：从种子节点沿边扩一跳，返回 [(node_id, rank)]。"""
    out = []
    seen = set()
    for sid in seed_ids:
        for nid in memory_edges.get_neighbors(sid):
            if nid not in seen:
                seen.add(nid)
                out.append((nid, len(out)))
            if len(out) >= limit:
                return out
    return out


def _rrf_fuse(lists, k=60):
    """RRF 融合多路排名：score += 1/(k+rank)。返回 {node_id: score}。"""
    scores = {}
    for lst in lists:
        for nid, rank in lst:
            scores[nid] = scores.get(nid, 0.0) + 1.0 / (k + rank)
    return scores


def _rank(scores, valid_keywords, focus, top_k):
    """按交集置信度加权，按 focus 排序，返回命中列表。"""
    vset = set(valid_keywords)
    enriched = []
    for nid, base in scores.items():
        node = memory_nodes.get_node(nid)
        if not node:
            continue
        nk = set(node.get("keywords") or [])
        inter = len(nk & vset)
        union = len(nk | vset) or 1
        jac = inter / union
        final = base * (0.5 + 0.5 * jac)
        enriched.append((node, final, jac))
    if focus == "time":
        enriched.sort(key=lambda x: x[0].get("created_at") or 0, reverse=True)
    elif focus == "strength":
        enriched.sort(key=lambda x: x[0].get("strength") or 0, reverse=True)
    else:
        enriched.sort(key=lambda x: x[1], reverse=True)
    out = []
    for node, final, jac in enriched[:top_k]:
        # 命中计数 + 突触强化
        memory_nodes.touch_hit(node["id"])
        out.append({
            "node_id": node["id"],
            "source": node.get("source"),
            "essence": node.get("essence"),
            "keywords": node.get("keywords"),
            "score": round(final, 4),
            "jaccard": round(jac, 4),
            "conv_id": node.get("conv_id"),
        })
    return out
