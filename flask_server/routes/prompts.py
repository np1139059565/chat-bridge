"""
路由：技能数据（说明段落 + 技能清单）与首页

- GET  /prompt_sections  返回已上线技能的统一说明段落
- GET  /                  服务首页，列出记忆系统入口与可用工具
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


# 首页样式：轻量内联，避免依赖外部静态资源，浏览器直开即可读
_INDEX_STYLE = (
    "body{font-family:system-ui,sans-serif;max-width:760px;margin:32px auto;padding:0 16px;"
    "line-height:1.7;color:#222}"
    "h2{margin-bottom:4px}h3{margin-top:24px;border-bottom:1px solid #eee;padding-bottom:4px}"
    "code{background:#f2f3f5;padding:1px 5px;border-radius:3px}"
    "ul{padding-left:20px}li{margin:4px 0}"
    "a{color:#2d6cdf}"
)


def _index_html():
    """拼首页 HTML：记忆系统入口 + 内置工具清单。"""
    tools = "".join(
        f"<li><b>{k}</b> — {v['description']}</li>" for k, v in runtime.TOOLS.items()
    )
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>AI 工具调用镜像 · 本地服务</title>"
        f"<style>{_INDEX_STYLE}</style></head><body>"
        "<h2>AI 工具调用镜像 · 本地服务</h2>"
        "<p>POST <code>/tool</code> 调用工具，GET <code>/tools</code> 获取工具目录，"
        "POST/GET <code>/config</code> 读写配置。</p>"
        "<h3>记忆系统</h3>"
        "<ul>"
        "<li><a href=\"/memory-graph\">记忆图谱</a> — 可视化查看记忆节点、突触与事件（也可用别名 /memory_graph.html）</li>"
        "<li><code>GET /memory/notes?kind=journal</code> — 每日记忆；<code>kind=notebook</code> — 错题本</li>"
        "<li><code>GET /memory/notes/days</code> — 有每日记忆的日期列表</li>"
        "<li><code>POST /memory/plan</code> + <code>POST /memory/search</code> — 计划锚定与验证式关联检索</li>"
        "<li><code>POST /memory/decay/run</code> — 触发一次衰减与升降级</li>"
        "<li><code>GET /memory/conversations?site_key=</code> — 会话列表（消息树已迁入后端）</li>"
        "</ul>"
        "<h3>内置工具</h3>"
        f"<ul>{tools}</ul>"
        "</body></html>"
    )


@bp.route("/", methods=["GET"])
def index():
    """服务首页：列出记忆系统入口与可用工具，便于浏览器直接确认服务在线。"""
    return Response(_index_html(), mimetype="text/html")
