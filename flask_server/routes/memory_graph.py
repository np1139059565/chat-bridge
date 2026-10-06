"""AI 工具调用镜像插件 —— 记忆系统：HTTP 接口

职责：暴露记忆系统的全部 HTTP 接口（方案第七节接口清单），
并在应用启动时触发内存加载。同时接管原 memory.py 的目录指纹接口（2B）。

接口分组：读写 / 检索 / 分级 / 事件 / 会话 / 可视化 / 加载。

依赖：flask、memory_* 各模块、paths
"""
import json

from flask import Blueprint, jsonify, request, send_file

import paths
import memory_nodes
import memory_edges
import memory_cards
import memory_decay
import memory_events
import memory_search
import memory_loader
import memory_conversations
import memory_solidify
import memory_notes
import rule_enforce

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


@bp.route("/memory/node/delete", methods=["POST"])
def node_hard_delete():
    """硬删一个节点（不可恢复）。前端须先做二次确认。"""
    data = request.get_json(force=True) or {}
    nid = data.get("node_id")
    if not nid:
        return _err("缺少 node_id")
    n = memory_nodes.hard_delete(nid)
    memory_loader.invalidate()
    return _ok(deleted=n)


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
    # 保存为异步：只把请求投入后台保存队列即返回，真正的写库与后续蒸馏
    # 由后台线程串行执行。请求线程不再被全量写库占用，也不再持有写锁，
    # 从而不拖慢其它界面接口请求（硬约束：任何操作禁止占用界面接口请求）。
    memory_conversations.save_conversation(conv_id, site_key, conv)
    memory_loader.invalidate()
    return _ok(accepted=True)


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
    """导出图数据（节点 + 边），供 D3 渲染。

    节点与边同口径：
      - 会话 id 留空：两边都返回全库（页面输入框语义「留空看全部」）；
      - 会话 id 非空：节点按该会话过滤，边只保留两端都在该会话节点集合内的边。
    避免出现「0 节点却配全库边」的口径错位。
    """
    conv_id = request.args.get("conv_id", "")
    site_key = request.args.get("site_key") or None
    # since_id：增量拉取——只返回 id 大于它的新节点，及「至少一端是新节点」的边，
    # 供页面「随 AI 生成逐个增加节点」的轮询使用；0 或未传表示全量。
    since_id = request.args.get("since_id", type=int) or 0
    if conv_id:
        raw_nodes = memory_nodes.list_by_conv(conv_id, site_key)
        node_ids = [n["id"] for n in raw_nodes]
        edges = memory_edges.edges_within(node_ids)
    else:
        raw_nodes = memory_nodes.list_all()
        edges = memory_edges.all_edges()
    max_id = max([n["id"] for n in raw_nodes], default=0)
    if since_id:
        raw_nodes = [n for n in raw_nodes if n["id"] > since_id]
        keep = set(n["id"] for n in raw_nodes)
        # 只保留「至少一端是新节点」的边，避免重复下发旧边
        edges = [e for e in edges
                 if e.get("src_node") in keep or e.get("dst_node") in keep]
    nodes = []
    for n in raw_nodes:
        nodes.append({
            "id": n["id"], "source": n["source"], "tier": n.get("tier"),
            "strength": n.get("strength"), "essence": n.get("essence"),
            "keywords": n.get("keywords"),
            # created_at：时间轴视图按时间排布节点需要
            "created_at": n.get("created_at") or 0,
        })
    # 边的 keywords 存的是 JSON 字符串，转为数组供前端直接使用
    for e in edges:
        kw = e.get("keywords")
        if isinstance(kw, str) and kw:
            try:
                e["keywords"] = json.loads(kw)
            except Exception:
                e["keywords"] = []
        else:
            e["keywords"] = []
    # max_id 供前端记下，下次轮询带上，实现增量
    return _ok(nodes=nodes, edges=edges, max_id=max_id)


# ---------------- 读写层·补充 ----------------

@bp.route("/memory/set", methods=["POST"])
def node_set():
    """更新节点内容字段（blocks / essence / keywords）。"""
    data = request.get_json(force=True) or {}
    nid = data.get("node_id")
    if not nid:
        return _err("缺少 node_id")
    ok = memory_nodes.set_content(
        nid,
        blocks=data.get("blocks"),
        essence=data.get("essence"),
        keywords=data.get("keywords"),
    )
    memory_loader.invalidate()
    return _ok(updated=ok)


# ---------------- 分级层·补充 ----------------

@bp.route("/memory/promote", methods=["POST"])
def node_promote():
    """手动设置节点分级（temp / mid / perm）。"""
    data = request.get_json(force=True) or {}
    nid = data.get("node_id")
    tier = data.get("tier")
    if not nid or tier not in ("temp", "mid", "perm"):
        return _err("缺少 node_id 或 tier 非法")
    node = memory_nodes.promote_node(nid, tier)
    if not node:
        return _err("节点不存在")
    memory_loader.invalidate()
    return _ok(node=node)


@bp.route("/memory/strength", methods=["GET"])
def node_strength():
    """查询节点当前强度。"""
    nid = request.args.get("node_id", type=int)
    if not nid:
        return _err("缺少 node_id")
    val = memory_nodes.get_strength(nid)
    if val is None:
        return _err("节点不存在")
    return _ok(node_id=nid, strength=val)


# ---------------- 事件层·补充 ----------------

