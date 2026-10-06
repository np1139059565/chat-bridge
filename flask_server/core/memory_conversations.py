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

写入模型（两条，互相独立）：
  1. 异步化：save_conversation 只把请求投入后台队列就立即返回，
     真正的写库由唯一后台线程串行执行。目的是让保存操作绝不占用
     Flask 请求线程、不长时间握数据库写锁、不拖慢其它界面接口请求。
  2. 增量：每个节点按「内容签名」比对，未变化的节点跳过写库；
     只写本轮新增或内容变化的节点，缩短提交时间、减少写锁占用。

依赖：memory_db、memory_nodes、memory_edges、memory_cards、json、time
"""
import collections
import hashlib
import json
import threading
import time

from memory_db import get_conn, maybe_commit, begin_batch, end_batch
from memory_nodes import upsert_node, get_by_msg_id, set_parent
from memory_edges import add_edge
from memory_cards import upsert_card
import app_log


def _now():
    """当前 Unix 时间戳（秒）。"""
    return int(time.time())


# ---------------- 异步保存队列（改造 A：不占用请求线程） ----------------
# 待保存：{(conv_id, site_key): conv}，配合 _pending_order 记录入队顺序。
# 采用「最新覆盖」语义：同一会话若在尚未处理前又有新保存，后者覆盖前者，
# 避免对同一会话做无谓的重复全量写。
_pending = {}
_pending_order = collections.deque()
_queue_lock = threading.Lock()
_worker_running = False

# 增量签名缓存（改造 B）：{(conv_id, site_key, msg_id): (内容签名, 库节点id)}
# 只存内存，进程重启后首次保存自然全量；会话删除时清除对应项。
_saved_sig = {}
_sig_lock = threading.Lock()


def save_conversation(conv_id, site_key, conv):
    """把会话保存请求投入后台队列，立即返回（不占请求线程）。

    真正的写库由唯一后台工作线程串行执行。这样保存不会在 Flask 请求线程里
    跑全量重写、长时间占据数据库写锁、拖慢其它界面接口请求。
    写入为最终一致：极端情况下（进程崩溃）可能丢失尚未落库的最后一次改动。
    @return None（不等待写入完成）
    """
    key = (conv_id, site_key)
    with _queue_lock:
        if key not in _pending:
            _pending_order.append(key)
        _pending[key] = conv
    _ensure_worker()


def _ensure_worker():
    """确保后台保存线程在跑（幂等：重复调用只启动一个）。"""
    global _worker_running
    with _queue_lock:
        if _worker_running:
            return
        _worker_running = True
    threading.Thread(target=_worker, daemon=True).start()


def _worker():
    """后台保存线程：串行处理队列，处理完一个会话再取下一个。

    每个会话完成后：先落库，再触发该会话的异步蒸馏（保证蒸馏读得到刚写的节点）。
    队列空时退出并复位标志，下次入队会再次拉起，不空转占资源。
    """
    global _worker_running
    while True:
        with _queue_lock:
            if not _pending_order:
                _worker_running = False
                return
            key = _pending_order.popleft()
            conv = _pending.pop(key, None)
        if conv is None:
            continue
        conv_id, site_key = key
        try:
            _save_conversation_sync(conv_id, site_key, conv)
            _distill_new(conv_id)
        except Exception as e:
            # 单会话失败不中断队列
            app_log.warn("[mem][save] 后台保存失败 conv=%s: %s" % (conv_id, e))


def _distill_new(conv_id):
    """对某会话尚未蒸馏的节点触发异步蒸馏。

    在后台保存完成后调用，保证此时节点已落库。只按 conv_id 取节点，
    不强制 site_key 匹配：站点切换时序不一致时强匹配会查出 0 个节点、
    蒸馏永不触发。
    @param conv_id 会话 id
    """
    try:
        import memory_nodes
        import memory_distill
        nodes = memory_nodes.list_by_conv(conv_id, None)
        pending = [n["id"] for n in nodes if not n.get("essence")]
        if pending:
            memory_distill.distill_async(pending)
    except Exception as e:
        app_log.warn("[mem][save] 触发蒸馏失败 conv=%s: %s" % (conv_id, e))


def _node_sig(node, parent_msg):
    """计算节点内容签名，用于增量比对。

    参与签名的字段：blocks（正文）、cards（卡片）、父消息指纹。
    任一变化即视为需重写。
    @return md5 十六进制字符串
    """
    payload = json.dumps({
        "b": node.get("blocks") or [],
        "p": parent_msg or "",
        "c": node.get("cards") or {},
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _save_conversation_sync(conv_id, site_key, conv):
    """同步把会话写库（仅供后台线程调用）。

    @param conv 前端会话对象 { title, page_url, msgTree, visibleKeys, ... }
    @return 实际写入的节点数
    """
    # 计时放在取连接之前：日志耗时为真实端到端耗时（含取连接）。
    # 用 perf_counter（高精度单调时钟）：Windows 上 time.time() 精度约 15ms，
    # 会把毫秒级耗时测成 0，用 perf_counter 才能如实反映。
    _t0 = time.perf_counter()
    conn = get_conn()
    # 进入批量模式：本轮所有写操作攒到最后统一提交，
    # 避免「每节点多次提交」造成的频繁抢写锁。
    begin_batch()
    result = None
    try:
        result = _save_conversation_inner(conn, conv_id, site_key, conv)
    finally:
        # 无论成败都退出批量并提交，保证数据落地、不长时间占锁
        end_batch(conn)
    # 计时放在提交之后：日志耗时含「写入 + 最终提交」，才是真实端到端耗时。
    ms = (time.perf_counter() - _t0) * 1000.0
    app_log.info("[mem][save] conv=%s 写入=%d 总耗时=%.1fms" % (conv_id, result, ms))
    return result


def _save_conversation_inner(conn, conv_id, site_key, conv):
    """保存会话的实际写入逻辑（在批量提交包裹内执行）。

    增量策略：逐节点比对内容签名，未变化者跳过节点写库及其边、卡片写入，
    只写新增或内容变化的节点，从而缩短提交时间、减少写锁占用。
    @return 本轮实际写入（新增或变化）的节点数
    """
    tree = (conv.get("msgTree") or {})
    # 预扫：建 msg_id → 节点 映射，记录父节点指纹，统计子边数（判 branch）
    node_by_msg = {}    # msg_id → 前端节点对象
    parent_of = {}      # 子 msg_id → 父 msg_id
    child_count = {}    # 父 msg_id → 子边数
    edges_raw = []      # [(父msg_id, 子msg_id)]
    for key, node in tree.items():
        if "-" not in key or not node:
            continue
        pid, cid = key.split("-", 1)
        node_by_msg[cid] = node
        parent_of[cid] = pid
        child_count[pid] = child_count.get(pid, 0) + 1
        edges_raw.append((pid, cid))
    # 第一遍：写节点；未变化的复用缓存中的库 id，不写库
    id_map = {}         # msg_id → 库 node id
    changed = set()     # 本轮内容变化、需重写边与卡片的 msg_id
    for mid, node in node_by_msg.items():
        sig = _node_sig(node, parent_of.get(mid))
        cache_key = (conv_id, site_key, mid)
        with _sig_lock:
            cached = _saved_sig.get(cache_key)
        if cached and cached[0] == sig:
            # 内容未变：直接复用已存库 id，跳过写库
            id_map[mid] = cached[1]
            continue
        nid = upsert_node(
            {"msg_id": mid, "conv_id": conv_id, "site_key": site_key},
            {"source": node.get("source") or _infer_source(node),
             "role": node.get("role", ""), "name": node.get("name", ""),
             "blocks": node.get("blocks") or []},
        )
        id_map[mid] = nid
        changed.add(mid)
        with _sig_lock:
            _saved_sig[cache_key] = (sig, nid)
    # 第二遍：只对内容变化的节点回填父子关系、建边、写卡片
    n_written = 0
    for pid, cid in edges_raw:
        if cid not in changed:
            continue
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
    """删除一个会话的全部节点、边、卡片、元数据与增量签名缓存。"""
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
    # 清除该会话的增量签名缓存，避免删除后残留导致误跳过
    with _sig_lock:
        for k in [k for k in _saved_sig if k[0] == conv_id and k[1] == site_key]:
            del _saved_sig[k]
    return len(ids)


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
