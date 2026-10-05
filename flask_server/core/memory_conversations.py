"""AI 工具调用镜像插件 —— 记忆系统：会话级读写

职责：把消息树整体存进库、整体取出来，供前端「全部走后端查询」。

映射关系（前端 msgTree ↔ 库表）：
  - msgTree 的每个 key '父id-子id' → 一条 parent_child 边；
  - msgTree 的每个 value（节点）→ 一个 nodes 行；
  - 节点的 cards → cards 表；
  - 会话级 visibleKeys / branchKeys / externalCards / orphanSlice → conversations 表。

关键约定：
  - msg_id 是前端消息指纹，是节点在前端与后端之间的稳定标识；
  - 同一父节点有 ≥2 条子边时，额外标一条 branch 边（版本分叉）；
  - 取会话时按边重建 msgTree，node id 用前端 msg_id 还原为 key。

依赖：memory_db、memory_nodes、memory_edges、memory_cards、json、time
"""
import json
import time

from memory_db import get_conn, maybe_commit, begin_batch, end_batch
from memory_nodes import upsert_node, get_by_msg_id, set_parent
from memory_edges import add_edge
from memory_cards import upsert_card
import app_log


def _now():
    """当前 Unix 时间戳（秒）。"""
    return int(time.time())


def save_conversation(conv_id, site_key, conv):
    """把前端会话对象整体存入库。

    @param conv 前端会话对象 { title, page_url, msgTree, visibleKeys, ... }
    @return 写入的节点数
    """
    # 计时放在取连接之前：日志耗时为真实端到端耗时（含取连接）
    _t0 = time.time()
    conn = get_conn()
    # 进入批量模式：本轮所有写操作攒到最后统一提交，
    # 避免「每节点多次提交」造成的频繁抢写锁。
    begin_batch()
    result = None
    try:
        result = _save_conversation_inner(conn, conv_id, site_key, conv, _t0)
    finally:
        # 无论成败都退出批量并提交，保证数据落地、不长时间占锁
        end_batch(conn)
    # 计时放在提交之后：日志耗时含「写入 + 最终提交」，才是真实端到端耗时
    ms = (time.time() - _t0) * 1000.0
    app_log.info("[mem][save] conv=%s 节点=%d 总耗时=%.1fms" % (conv_id, result, ms))
    return result


def _save_conversation_inner(conn, conv_id, site_key, conv, _t0):
    """保存会话的实际写入逻辑（在批量提交包裹内执行）。"""
    tree = (conv.get("msgTree") or {})
    # 预扫：建 msg_id → 节点 映射，并统计每个父节点的子边数（判 branch）
    node_by_msg = {}    # msg_id → 前端节点对象
    child_count = {}    # 父 msg_id → 子边数
    edges_raw = []      # [(父msg_id, 子msg_id)]
    for key, node in tree.items():
        if "-" not in key or not node:
            continue
        pid, cid = key.split("-", 1)
        node_by_msg[cid] = node
        child_count[pid] = child_count.get(pid, 0) + 1
        edges_raw.append((pid, cid))
    # 第一遍：建全部节点（此时父关系未知，parent_id 默认 0）
    id_map = {}         # msg_id → 库 node id
    for mid, node in node_by_msg.items():
        id_map[mid] = upsert_node(
            {"msg_id": mid, "conv_id": conv_id, "site_key": site_key},
            {"source": node.get("source") or _infer_source(node),
             "role": node.get("role", ""), "name": node.get("name", ""),
             "blocks": node.get("blocks") or []},
        )
    # 第二遍：回填父子关系、建边、写卡片
    n_written = 0
    for pid, cid in edges_raw:
        nid = id_map.get(cid)
        if nid is None:
            continue
        src_id = id_map.get(pid, 0) if pid != "0" else 0
        # 回填父节点：非哨兵根才回填
        if src_id:
            set_parent(nid, src_id)
            add_edge(src_id, nid, "parent_child")
            if child_count.get(pid, 0) >= 2:
                add_edge(src_id, nid, "branch")
        n_written += 1
        # 写卡片
        for bid, card in (node_by_msg.get(cid, {}).get("cards") or {}).items():
            if card:
                upsert_card(nid, bid, card.get("tool"), card.get("status"),
                            card.get("result"), card.get("finishedAt"))
    # 2) 写会话级元数据
    conn.execute(
        "INSERT INTO conversations (conv_id, site_key, title, page_url, visible_keys,"
        " branch_keys, external_cards, orphan_slice, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)"
        " ON CONFLICT(conv_id, site_key) DO UPDATE SET"
        " title=excluded.title, page_url=excluded.page_url,"
        " visible_keys=excluded.visible_keys, branch_keys=excluded.branch_keys,"
        " external_cards=excluded.external_cards, orphan_slice=excluded.orphan_slice,"
        " updated_at=excluded.updated_at",
        (conv_id, site_key, conv.get("title", ""), conv.get("page_url", ""),
         json.dumps(conv.get("visibleKeys") or [], ensure_ascii=False),
         json.dumps(conv.get("branchKeys") or [], ensure_ascii=False),
         json.dumps(conv.get("externalCards") or [], ensure_ascii=False),
         json.dumps(conv.get("orphanSlice") or [], ensure_ascii=False),
         _now()),
    )
    maybe_commit(conn)
    return n_written


