"""AI 工具调用镜像插件 —— 记忆系统：卡片表读写

职责：cards 表的增删改查，记录消息节点上挂着的工具卡片（执行状态与结果）。
卡片是「工具调用」的落点，蒸馏时 tool 来源节点的精华主要来自这里。

依赖：memory_db（连接）、json
"""
import json

from memory_db import get_conn, maybe_commit


# 卡片可写字段：与 cards 表列一一对应。集中在此，新增字段只改这一处。
CARD_FIELDS = ("tool", "status", "result", "finished_at",
               "is_tool", "msg_id", "parameters", "executed")


def upsert_card(node_id, block_id, fields=None, **kwargs):
    """写入或更新一张卡片。

    唯一性由 (node_id, block_id) 决定——同一消息的同一代码块只对应一张卡。

    入参分两段：定位键（node_id, block_id）与字段值。字段值既可放在
    fields 字典里，也可按关键字直接传入（两者会合并，fields 优先）。
    这样字段增至八项时函数签名仍是三项，不必每加一个字段就改签名。

    is_tool / msg_id / parameters / executed 是前端渲染与重跑所必需的：
    没有 is_tool 就渲染成普通代码块，没有 msg_id 与 parameters 就拼不出
    执行签名、也无法重新执行。

    @param fields 字段字典，键见 CARD_FIELDS
    @param kwargs 按关键字传入的字段值，与 fields 合并
    @return 卡片 id
    """
    # 合并两路入参：先取关键字，再用 fields 覆盖，保证显式字典优先
    values = {k: kwargs.get(k) for k in CARD_FIELDS}
    if fields:
        values.update({k: v for k, v in fields.items() if k in CARD_FIELDS})
    tool = values["tool"]
    status = values["status"]
    result = values["result"]
    finished_at = values["finished_at"]
    is_tool = values["is_tool"]
    msg_id = values["msg_id"]
    parameters = values["parameters"]
    executed = values["executed"]
    conn = get_conn()
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    # 参数是字典，存 JSON 文本；None 保持为 NULL，与「空字典」区分开
    params_json = json.dumps(parameters, ensure_ascii=False) if parameters is not None else None
    # 布尔存整数：SQLite 无原生布尔类型
    is_tool_int = None if is_tool is None else (1 if is_tool else 0)
    executed_int = None if executed is None else (1 if executed else 0)
    row = conn.execute(
        "SELECT id FROM cards WHERE node_id=? AND block_id=?", (node_id, block_id)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE cards SET tool=?, status=?, result=?, finished_at=?,"
            " is_tool=?, msg_id=?, parameters=?, executed=? WHERE id=?",
            (tool, status, result_json, finished_at,
             is_tool_int, msg_id, params_json, executed_int, row["id"]),
        )
        maybe_commit(conn)
        return row["id"]
    cur = conn.execute(
        "INSERT INTO cards (node_id, block_id, tool, status, result, finished_at,"
        " is_tool, msg_id, parameters, executed) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (node_id, block_id, tool, status, result_json, finished_at,
         is_tool_int, msg_id, params_json, executed_int),
    )
    maybe_commit(conn)
    return cur.lastrowid


def _row_to_card(r):
    """把一行卡片记录转成前端可直接使用的卡片对象。

    列名用下划线（SQLite 习惯），前端用驼峰，此处统一转换。
    JSON 文本列反序列化；布尔列由整数还原。

    @param r 数据库行
    @returns 卡片字典
    """
    d = dict(r)
    # result：JSON 反序列化，NULL 还原为 None
    try:
        d["result"] = json.loads(d.get("result") or "null")
    except Exception:
        pass
    # parameters：同上
    try:
        d["parameters"] = json.loads(d["parameters"]) if d.get("parameters") else {}
    except Exception:
        d["parameters"] = {}
    # 布尔列：整数还原；NULL 视为 False
    d["isTool"] = bool(d.pop("is_tool", 0))
    d["executed"] = bool(d.pop("executed", 0))
    # msg_id → msgId
    d["msgId"] = d.pop("msg_id", "") or ""
    # finishedAt：前端用驼峰
    d["finishedAt"] = d.pop("finished_at", None)
    return d


def list_by_node(node_id):
    """取某节点下的全部卡片，字段名已转为前端使用的驼峰格式。"""
    rows = get_conn().execute("SELECT * FROM cards WHERE node_id=?", (node_id,)).fetchall()
    return [_row_to_card(r) for r in rows]


def cards_map(node_id):
    """取某节点的卡片字典 {block_id: 卡片}，供会话整体返回时嵌入节点。"""
    out = {}
    for c in list_by_node(node_id):
        out[c["block_id"]] = c
    return out
