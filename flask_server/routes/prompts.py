"""
路由：技能说明段落、自愈 HTTP 接口与首页

- GET  /prompt_sections  返回已上线技能的统一说明段落
- POST /hot_fix           修复工具代码并热重载（等价于 hot_reload_fix 工具）
- GET  /                  服务首页，列出可用工具
"""
from flask import Blueprint, Response, jsonify, request

import runtime
import prompt_sections
from responses import exception_payload
from self_healing import t_hot_reload_fix

bp = Blueprint("prompts", __name__)


@bp.route("/prompt_sections", methods=["GET", "OPTIONS"])
def prompt_section_list():
    """技能说明段落：返回已上线技能的统一说明，供镜像插件注入 System Prompt。"""
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify({"success": True, "sections": prompt_sections.sections()})


@bp.route("/hot_fix", methods=["POST", "OPTIONS"])
def hot_fix():
    """AI 自愈专用 HTTP 接口：修复本地工具代码并热重载（等价于 hot_reload_fix 工具）。"""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(success=True, result=t_hot_reload_fix(data))
    except Exception as e:
        # 失败时同样给出分类 + 堆栈 + 位置，便于 AI 继续定位
        return jsonify(exception_payload(e)), 200


@bp.route("/", methods=["GET"])
def index():
    """服务首页：列出工具与常用接口，便于浏览器直接确认服务在线。"""
    items = "".join(
        f"<li><b>{k}</b> — {v['description']}</li>" for k, v in runtime.TOOLS.items()
    )
    return Response(
        f"<h2>AI 工具调用镜像 · 本地服务</h2>"
        f"<p>POST <code>/tool</code> 调用工具，GET <code>/tools</code> 获取工具目录，"
        f"POST <code>/hot_fix</code> 修复工具代码并热重载。POST/GET <code>/config</code> 读写配置。</p>"
        f"<ul>{items}</ul>",
        mimetype="text/html",
    )
