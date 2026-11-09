"""
路由：客户端注册与自定义配置保管

- POST   /api/clients                    注册（同一 site_key 覆盖）
- GET    /api/clients?site_key=...       取回注册信息
- DELETE /api/clients?site_key=...       注销

约定：
- 自定义配置与可执行指令声明原样存取，不做字段校验、不做结构清洗；
- 错误以 { success: false, error } 配明确 HTTP 状态返回。
"""
from flask import Blueprint, jsonify, request

import paths  # noqa: F401  触发路径引导，保证下面的扁平导入可用
import client_registry as registry

bp = Blueprint("clients_route", __name__)


def _body():
    """读取请求体 JSON；非 JSON 或解析失败时按空字典处理。"""
    return request.get_json(force=True, silent=True) or {}


def _valid_key(key):
    """标识只用于路由索引，必须是非空字符串；不涉及自定义配置内容。"""
    return isinstance(key, str) and bool(key)


def _register_client():
    """POST 分支：登记客户端，返回注册结果。"""
    # 读请求体；非法 JSON 由 _body 兜底为空字典。
    data = _body()
    key = data.get("site_key")
    # 标识缺失或不合法：明确回 400，避免把 None 当键写盘。
    if not _valid_key(key):
        return jsonify({"success": False, "error": "site_key 必须是非空字符串"}), 400
    # 自定义配置与指令声明取到什么就存什么，缺省 None 也原样保留。
    entry = registry.register(key, data.get("custom_config"), data.get("commands"))
    return jsonify({"success": True, "site_key": entry["site_key"]})


def _lookup_client(key):
    """GET 分支：取回注册信息；未注册返回 404 与明确错误。"""
    entry = registry.lookup(key)
    # 查无此键：不静默返回空，给出可判别的错误文本。
    if entry is None:
        return jsonify({"success": False, "error": "客户端未注册：" + key}), 404
    return jsonify({
        "success": True,
        "site_key": entry["site_key"],
        "custom_config": entry["custom_config"],
        "commands": entry["commands"],
    })


def _unregister_client(key):
    """DELETE 分支：注销；标识不存在也返回成功，removed=false。"""
    removed = registry.unregister(key)
    return jsonify({"success": True, "site_key": key, "removed": removed})


@bp.route("/api/clients", methods=["POST", "GET", "DELETE", "OPTIONS"])
def clients():
    """注册（POST）、取回（GET）或注销（DELETE）一个客户端。"""
    # 注册单独走 POST 分支，参数取自请求体。
    if request.method == "POST":
        return _register_client()
    # 取回与注销共用查询串中的 site_key，避免路径里出现斜杠被截断。
    key = request.args.get("site_key")
    if not _valid_key(key):
        return jsonify({"success": False, "error": "site_key 必须是非空字符串"}), 400
    if request.method == "GET":
        return _lookup_client(key)
    return _unregister_client(key)