@bp.route("/memory/event/merge", methods=["POST"])
def event_merge():
    """把若干事件根节点合并到同一事件。"""
    data = request.get_json(force=True) or {}
    root_id = data.get("root_id")
    members = data.get("member_ids") or []
    if not root_id:
        return _err("缺少 root_id")
    n = memory_events.event_merge(root_id, members, reason=data.get("reason", "manual"))
    return _ok(merged=n)


@bp.route("/memory/event/tree", methods=["GET"])
def event_tree():
    """取某事件树（根 + 被并成员 + 子节点）。"""
    root_id = request.args.get("root_id", type=int)
    if not root_id:
        return _err("缺少 root_id")
    tree = memory_events.event_tree_get(root_id)
    if tree is None:
        return _err("事件根不存在")
    return _ok(tree=tree)


# ---------------- 固化层 ----------------

@bp.route("/memory/solidify/rule", methods=["POST"])
def solidify_rule():
    """把某节点固化为规则文件。"""
    data = request.get_json(force=True) or {}
    nid = data.get("node_id")
    rule_name = data.get("rule_name")
    if not nid or not rule_name:
        return _err("缺少 node_id 或 rule_name")
    res = memory_solidify.promote_to_rule(nid, rule_name, title=data.get("title", ""))
    if res is None:
        return _err("节点不存在")
    memory_loader.invalidate()
    return _ok(**res)


@bp.route("/memory/solidify/notebook", methods=["POST"])
def solidify_notebook():
    """把某节点写入错题本。"""
    data = request.get_json(force=True) or {}
    nid = data.get("node_id")
    if not nid:
        return _err("缺少 node_id")
    res = memory_solidify.promote_to_notebook(nid, note=data.get("note", ""))
    if res is None:
        return _err("节点不存在")
    return _ok(**res)


# ---------------- 规则程序化（方案第九节） ----------------

@bp.route("/memory/rule-check", methods=["POST"])
def rule_check():
    """对一组工具调用 / 命令 / 文本跑可机械判定的规则检查。"""
    data = request.get_json(force=True) or {}
    res = rule_enforce.run_all(
        tool_calls=data.get("tool_calls"),
        command=data.get("command"),
        target=data.get("target", ""),
        text=data.get("text"),
    )
    return _ok(**res)


# ---------------- 加载层 ----------------

@bp.route("/memory/load", methods=["POST"])
def load():
    """触发一次内存加载。"""
    return _ok(**memory_loader.load_all())


# ---------------- 笔记层（每日记忆 + 错题本，全部存库） ----------------

@bp.route("/memory/note", methods=["POST"])
def note_add():
    """新增一条笔记（journal=每日记忆 / notebook=错题本）。"""
    data = request.get_json(force=True) or {}
    kind = data.get("kind")
    text = (data.get("text") or "").strip()
    if kind not in ("journal", "notebook"):
        return _err("kind 非法（应为 journal / notebook）")
    if not text:
        return _err("缺少 text")
    nid = memory_notes.add_note(
        kind, text, day=data.get("day"), node_id=data.get("node_id") or 0,
        keywords=data.get("keywords") or [],
    )
    return _ok(note_id=nid)


@bp.route("/memory/notes", methods=["GET"])
def note_list():
    """列举笔记（可按 kind / day 过滤）。"""
    kind = request.args.get("kind")
    day = request.args.get("day")
    limit = request.args.get("limit", type=int) or 200
    return _ok(notes=memory_notes.list_notes(kind=kind, day=day, limit=limit))


@bp.route("/memory/notes/days", methods=["GET"])
def note_days():
    """列出每日记忆有内容的日期（倒序）。"""
    return _ok(days=memory_notes.list_days())


@bp.route("/memory/note/delete", methods=["POST"])
def note_delete():
    """删除一条笔记。"""
    data = request.get_json(force=True) or {}
    nid = data.get("note_id")
    if not nid:
        return _err("缺少 note_id")
    return _ok(deleted=memory_notes.delete_note(nid))


@bp.route("/memory-graph", methods=["GET"])
@bp.route("/memory_graph.html", methods=["GET"])
def graph_page():
    """记忆图谱可视化页面（原生 Canvas 力导向图）。

    页面放在 static/（入库），不放 data/（被忽略），否则他人拉取后页面缺失。
    两个路径都指向同一页面：/memory-graph（规范）与 /memory_graph.html（别名，
    与页面文件名一致，便于直接记忆与访问）。
    """
    page = paths.APP_DIR / "static" / "memory_graph.html"
    if not page.is_file():
        return _err("图谱页面不存在")
    # 禁用缓存：页面与脚本改动频繁，缓存旧页会导致「引用已删脚本→白屏」。
    resp = send_file(str(page), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


@bp.route("/memory-graph-assets/<path:name>", methods=["GET"])
def graph_asset(name):
    """记忆图谱页面的脚本资源（static 目录下 mg_*.js）。

    只允许 mg_ 前缀的 .js 文件名，拦截目录穿越，避免暴露 static 下其它文件。
    """
    import os
    if not name.startswith("mg_") or not name.endswith(".js") or "/" in name or "\\" in name or ".." in name:
        return _err("非法资源名")
    js = paths.APP_DIR / "static" / name
    if not js.is_file():
        return _err("图谱脚本不存在")
    # 脚本同样禁用缓存：否则浏览器混用新旧脚本会直接报错、页面空白。
    resp = send_file(str(js), mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp
