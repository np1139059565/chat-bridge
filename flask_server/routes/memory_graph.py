"""AI 工具调用镜像插件 —— 记忆系统：HTTP 接口

职责：暴露记忆系统的全部 HTTP 接口（方案第七节接口清单），
并在应用启动时触发内存加载。同时接管原 memory.py 的目录指纹接口（2B）。

接口分组：读写 / 检索 / 分级 / 事件 / 会话 / 可视化 / 加载。

依赖：flask、memory_* 各模块、paths、hashlib
"""
import hashlib

from flask import Blueprint, jsonify, request, send_file

import paths
import memory_nodes
import memory_edges
import memory_cards
import memory_distill
import memory_decay
import memory_events
import memory_search
import memory_loader
import memory_conversations

bp = Blueprint("memory_graph", __name__)


def _ok(**kw):
    """统一成功响应。"""
    payload = {"success": True}
    payload.update(kw)
    return jsonify(payload)


def _err(msg):
    """统一失败响应。"""
    return jsonify({"success": False, "error": msg})


# ---------------- 读写层 ----------------

@bp.route("/memory/node/<int:node_id>", methods=["GET"])
def node_get(node_id):
    """按 id 取节点。"""
    node = memory_nodes.get_node(node_id)
    if not node:
        return _err("节点不存在")
    node["cards"] = memory_cards.cards_map(node_id)
    return _ok(node=node)


@bp.route("/memory/list", methods=["GET"])
def node_list():
    """列举某会话的节点。"""
    conv_id = request.args.get("conv_id", "")
    site_key = request.args.get("site_key", "")
    if not conv_id:
        return _err("缺少 conv_id")
    return _ok(nodes=memory_nodes.list_by_conv(conv_id, site_key or None))


@bp.route("/memory/delete", methods=["POST"])
def node_delete():
    """软删除一个节点。"""
    data = request.get_json(force=True) or {}
    nid = data.get("node_id")
    if not nid:
        return _err("缺少 node_id")
    memory_nodes.soft_delete(nid)
    return _ok()


# ---------------- 会话层（前端走后端查询） ----------------

@bp.route("/memory/conversation", methods=["GET"])
def conversation_get():
    """取整个会话的消息树。"""
    conv_id = request.args.get("conv_id", "")
    site_key = request.args.get("site_key", "")
    if not conv_id:
        return _err("缺少 conv_id")
    conv = memory_conversations.load_conversation(conv_id, site_key)
    if conv is None:
        return _ok(conv=None)
    return _ok(conv=conv)


@bp.route("/memory/conversation", methods=["POST"])
def conversation_put():
    """写整个会话的消息树。"""
    data = request.get_json(force=True) or {}
    conv_id = data.get("conv_id")
    site_key = data.get("site_key", "")
    conv = data.get("conv") or {}
    if not conv_id:
        return _err("缺少 conv_id")
    n = memory_conversations.save_conversation(conv_id, site_key, conv)
    # 落库后触发异步蒸馏（决策 3B）
    _distill_new(conv_id, site_key)
    memory_loader.invalidate()
    return _ok(written=n)


@bp.route("/memory/conversations", methods=["GET"])
def conversation_list():
    """列出会话摘要。"""
    site_key = request.args.get("site_key", "")
    return _ok(conversations=memory_conversations.list_conversations(site_key or None))


@bp.route("/memory/conversation/delete", methods=["POST"])
def conversation_delete():
    """删除一个会话。"""
    data = request.get_json(force=True) or {}
    n = memory_conversations.delete_conversation(data.get("conv_id", ""), data.get("site_key", ""))
    return _ok(deleted=n)


def _distill_new(conv_id, site_key):
    """对尚未蒸馏的节点异步蒸馏（决策 3B）。"""
    nodes = memory_nodes.list_by_conv(conv_id, site_key or None)
    pending = [n["id"] for n in nodes if not n.get("essence")]
    if pending:
        memory_distill.distill_async(pending)


