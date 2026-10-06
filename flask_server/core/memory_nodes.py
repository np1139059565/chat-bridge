"""AI 工具调用镜像插件 —— 记忆系统：节点表读写

职责：nodes 表的增删改查，是记忆系统的最小存储单元。
每个节点对应消息树里的一个消息，另挂蒸馏层字段（精华/关键词/分级/强度）。

关键约定：
  - msg_id 全局唯一，重复写入按 msg_id 幂等（ON CONFLICT 更新内容，不新增行）；
  - blocks 永久保留、无损存储，蒸馏不覆盖它；
  - source 取 user / assistant / tool，用于事件层判定根节点。

依赖：memory_db（连接）、json、time
"""
import json
import time

from memory_db import get_conn, vec_to_blob, blob_to_vec, cosine_topk, maybe_commit


def _now():
    """当前 Unix 时间戳（秒）。"""
    return int(time.time())


def upsert_node(identity, fields, created_at=None):
    """按 msg_id 幂等写入节点；已存在则更新内容字段，不动蒸馏字段。

    参数拆成两段，避免长参数列表：
    @param identity { msg_id, conv_id, site_key } 定位该节点的三要素
    @param fields { source, role, name, blocks, parent_id } 节点内容字段
    @return 节点 id
    """
    msg_id = identity.get("msg_id")
    conv_id = identity.get("conv_id", "")
    site_key = identity.get("site_key", "")
    parent_id = fields.get("parent_id", 0)
    conn = get_conn()
    ts = created_at or _now()
    blocks_json = json.dumps(fields.get("blocks") or [], ensure_ascii=False)
    cur = conn.execute(
        "INSERT INTO nodes (msg_id, conv_id, site_key, parent_id, source, role, name, blocks, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(msg_id) DO UPDATE SET blocks=excluded.blocks, parent_id=excluded.parent_id",
        (msg_id, conv_id, site_key, parent_id, fields.get("source"),
         fields.get("role", ""), fields.get("name", ""), blocks_json, ts),
    )
    maybe_commit(conn)
    if cur.lastrowid:
        return cur.lastrowid
    # 冲突更新时 lastrowid 不可靠，回查一次
    row = conn.execute("SELECT id FROM nodes WHERE msg_id=?", (msg_id,)).fetchone()
    return row["id"] if row else None


def get_node(node_id):
    """按 id 取节点，返回 dict（blocks 已反序列化）；不存在返回 None。"""
    row = get_conn().execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    return _row_to_dict(row)


def get_by_msg_id(msg_id):
    """按消息指纹取节点；不存在返回 None。"""
    row = get_conn().execute("SELECT * FROM nodes WHERE msg_id=?", (msg_id,)).fetchone()
    return _row_to_dict(row)


