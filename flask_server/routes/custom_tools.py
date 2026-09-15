"""
路由：自定义工具（来自标准 skill 的 tool.json）

- GET    /custom_tools          返回已安装的自定义工具与可扫描根目录
- POST   /custom_tools/scan     扫描指定目录下的可安装 skill
- POST   /custom_tools/install  安装指定 skill 中的工具
- PUT    /custom_tools/<name>   更新自定义工具（上下线 / 描述 / 参数）
- DELETE /custom_tools/<name>   删除自定义工具

安装 / 删除 / 上下线都会改变提供方工具集合，因此统一刷新外部提供方注册表。
"""
from flask import Blueprint, jsonify, request

import runtime
import custom_tools as ct

bp = Blueprint("custom_tools_route", __name__)


@bp.route("/custom_tools", methods=["GET", "OPTIONS"])
def custom_tools_list():
    """返回已安装的自定义工具与可扫描的默认根目录。"""
    if request.method == "OPTIONS":
        return ("", 204)
    roots = [str(p) for p in ct.DEFAULT_SKILL_ROOTS]
    return jsonify({"tools": ct.all_meta_full(), "scanRoots": roots})


@bp.route("/custom_tools/scan", methods=["POST", "OPTIONS"])
def custom_tools_scan():
    """扫描指定目录，返回其中可安装的 skill 与工具。"""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    d = (data.get("dir") or "").strip()
    try:
        return jsonify({"ok": True, "skills": ct.scan_dir(d)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/custom_tools/install", methods=["POST", "OPTIONS"])
def custom_tools_install():
    """安装指定 skill 中的工具（names 为空时安装全部）。"""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    d = (data.get("dir") or "").strip()
    names = data.get("names")
    try:
        installed = ct.install(d, set(names) if names else None)
        runtime.refresh_external_providers()
        return jsonify({"ok": True, "installed": installed})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/custom_tools/<name>", methods=["PUT", "DELETE", "OPTIONS"])
def custom_tools_manage(name):
    """更新（PUT）或删除（DELETE）某个自定义工具。"""
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "DELETE":
        ok = ct.remove(name)
        runtime.refresh_external_providers()
        return jsonify({"ok": bool(ok), "removed": name})
    data = request.get_json(force=True, silent=True) or {}
    t = ct.update(name, data)
    if not t:
        return jsonify({"ok": False, "error": "未找到工具：" + name}), 404
    # 上线 / 下线变化会改变提供方工具集合
    runtime.refresh_external_providers()
    return jsonify({"ok": True, "tool": t, "tool_name": name})
