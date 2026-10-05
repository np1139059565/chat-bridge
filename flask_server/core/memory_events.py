"""AI 工具调用镜像插件 —— 记忆系统：事件层

职责（方案第五节）：
  1. 用户发言为根 → 每句用户发言是一棵记忆树的根；
  2. 语义聚类 → 跨会话「讲同一件事」的发言聚成事件；
  3. 突触关联 → 关键词交集达阈值时，节点间建 associative 边；
  4. 三条护栏 → 边界锚定、语义化延迟、修订留痕。

依赖：memory_db、memory_nodes、memory_edges、json、time
"""
import json
import time

from memory_db import get_conn, maybe_commit
import memory_nodes
import memory_edges

# 突触建边门槛：交集 >= 3 且 Jaccard >= 0.3
SYNAPSE_MIN_INTERSECT = 3
SYNAPSE_MIN_JACCARD = 0.3


def build_synapses(new_node_id):
    """为新节点与已有节点按关键词交集建突触边。

    @return 新建/强化边数
    """
    new_node = memory_nodes.get_node(new_node_id)
    if not new_node:
        return 0
    nk = set(new_node.get("keywords") or [])
    if not nk:
        return 0
    conn = get_conn()
    # 一次查出全部候选（id + keywords），不再逐个 get_node；
    # 此前每建一次突触要全表扫描 + 逐行回查，N 个节点就是 N 次查询，
    # 在并发入库时把写锁长期占住。改为单查询 + 内存匹配。
    rows = conn.execute(
        "SELECT id, keywords FROM nodes WHERE id!=? AND keywords IS NOT NULL AND keywords!='' AND deleted=0",
        (new_node_id,),
    ).fetchall()
    count = 0
    for r in rows:
        ok = set(_loads(r["keywords"], []))
        if not ok:
            continue
        # 包含式匹配：一个关键词是另一个的子串即算相关（中文短语常有包含关系）
        inter = _related(nk, ok)
        # 自适应交集门槛：关键词数量少时，硬套 3 会永远建不成边。
        # 取「关键词较少一方的一半（向上取整）」与 3 的较小值，下限 1：
        #   各 1~2 个词 → 门槛 1；各 3~4 个词 → 门槛 2；各 ≥5 个词 → 门槛 3。
        # 仍由下方 Jaccard 门槛兜底，避免少量巧合词就建边。
        need = min(SYNAPSE_MIN_INTERSECT, max(1, (min(len(nk), len(ok)) + 1) // 2))
        if len(inter) < need:
            continue
        union = len(nk) + len(ok) - len(inter)
        jac = len(inter) / union if union else 0
        if jac < SYNAPSE_MIN_JACCARD:
            continue
        # 无向去重：同一对节点只建一条边，以较小 id 为 src 规范化。
        # 此前用「跳过 id 较小的一方」实现去重，方向写反，导致新节点
        # （id 总是更大）对全部已有节点都跳过，突触永远建不成。
        lo, hi = (new_node_id, r["id"]) if new_node_id < r["id"] else (r["id"], new_node_id)
        memory_edges.add_edge(lo, hi, "associative", weight=float(len(inter)))
        count += 1
    return count


def _related(nk, ok):
    """求两组关键词的「相关交集」：一个词是另一个的子串即算命中。

    中文短语常有包含关系（如「网页版机器人语音」⊂「网页版机器人语音自动播放」），
    用精确相等会漏掉这类真实关联，故改用包含式匹配。
    命中项取较短的那一方：短词更通用，也保证不同关键词的命中不被合并成一个。
    @return 命中的关键词集合
    """
    hits = set()
    for a in nk:
        for b in ok:
            if a in b or b in a:
                hits.add(a if len(a) <= len(b) else b)
    return hits


def reinforce_by_hits(hit_ids):
    """一次检索命中多个节点时，两两强化它们之间的突触边。

    @param hit_ids 本次命中的节点 id 列表
    """
    for i in range(len(hit_ids)):
        for j in range(i + 1, len(hit_ids)):
            memory_edges.reinforce_edge(hit_ids[i], hit_ids[j], "associative")


def cluster_events(min_shared=2):
    """把跨会话讲同一件事的用户发言聚成事件。

    做法：以关键词共享数为相似度，对 user 节点做并查集聚类；
    同一簇内的根节点共享一个 event_id（写入节点的 name 字段前缀不便，
    改用 revision_log 记录聚类事件 + 在返回里给映射）。

    @return { event_id: [root_node_id, ...] }
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, keywords FROM nodes WHERE source='user' AND deleted=0"
    ).fetchall()
    roots = []
    for r in rows:
        kwset = _loads(r["keywords"], [])
        if kwset:
            roots.append((r["id"], set(kwset)))
    # 并查集
    parent = {nid: nid for nid, _ in roots}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(roots)):
        for j in range(i + 1, len(roots)):
            # 包含式匹配：与突触建边同一套判定，避免「精确相等」漏掉真实关联
            if len(_related(roots[i][1], roots[j][1])) >= min_shared:
                union(roots[i][0], roots[j][0])
    clusters = {}
    for nid, _ in roots:
        clusters.setdefault(find(nid), []).append(nid)
    # 只保留多节点的事件
    events = {}
    for root_id, members in clusters.items():
        if len(members) >= 2:
            events["event-%d" % root_id] = sorted(members)
    return events


def anchor_boundary(node_id, boundary_text, reason):
    """护栏一·边界锚定：记录触发事件边界的原句。"""
    _log_revision(node_id, "", boundary_text, "boundary:" + (reason or ""))


def log_semantic_revision(node_id, old_text, new_text, reason):
    """护栏三·修订留痕：任何语义修订只追加不覆盖。"""
    _log_revision(node_id, old_text, new_text, reason)


def _log_revision(node_id, old_text, new_text, reason):
    """写一条修订日志。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO revision_log (node_id, old_text, new_text, reason, created_at)"
        " VALUES (?,?,?,?,?)",
        (node_id, old_text, new_text, reason, int(time.time())),
    )
    maybe_commit(conn)


def event_history(root_id):
    """取某事件的全部关联节点（按时间排序），供接口感知事件树。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM revision_log WHERE node_id=? ORDER BY created_at", (root_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def event_merge(root_id, member_ids, reason="manual"):
    """把若干事件根节点合并到同一事件（接口 event_merge 的落点）。

    事件层全自动，但保留人工合并入口。合并动作写入 revision_log 留痕，
    并在每条被并入的根上登记归属，使 event_tree_get 能按根聚合。
    @param root_id 目标事件根节点 id
    @param member_ids 要并入的其它根节点 id 列表
    @return 实际并入的节点数
    """
    conn = get_conn()
    merged = 0
    for mid in (member_ids or []):
        if not mid or mid == root_id:
            continue
        conn.execute(
            "INSERT INTO revision_log (node_id, old_text, new_text, reason, created_at)"
            " VALUES (?,?,?,?,?)",
            (mid, "", str(root_id), "merge:%s" % reason, int(time.time())),
        )
        merged += 1
    maybe_commit(conn)
    return merged


def event_tree_get(root_id):
    """取某事件树：根节点 + 被并入的成员根 + 全部相关节点（接口 event_tree_get 的落点）。

    组装三部分：根节点本身、revision_log 里登记归属该根的被并节点、
    以及根节点下的子节点（parent_id 指向根）。
    @return dict { root, members, children }；根不存在返回 None
    """
    root = memory_nodes.get_node(root_id)
    if not root:
        return None
    conn = get_conn()
    member_rows = conn.execute(
        "SELECT node_id FROM revision_log WHERE new_text=? AND reason LIKE 'merge:%'",
        (str(root_id),),
    ).fetchall()
    members = []
    for r in member_rows:
        m = memory_nodes.get_node(r["node_id"])
        if m:
            members.append(m)
    child_rows = conn.execute(
        "SELECT id FROM nodes WHERE parent_id=? AND deleted=0 ORDER BY created_at, id",
        (root_id,),
    ).fetchall()
    children = []
    for r in child_rows:
        c = memory_nodes.get_node(r["id"])
        if c:
            children.append(c)
    return {"root": root, "members": members, "children": children}


def set_shadow(root_id, summary):
    """护栏二·语义化延迟：把语义摘要作为影子挂在原句根节点上。

    原句始终保留在节点 blocks 里，影子只记摘要文本，检索优先返回原句。
    影子以 revision_log 记录（reason=shadow），不覆盖原节点任何字段。
    """
    _log_revision(root_id, "", summary or "", "shadow")


def get_shadow(root_id):
    """取某节点的最新影子摘要；无则返回 None。"""
    row = get_conn().execute(
        "SELECT new_text FROM revision_log WHERE node_id=? AND reason='shadow'"
        " ORDER BY created_at DESC LIMIT 1",
        (root_id,),
    ).fetchone()
    return row["new_text"] if row else None


def _loads(text, default):
    """安全反序列化。"""
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default