def load_conversation(conv_id, site_key):
    """从库重建前端会话对象；不存在返回 None。"""
    conn = get_conn()
    meta = conn.execute(
        "SELECT * FROM conversations WHERE conv_id=? AND site_key=?", (conv_id, site_key)
    ).fetchone()
    # 取该会话全部节点
    rows = conn.execute(
        "SELECT * FROM nodes WHERE conv_id=? AND site_key=? ORDER BY created_at, id",
        (conv_id, site_key),
    ).fetchall()
    if not rows and not meta:
        return None
    # 重建 msgTree：key = '父msg_id-子msg_id'
    tree = {}
    id_to_msg = {}
    for r in rows:
        id_to_msg[r["id"]] = r["msg_id"]
    for r in rows:
        pid_db = r["parent_id"] or 0
        pid_msg = id_to_msg.get(pid_db, "0")
        key = pid_msg + "-" + r["msg_id"]
        node = {
            "role": r["role"], "name": r["name"],
            "blocks": _loads(r["blocks"], []),
            "source": r["source"], "deleted": bool(r["deleted"]), "cards": {},
        }
        tree[key] = node
    # 挂卡片
    for r in rows:
        pid_db = r["parent_id"] or 0
        pid_msg = id_to_msg.get(pid_db, "0")
        key = pid_msg + "-" + r["msg_id"]
        for c in conn.execute("SELECT * FROM cards WHERE node_id=?", (r["id"],)).fetchall():
            if key in tree:
                tree[key]["cards"][c["block_id"]] = {
                    "tool": c["tool"], "status": c["status"],
                    "result": _loads(c["result"], None), "finishedAt": c["finished_at"],
                }
    return {
        "title": (meta["title"] if meta else "") or "",
        "page_url": (meta["page_url"] if meta else "") or "",
        "msgTree": tree,
        "visibleKeys": _loads(meta["visible_keys"], []) if meta else [],
        "branchKeys": _loads(meta["branch_keys"], []) if meta else [],
        "externalCards": _loads(meta["external_cards"], []) if meta else [],
        "orphanSlice": _loads(meta["orphan_slice"], []) if meta else [],
    }


def list_conversations(site_key=None):
    """列出会话摘要（不切会话也能看列表）。"""
    conn = get_conn()
    if site_key:
        rows = conn.execute(
            "SELECT conv_id, site_key, title, page_url, updated_at FROM conversations"
            " WHERE site_key=? ORDER BY updated_at DESC", (site_key,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT conv_id, site_key, title, page_url, updated_at FROM conversations"
            " ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_conversation(conv_id, site_key):
    """删除一个会话的全部节点、边、卡片与元数据。"""
    conn = get_conn()
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM nodes WHERE conv_id=? AND site_key=?", (conv_id, site_key)
    ).fetchall()]
    for nid in ids:
        conn.execute("DELETE FROM edges WHERE src_node=? OR dst_node=?", (nid, nid))
        conn.execute("DELETE FROM cards WHERE node_id=?", (nid,))
    conn.execute("DELETE FROM nodes WHERE conv_id=? AND site_key=?", (conv_id, site_key))
    conn.execute("DELETE FROM conversations WHERE conv_id=? AND site_key=?", (conv_id, site_key))
    maybe_commit(conn)
    return len(ids)


def _find_key_by_child(tree, child_id):
    """在 msgTree 里按子 id 找到其所在 key；找不到返回 None。"""
    for k in tree:
        if "-" in k and k.split("-", 1)[1] == child_id:
            return k
    return None


def _infer_source(node):
    """从节点推断来源（user / assistant / tool）。"""
    role = (node or {}).get("role", "")
    if role == "user":
        return "user"
    if role == "assistant":
        return "assistant"
    return "tool" if role == "tool" else "assistant"


def _loads(text, default):
    """安全反序列化 JSON 文本。"""
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default