def list_by_conv(conv_id, site_key=None):
    """列出某会话的全部节点，按创建时间升序。"""
    if site_key:
        rows = get_conn().execute(
            "SELECT * FROM nodes WHERE conv_id=? AND site_key=? ORDER BY created_at, id",
            (conv_id, site_key),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM nodes WHERE conv_id=? ORDER BY created_at, id", (conv_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_all():
    """列出全库未删除节点，按创建时间升序（图谱「留空看全部」用）。"""
    rows = get_conn().execute(
        "SELECT * FROM nodes WHERE deleted=0 ORDER BY created_at, id"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def set_essence(node_id, essence, keywords, vector=None):
    """写入蒸馏结果：精华、关键词、向量。不覆盖 blocks。"""
    conn = get_conn()
    kw_json = json.dumps(keywords or [], ensure_ascii=False)
    conn.execute(
        "UPDATE nodes SET essence=?, keywords=?, vector=? WHERE id=?",
        (essence, kw_json, vec_to_blob(vector), node_id),
    )
    maybe_commit(conn)


def set_parent(node_id, parent_id):
    """设置节点的父 id（建树用；父节点可能晚于子节点写入）。"""
    conn = get_conn()
    conn.execute("UPDATE nodes SET parent_id=? WHERE id=?", (parent_id, node_id))
    maybe_commit(conn)


def set_tier(node_id, tier, strength=None):
    """更新分级标签与（可选）强度。"""
    conn = get_conn()
    if strength is None:
        conn.execute("UPDATE nodes SET tier=? WHERE id=?", (tier, node_id))
    else:
        conn.execute("UPDATE nodes SET tier=?, strength=? WHERE id=?", (tier, strength, node_id))
    maybe_commit(conn)


def touch_hit(node_id):
    """标记一次命中：命中次数 +1，记录最后命中时间。"""
    conn = get_conn()
    conn.execute(
        "UPDATE nodes SET hit_count=hit_count+1, last_hit_at=? WHERE id=?", (_now(), node_id)
    )
    maybe_commit(conn)


def set_strength(node_id, strength):
    """直接写强度值（衰减计算用）。"""
    conn = get_conn()
    conn.execute("UPDATE nodes SET strength=? WHERE id=?", (float(strength), node_id))
    maybe_commit(conn)


def soft_delete(node_id):
    """软删除：置 deleted=1，节点保留、树不断裂。"""
    conn = get_conn()
    conn.execute("UPDATE nodes SET deleted=1 WHERE id=?", (node_id,))
    maybe_commit(conn)


def set_content(node_id, blocks=None, essence=None, keywords=None):
    """更新节点的内容字段（接口 memory_set 的落点）。

    只更新调用方显式传入的字段，未传入的保持原值，避免误清空；
    blocks 传入时整体替换，essence/keywords 属蒸馏层字段。
    @return 是否有字段被更新
    """
    sets = []
    args = []
    if blocks is not None:
        sets.append("blocks=?")
        args.append(json.dumps(blocks, ensure_ascii=False))
    if essence is not None:
        sets.append("essence=?")
        args.append(essence)
    if keywords is not None:
        sets.append("keywords=?")
        args.append(json.dumps(keywords or [], ensure_ascii=False))
    if not sets:
        return False
    args.append(node_id)
    conn = get_conn()
    conn.execute("UPDATE nodes SET %s WHERE id=?" % ", ".join(sets), args)
    maybe_commit(conn)
    return True


def promote_node(node_id, tier):
    """手动设置节点分级（接口 memory_promote 的落点）。

    与自动升降级互补：这是人工干预入口，不校验触发条件。
    @return 更新后的节点 dict；节点不存在返回 None
    """
    set_tier(node_id, tier)
    return get_node(node_id)


def get_strength(node_id):
    """查询节点当前强度（接口 memory_strength 的落点）。

    @return 强度浮点值；节点不存在返回 None
    """
    row = get_conn().execute("SELECT strength FROM nodes WHERE id=?", (node_id,)).fetchone()
    return float(row["strength"]) if row and row["strength"] is not None else None


def all_with_vectors():
    """取全部带向量的节点，供向量检索用，返回 [(id, blob)]。"""
    rows = get_conn().execute(
        "SELECT id, vector FROM nodes WHERE vector IS NOT NULL AND deleted=0"
    ).fetchall()
    return [(r["id"], r["vector"]) for r in rows]


def search_vectors(query_vec, top_k=10):
    """向量语义近邻检索：暴力余弦，返回 [(node_id, 相似度)]。"""
    return cosine_topk(query_vec, all_with_vectors(), top_k)


def _row_to_dict(row):
    """sqlite3.Row 转 dict，并反序列化 blocks / keywords。"""
    if row is None:
        return None
    d = dict(row)
    try:
        d["blocks"] = json.loads(d.get("blocks") or "[]")
    except Exception:
        d["blocks"] = []
    try:
        d["keywords"] = json.loads(d.get("keywords") or "[]")
    except Exception:
        d["keywords"] = []
    d.pop("vector", None)  # 向量体积大，不随节点返回
    return d
