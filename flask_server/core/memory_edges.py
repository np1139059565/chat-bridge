"""AI 工具调用镜像插件 —— 记忆系统：边表读写

职责：edges 表的增删改查。边承载三种关系：
  - parent_child：消息树的父子边（对应 msgTree 的 '父id-子id'）；
  - branch：同一父节点分出 ≥2 条子边时，标记为版本分叉（重新生成）；
  - associative：跨树突触边，由关键词交集触发。

关键约定：
  - (src, dst, kind) 唯一，重复建边走权重强化，不新增行；
  - 突触边有饱和式强化与时间衰减；
  - 边权重参与节点的衰减率计算（见 memory_decay）。

依赖：memory_db（连接）、time
"""
import time

from memory_db import get_conn, maybe_commit


def _now():
    """当前 Unix 时间戳（秒）。"""
    return int(time.time())


def add_edge(src, dst, kind, weight=1.0):
    """建边；已存在则强化权重，不新增行。"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO edges (src_node, dst_node, kind, weight, created_at, last_active_at)"
        " VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(src_node, dst_node, kind) DO UPDATE SET"
        " weight=MIN(1.0, edges.weight + 0.2 * (1.0 - edges.weight)),"
        " last_active_at=excluded.last_active_at",
        (src, dst, kind, float(weight), _now(), _now()),
    )
    maybe_commit(conn)


def reinforce_edge(src, dst, kind="associative", delta=0.2):
    """饱和式强化一条边：weight += delta * (1 - weight)，上限 1.0。"""
    conn = get_conn()
    conn.execute(
        "UPDATE edges SET weight = MIN(1.0, weight + ? * (1.0 - weight)),"
        " last_active_at=? WHERE src_node=? AND dst_node=? AND kind=?",
        (float(delta), _now(), src, dst, kind),
    )
    maybe_commit(conn)


def get_neighbors(node_id, kind=None):
    """取某节点的全部邻居（出边 + 入边），返回节点 id 列表。

    @param kind 只取指定类型；None 表示全部
    """
    conn = get_conn()
    if kind:
        rows = conn.execute(
            "SELECT dst_node AS nid FROM edges WHERE src_node=? AND kind=?"
            " UNION SELECT src_node AS nid FROM edges WHERE dst_node=? AND kind=?",
            (node_id, kind, node_id, kind),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT dst_node AS nid FROM edges WHERE src_node=?"
            " UNION SELECT src_node AS nid FROM edges WHERE dst_node=?",
            (node_id, node_id),
        ).fetchall()
    return [r["nid"] for r in rows]


def associative_weight_sum(node_id):
    """某节点全部 associative 边的权重之和（供衰减率计算）。"""
    row = get_conn().execute(
        "SELECT COALESCE(SUM(weight), 0) AS s FROM edges"
        " WHERE kind='associative' AND (src_node=? OR dst_node=?)",
        (node_id, node_id),
    ).fetchone()
    return float(row["s"]) if row else 0.0


def decay_edges(half_life_days=30, floor=0.1):
    """对突触边做时间衰减：超期未激活的权重减半，过低标 dormant。

    @param half_life_days 半衰期（天）
    @param floor 低于此权重标记 dormant
    @return 受影响边数
    """
    conn = get_conn()
    now = _now()
    span = int(half_life_days * 86400)
    rows = conn.execute(
        "SELECT id, weight, last_active_at FROM edges WHERE kind='associative' AND weight > 0"
    ).fetchall()
    changed = 0
    for r in rows:
        idle = now - (r["last_active_at"] or now)
        if idle < span:
            continue
        # 每过一个半衰期权重减半；公式：w * 2^(-idle/half_life)
        factor = 2.0 ** (-idle / span)
        new_w = r["weight"] * factor
        if new_w < floor:
            new_w = 0.0
        conn.execute("UPDATE edges SET weight=? WHERE id=?", (new_w, r["id"]))
        changed += 1
    maybe_commit(conn)
    return changed


def edges_from(src, kind=None):
    """取某节点作为源的全部边，返回 dict 列表。"""
    conn = get_conn()
    if kind:
        rows = conn.execute(
            "SELECT * FROM edges WHERE src_node=? AND kind=?", (src, kind)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM edges WHERE src_node=?", (src,)).fetchall()
    return [dict(r) for r in rows]


def all_edges():
    """取全部边（可视化用）。"""
    rows = get_conn().execute("SELECT * FROM edges").fetchall()
    return [dict(r) for r in rows]


def edges_within(node_ids):
    """取两端都在给定节点集合内的边（图谱按会话过滤用）。

    用于让边与节点同口径：只保留 src、dst 均在该集合中的边，
    避免出现「0 节点却配全库边」的口径错位。
    @param node_ids 节点 id 的可迭代集合
    @return 边 dict 列表；集合为空时返回空列表
    """
    ids = list(node_ids)
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    rows = get_conn().execute(
        "SELECT * FROM edges WHERE src_node IN (%s) AND dst_node IN (%s)" % (placeholders, placeholders),
        ids + ids,
    ).fetchall()
    return [dict(r) for r in rows]