# ---------------- 检索层（双接口） ----------------

@bp.route("/memory/plan", methods=["POST"])
def plan_submit():
    """接口 A：暂存计划原文。"""
    data = request.get_json(force=True) or {}
    pid = memory_search.plan_submit(data.get("plan_text", ""), data.get("session_id", ""))
    return _ok(plan_id=pid)


@bp.route("/memory/search", methods=["POST"])
def search():
    """接口 B：验证式关联搜索。"""
    data = request.get_json(force=True) or {}
    result = memory_search.memory_search(
        data.get("plan_id", ""), data.get("keywords") or [],
        focus=data.get("focus", "relevance"), top_k=int(data.get("top_k", 10)),
    )
    # 命中后强化突触（方案 5.2）
    hit_ids = [h["node_id"] for h in result.get("hits", [])]
    if len(hit_ids) >= 2:
        memory_events.reinforce_by_hits(hit_ids)
    return _ok(**result)


# ---------------- 分级层 ----------------

@bp.route("/memory/decay/run", methods=["POST"])
def decay_run():
    """触发一次衰减计算与升降级。"""
    n, up, down = memory_decay.recompute_all()
    return _ok(processed=n, upgraded=up, downgraded=down)


# ---------------- 事件层 ----------------

@bp.route("/memory/events", methods=["GET"])
def events_list():
    """列出事件簇（用户发言按关键词聚类）。"""
    return _ok(events=memory_events.cluster_events())


@bp.route("/memory/event/history", methods=["GET"])
def event_history():
    """取某事件根节点的演化史（修订日志）。"""
    root_id = request.args.get("root_id", type=int)
    if not root_id:
        return _err("缺少 root_id")
    return _ok(history=memory_events.event_history(root_id))


# ---------------- 可视化 ----------------

@bp.route("/memory/graph", methods=["GET"])
def graph_export():
    """导出图数据（节点 + 边），供 D3 渲染。"""
    nodes = []
    for n in memory_nodes.list_by_conv(request.args.get("conv_id", ""), request.args.get("site_key") or None):
        nodes.append({
            "id": n["id"], "source": n["source"], "tier": n.get("tier"),
            "strength": n.get("strength"), "essence": n.get("essence"),
            "keywords": n.get("keywords"),
        })
    return _ok(nodes=nodes, edges=memory_edges.all_edges())


# ---------------- 加载层 ----------------

@bp.route("/memory/load", methods=["POST"])
def load():
    """触发一次内存加载。"""
    return _ok(**memory_loader.load_all())


# ---------------- 目录指纹（并入，原 memory.py 功能） ----------------

def memory_fingerprint():
    """计算 memory 目录内容指纹（判断 AI 是否真的写入工作记忆）。"""
    if not paths.MEMORY_DIR.is_dir():
        return ""
    h = hashlib.md5()
    files = sorted(f for f in paths.MEMORY_DIR.rglob("*") if f.is_file())
    for f in files:
        h.update(str(f.relative_to(paths.MEMORY_DIR)).replace("\\", "/").encode("utf-8"))
        try:
            h.update(f.read_bytes())
        except Exception:
            pass
    return h.hexdigest()


@bp.route("/memory/fingerprint", methods=["GET"])
def get_fingerprint():
    """返回 memory 目录当前指纹。"""
    return jsonify({"success": True, "fingerprint": memory_fingerprint()})


@bp.route("/memory-graph", methods=["GET"])
def graph_page():
    """记忆图谱可视化页面（原生 Canvas 力导向图）。

    页面放在 static/（入库），不放 data/（被忽略），否则他人拉取后页面缺失。
    """
    page = paths.APP_DIR / "static" / "memory_graph.html"
    if not page.is_file():
        return _err("图谱页面不存在")
    return send_file(str(page), mimetype="text/html")
