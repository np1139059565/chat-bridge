"""AI 工具调用镜像插件 —— 记忆系统：会话级读取

职责：把库里存的节点、边、卡片与会话元数据重建为前端可用的会话对象。

为何独立成模块：
- 读写两条链路关注点不同，写入侧关心增量比对与批量提交，读取侧关心
  重建顺序与字段还原，混在一个文件里既超长也难改；
- 入口函数 load_conversation / list_conversations 由 memory_conversations
  重导出，调用方无需感知拆分。

重建口径（与写入侧对称）：
  - 每条 parent_child 边还原为 msgTree 的键「父msg_id-子msg_id」；
  - 节点的 cards 按 block_id 挂回节点；
  - 会话级 visibleKeys / branchKeys / externalCards / orphanSlice /
    executedSigs 从 conversations 行还原。

依赖：memory_db（连接）、memory_cards（卡片字段转换）、json_utils
"""
from memory_db import get_conn
import memory_cards
import json_utils


def _key_child(key):
    """从会话引用键里取出「子消息指纹」。

    会话的 visible_keys / branch_keys 存的是树键「父指纹-子指纹」
    （根节点为「0-子指纹」），引用的是子节点。判定悬空须取子段比对，
    不可拿整条树键去比对 msg_id（否则会全部误判为悬空）。
    @param key 树键字符串
    @return 子消息指纹
    """
    return key.split("-", 1)[1] if "-" in key else key


def _loads(text, default):
    """安全反序列化 JSON 文本（委托公共函数，保留本名以兼容既有调用点）。"""
    return json_utils.safe_json_loads(text, default)


def _conv_key(id_to_msg, r):
    """按节点行与其父节点拼出前端 msgTree 的 key：'父msg_id-子msg_id'。"""
    pid_db = r["parent_id"] or 0
    pid_msg = id_to_msg.get(pid_db, "0")
    return pid_msg + "-" + r["msg_id"]


def _build_tree(rows):
    """由节点行重建 msgTree（key = '父msg_id-子msg_id'），卡片位先留空。"""
    tree = {}
    id_to_msg = {r["id"]: r["msg_id"] for r in rows}
    for r in rows:
        tree[_conv_key(id_to_msg, r)] = {
            "role": r["role"], "name": r["name"],
            "blocks": _loads(r["blocks"], []),
            "source": r["source"], "deleted": bool(r["deleted"]), "cards": {},
        }
    return tree, id_to_msg


def _attach_cards(conn, rows, tree, id_to_msg):
    """把各节点的卡片挂到 msgTree 对应节点上。"""
    for r in rows:
        key = _conv_key(id_to_msg, r)
        if key not in tree:
            continue
        for c in conn.execute("SELECT * FROM cards WHERE node_id=?", (r["id"],)).fetchall():
            # 直接复用 memory_cards 的字段转换，避免此处再维护一份字段清单：
            # 两处清单不同步正是「库里存了、读时却没还原」的根源。
            card = memory_cards._row_to_card(c)
            tree[key]["cards"][c["block_id"]] = card


def _conv_meta_fields(meta):
    """从 conversations 行取出会话级字段（meta 为空时全用兜底值）。"""
    if not meta:
        return {"title": "", "page_url": "", "visibleKeys": [], "branchKeys": [],
                "externalCards": [], "orphanSlice": [], "executedSigs": {}}
    # 旧库可能还没迁出该列：用 keys() 判断，缺列时返回空字典而非报错
    sigs = _loads(meta["executed_sigs"], {}) if "executed_sigs" in meta.keys() else {}
    return {
        "title": meta["title"] or "",
        "page_url": meta["page_url"] or "",
        "visibleKeys": _loads(meta["visible_keys"], []),
        "branchKeys": _loads(meta["branch_keys"], []),
        "externalCards": _loads(meta["external_cards"], []),
        "orphanSlice": _loads(meta["orphan_slice"], []),
        "executedSigs": sigs,   # 已执行签名库：刷新后据此恢复卡片状态
    }


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
    tree, id_to_msg = _build_tree(rows)
    _attach_cards(conn, rows, tree, id_to_msg)
    result = _conv_meta_fields(meta)
    result["msgTree"] = tree
    return result


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
