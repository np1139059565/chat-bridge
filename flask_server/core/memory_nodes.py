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


# 初始分级映射（设计文档 4.4）：用户发言 perm、AI 回复 temp、工具结果 mid
_INITIAL_TIER = {"user": "perm", "assistant": "temp", "tool": "mid"}


def _initial_tier(source):
    """按来源取节点初始分级；未知来源回退 temp。"""
    return _INITIAL_TIER.get(source or "", "temp")


def upsert_node(identity, fields, created_at=None):
    """按 msg_id 幂等写入节点；已存在则更新 blocks 与 parent_id，不动蒸馏字段。

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
    # 初始分级按来源设定（user→perm / assistant→temp / tool→mid）
    tier = _initial_tier(fields.get("source"))
    cur = conn.execute(
        "INSERT INTO nodes (msg_id, conv_id, site_key, parent_id, source, role, name, blocks, tier, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(msg_id) DO UPDATE SET blocks=excluded.blocks, parent_id=excluded.parent_id",
        (msg_id, conv_id, site_key, parent_id, fields.get("source"),
         fields.get("role", ""), fields.get("name", ""), blocks_json, tier, ts),
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


def bulk_set_strength_tier(pairs):
    """批量写入「强度 + 分级」（全量衰减重算用）。

    逐条 UPDATE 会让 4000+ 节点产生 4000+ 条语句、每条都要过一遍 SQL 追踪回调，
    实测是全量重算的主要耗时来源（约 1ms/条）。改用 executemany 一次提交一批，
    把语句级开销摊薄，是重算提速的关键。
    @param pairs [(node_id, strength, tier), ...] 三元组列表
    """
    if not pairs:
        return
    conn = get_conn()
    conn.executemany(
        "UPDATE nodes SET strength=?, tier=? WHERE id=?",
        [(float(s), t, nid) for (nid, s, t) in pairs],
    )
    maybe_commit(conn)


def soft_delete(node_id):
    """软删除：置 deleted=1，节点保留、树不断裂。"""
    conn = get_conn()
    conn.execute("UPDATE nodes SET deleted=1 WHERE id=?", (node_id,))
    maybe_commit(conn)


def _delete_node_related(conn, node_id):
    """删除单个节点及其全部关联数据（须在批量模式或调用方控制提交）。

    关联数据覆盖所有引用该节点的表，避免留下孤儿死数据：
      - edges：src/dst 指向它的边；
      - cards：挂在它名下的卡片；
      - revision_log：它的修订留痕（节点已删，留痕无意义）；
      - notes：引用它的每日记忆/错题本条目。
    @return 删除的节点行数（0 表示节点不存在）
    """
    conn.execute("DELETE FROM edges WHERE src_node=? OR dst_node=?", (node_id, node_id))
    conn.execute("DELETE FROM cards WHERE node_id=?", (node_id,))
    conn.execute("DELETE FROM revision_log WHERE node_id=?", (node_id,))
    conn.execute("DELETE FROM notes WHERE node_id=?", (node_id,))
    return conn.execute("DELETE FROM nodes WHERE id=?", (node_id,)).rowcount


def hard_delete(node_id):
    """硬删除：真删节点行及其全部关联数据，不可恢复。

    调用方须先做二次确认（前端弹框）。
    @return 被删除的节点数（0 表示节点不存在）
    """
    conn = get_conn()
    n = _delete_node_related(conn, node_id)
    maybe_commit(conn)
    return n


def hard_delete_many(node_ids):
    """批量硬删一批节点（连同它们的边与卡片）。

    供图谱的「清理下级节点 / 清理旧节点」使用。
    @param node_ids 节点 id 列表
    @return 实际删除的节点数
    """
    if not node_ids:
        return 0
    conn = get_conn()
    total = 0
    for nid in node_ids:
        total += _delete_node_related(conn, nid)
    maybe_commit(conn)
    return total


def descendant_ids(root_id, sources=None, stop_at_user=False):
    """取某节点的全部后代 id（沿 parent_id 向下），不含自身。

    @param root_id      根节点 id
    @param sources      仅取这些来源的后代；None 表示不限
    @param stop_at_user 遇到嵌套的用户发言时是否停止下钻。
        用户的每一轮发言都是一条独立对话；清理某用户节点的下挂内容时，
        若其子树里还嵌套着另一条用户发言，那条发言的 AI/工具节点属于它自己，
        不该被这一轮的清理牵连。置 True 即遇到用户节点不下钻（防止过度清理）。
    @return 后代 id 列表
    """
    conn = get_conn()
    seen = set()
    frontier = [root_id]
    out = []
    while frontier:
        placeholders = ",".join("?" for _ in frontier)
        sql = "SELECT id, source FROM nodes WHERE parent_id IN (%s) AND deleted=0" % placeholders
        rows = conn.execute(sql, list(frontier)).fetchall()
        frontier = []
        for r in rows:
            nid = r["id"]
            if nid in seen:
                continue
            seen.add(nid)
            if sources is None or r["source"] in sources:
                out.append(nid)
            # 遇嵌套用户发言：不下钻，避免牵连它自己那一轮的对话内容
            if stop_at_user and r["source"] == "user":
                continue
            frontier.append(nid)
    return out


def ids_older_than(node_id, conv_id, site_key=None):
    """取「同一会话内」创建时间早于某节点的节点 id（不含自身）。

    以目标节点的 created_at 为界；同一时刻用 id 兜底，保证「之前」稳定。

    会话隔离是硬约束：所有会话的节点共用同一条时间轴，若只按时间筛，
    会跨会话删除其它会话里更早的节点（造成不可恢复的越界删除）。
    故这里强制按 conv_id 过滤；site_key 传了就一并限定站点。
    @param node_id  参照节点 id
    @param conv_id  会话 id（必填，隔离边界）
    @param site_key 站点标识；None 表示不限站点
    @return 同会话内更早的节点 id 列表
    """
    conn = get_conn()
    row = conn.execute("SELECT created_at FROM nodes WHERE id=?", (node_id,)).fetchone()
    if not row:
        return []
    ts = row["created_at"] or 0
    # 会话过滤：先限定同一 conv_id（（可选）同一 site_key），再按时间取更早的
    sql = ("SELECT id FROM nodes WHERE deleted=0 AND conv_id=? "
           "AND (created_at < ? OR (created_at = ? AND id < ?))")
    args = [conv_id, ts, ts, node_id]
    if site_key is not None:
        sql = ("SELECT id FROM nodes WHERE deleted=0 AND conv_id=? AND site_key=? "
               "AND (created_at < ? OR (created_at = ? AND id < ?))")
        args = [conv_id, site_key, ts, ts, node_id]
    rows = conn.execute(sql, args).fetchall()
    return [r["id"] for r in rows]


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
