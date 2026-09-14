"""外部工具提供方通道：轮询取命令、回传执行结果。

提供方通过 POST /api/ext/<provider> 与工具服务交互：
    action=poll   取走待执行命令（兼作心跳）
    action=result 回传某次工具调用的结果
"""
from flask import Blueprint, request, jsonify

from external_tools import hub

bp = Blueprint("ext", __name__)


@bp.route("/api/ext/<provider>", methods=["POST", "OPTIONS"])
def provider_channel(provider):
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action")

    if action == "poll":
        commands = hub.poll(provider)
        return jsonify({"success": True, "commands": commands})

    if action == "result":
        request_id = data.get("request_id")
        if not request_id:
            return jsonify({"success": False, "error": "INVALID_PARAMS", "message": "request_id required"}), 400
        ok = hub.resolve(request_id, data.get("result"))
        return jsonify({"success": bool(ok)})

    return jsonify({"success": False, "error": "UNKNOWN_ACTION", "message": action}), 400
