"""AI 工具调用镜像插件 —— 记忆图谱：可视化页面与静态资源

职责：只服务记忆图谱这个「页面」本身——返回 HTML 页面与页面用到的 mg_*.js。
数据接口（图数据、节点、会话等）在 routes/memory_graph.py。
拆出本文件的动因：memory_graph.py 因数据接口较多触及 450 行上限，
把「页面与资源」这一独立关注点分离，两侧都保持精简。

依赖：flask、paths
"""
from flask import Blueprint, send_file

import paths

bp = Blueprint("memory_graph_page", __name__)


def _err(msg):
    """统一失败响应。"""
    from flask import jsonify
    return jsonify({"success": False, "error": msg})


def _no_cache(resp):
    """给响应加上禁用缓存头。

    页面与脚本改动频繁，缓存旧页会导致「引用已删脚本→白屏」，故一律禁缓存。
    @param resp Flask 响应对象
    @returns 同一个响应对象（已加头）
    """
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


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
    return _no_cache(send_file(str(page), mimetype="text/html"))


@bp.route("/memory-graph-assets/<path:name>", methods=["GET"])
def graph_asset(name):
    """记忆图谱页面的脚本资源（static 目录下 mg_*.js）。

    只允许 mg_ 前缀的 .js 文件名，拦截目录穿越，避免暴露 static 下其它文件。
    """
    if not name.startswith("mg_") or not name.endswith(".js") or "/" in name or "\\" in name or ".." in name:
        return _err("非法资源名")
    js = paths.APP_DIR / "static" / name
    if not js.is_file():
        return _err("图谱脚本不存在")
    return _no_cache(send_file(str(js), mimetype="application/javascript"))
