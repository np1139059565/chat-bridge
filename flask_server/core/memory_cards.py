"""AI 工具调用镜像插件 —— 记忆系统：卡片表读写

职责：cards 表的增删改查，记录消息节点上挂着的工具卡片（执行状态与结果）。
卡片是「工具调用」的落点，蒸馏时 tool 来源节点的精华主要来自这里。

依赖：memory_db（连接）、json
"""
import json

from memory_db import get_conn


def upsert_card(node_id, block_id, tool=None, status=None, result=None, finished_at=None):
    """写入或更新一张卡片。

    唯一性由 (node_id, block_id) 决定——同一消息的同一代码块只对应一张卡。
    @return 卡片 id
    """
    conn = get_conn()
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    row = conn.execute(
        "SELECT id FROM cards WHERE node_id=? AND block_id=?", (node_id, block_id)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE cards SET tool=?, status=?, result=?, finished_at=? WHERE id=?",
            (tool, status, result_json, finished_at, row["id"]),
        )
        conn.commit()
        return row["id"]
    cur = conn.execute(
        "INSERT INTO cards (node_id, block_id, tool, status, result, finished_at)"
        " VALUES (?,?,?,?,?,?)",
        (node_id, block_id, tool, status, result_json, finished_at),
    )
    conn.commit()
    return cur.lastrowid


def list_by_node(node_id):
    """取某节点下的全部卡片。"""
    rows = get_conn().execute("SELECT * FROM cards WHERE node_id=?", (node_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["result"] = json.loads(d.get("result") or "null")
        except Exception:
            pass
        out.append(d)
    return out


def cards_map(node_id):
    """取某节点的卡片字典 {block_id: 卡片}，供会话整体返回时嵌入节点。"""
    out = {}
    for c in list_by_node(node_id):
        out[c["block_id"]] = c
    return out
