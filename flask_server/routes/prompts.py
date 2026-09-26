"""
路由：技能数据（说明段落 + 技能清单）与首页

- GET  /prompt_sections  返回已上线技能的统一说明段落
- GET  /                  服务首页，列出可用工具
"""
from flask import Blueprint, Response, jsonify, request

import runtime
import prompt_sections
import custom_tools as ct

bp = Blueprint("prompts", __name__)


@bp.route("/prompt_sections", methods=["GET", "OPTIONS"])
def prompt_section_list():
    """技能数据：返回已上线技能的统一说明与技能清单，供镜像插件注入 System Prompt。

    skills        —— 注入 System Prompt 的精简清单（含说明文档的技能）。
    skillsManage  —— 设置页「技能」区块的管理视图（全部技能 + 其工具 + 开关状态）。
    """
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify({
        "success": True,
        "sections": prompt_sections.sections(),
        "skills": prompt_sections.skills(),
        "skillsManage": prompt_sections.skills_manage(),
    })


@bp.route("/skills/<skill>/enabled", methods=["PUT", "OPTIONS"])
def skill_set_enabled(skill):
    """技能一键上 / 下线：批量设置该技能下全部工具的 enabled，并刷新提供方注册表。"""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    enabled = bool(data.get("enabled"))
    changed = ct.set_skill_enabled(skill, enabled)
    # 上下线会改变提供方工具集合（external 工具是否注册）
    runtime.refresh_external_providers()
    return jsonify({"ok": True, "skill": skill, "enabled": enabled, "changed": changed})


@bp.route("/skills/<skill>/doc", methods=["GET", "PUT", "OPTIONS"])
def skill_doc(skill):
    """技能说明文档（默认 SKILL.md）的读取与写回。

    GET  ?file=SKILL.md          读取文档文本
    PUT  { file, text }          写回文档文本
    """
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        if request.method == "GET":
            rel = (request.args.get("file") or "SKILL.md").strip()
            return jsonify({"ok": True, **ct.read_skill_doc(skill, rel)})
        data = request.get_json(force=True, silent=True) or {}
        rel = (data.get("file") or "SKILL.md").strip()
        return jsonify({"ok": True, **ct.write_skill_doc(skill, rel, data.get("text"))})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/", methods=["GET"])
def index():
    """服务首页：列出工具与常用接口，便于浏览器直接确认服务在线。"""
    items = "".join(
        f"<li><b>{k}</b> — {v['description']}</li>" for k, v in runtime.TOOLS.items()
    )
    return Response(
        f"<h2>AI 工具调用镜像 · 本地服务</h2>"
        f"<p>POST <code>/tool</code> 调用工具，GET <code>/tools</code> 获取工具目录，"
        f"POST/GET <code>/config</code> 读写配置。</p>"
        f"<ul>{items}</ul>",
        mimetype="text/html",
    )
