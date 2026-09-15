"""
路由：规则文件管理（设置页增 / 删 / 改）

- GET    /rules          列出全部规则与优先级定义
- POST   /rules          新建规则
- GET    /rules/<name>   读取单条规则内容与优先级
- PUT    /rules/<name>   更新规则内容或优先级
- DELETE /rules/<name>   删除规则
"""
from flask import Blueprint, jsonify, request

import rules as rules_mod

bp = Blueprint("rules_route", __name__)


@bp.route("/rules", methods=["GET", "POST", "OPTIONS"])
def rules_list():
    """列出规则（GET）或新建规则（POST）。"""
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        name = data.get("name")
        content = data.get("content", "")
        try:
            saved = rules_mod.write_rule(name, content, priority=data.get("priority"))
            return jsonify({"ok": True, "name": saved})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    # GET：返回规则列表、目录与优先级定义
    return jsonify({
        "rules": rules_mod.list_rules(),
        "rulesDir": str(rules_mod.RULES_DIR),
        "priorities": rules_mod.PRIORITIES,
        "priorityLabels": rules_mod.PRIORITY_LABELS,
    })


def _update_rule(name):
    """PUT 分支：提供了 content 时整条重写，否则仅更新 priority。"""
    data = request.get_json(force=True, silent=True) or {}
    try:
        if "content" in data:
            saved = rules_mod.write_rule(name, data.get("content", ""), priority=data.get("priority"))
        else:
            if data.get("priority") is not None:
                rules_mod.set_priority(name, data.get("priority"))
            saved = name
        return jsonify({"ok": True, "name": saved})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


def _get_rule(name):
    """GET 分支：读取单条规则内容与优先级。"""
    if not rules_mod.valid_name(name):
        return jsonify({"ok": False, "error": "规则名非法"}), 400
    try:
        content = rules_mod.read_rule(name)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "规则不存在：" + name}), 404
    return jsonify({"ok": True, "name": name, "content": content, "priority": rules_mod.get_priority(name)})


@bp.route("/rules/<name>", methods=["GET", "PUT", "DELETE", "OPTIONS"])
def rules_manage(name):
    """读取（GET）、更新（PUT）或删除（DELETE）单条规则。"""
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "DELETE":
        ok = rules_mod.delete_rule(name)
        return jsonify({"ok": bool(ok), "removed": name})
    if request.method == "PUT":
        return _update_rule(name)
    return _get_rule(name)
