"""卡片路由：创建并同步等待、投递给镜像插件、结果回填。"""
from flask import Blueprint, request, jsonify

from card_bus import bus, DEFAULT_TIMEOUT_MS

bp = Blueprint("cards", __name__)


def _parse_timeout(data):
    """解析超时时间：非法或缺省时回退默认值（毫秒）。"""
    timeout_ms = data.get("timeout_ms") or DEFAULT_TIMEOUT_MS
    try:
        return int(timeout_ms)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MS


def _parse_card_fields(data):
    """解析建卡字段；content 非法时返回错误响应，否则返回字段字典。"""
    content = data.get("content")
    # content 必须是字符串：卡片正文即投递给镜像插件的内容
    if not content or not isinstance(content, str):
        return jsonify({"success": False, "error": "INVALID_CARD", "message": "content(str) required"}), 400
    return {
        "source": data.get("source") or "external",
        "card_type": data.get("type") or "",
        "title": data.get("title") or "",
        "content": content,
        "payload": data.get("payload") or {},
    }


@bp.route("/api/cards", methods=["POST", "OPTIONS"])
def create_card():
    """创建一张卡片并阻塞等待结果。

    请求体：{ title, content, payload, timeout_ms }
    成功返回：{ success: true, id, result }
    超时返回：{ success: false, id, error: "TIMEOUT" }
    """
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    fields = _parse_card_fields(data)
    # 字段解析失败：直接返回 400 响应
    if isinstance(fields, tuple):
        return fields

    timeout_ms = _parse_timeout(data)
    card = bus.create(timeout_ms=timeout_ms, **fields)
    ok, result = bus.wait(card.id, timeout_ms)
    if ok:
        return jsonify({"success": True, "id": card.id, "result": result})
    return jsonify({"success": False, "id": card.id, "error": result})


@bp.route("/api/cards/pending", methods=["GET", "OPTIONS"])
def pending_cards():
    """镜像插件轮询：取走尚未投递的卡片。"""
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify({"success": True, "cards": bus.claim_pending()})


@bp.route("/api/cards/<card_id>/reply", methods=["POST", "OPTIONS"])
def reply_card(card_id):
    """镜像插件回填某张卡片的结果，唤醒创建请求。"""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    result = data.get("result")
    ok = bus.resolve(card_id, result)
    if not ok:
        return jsonify({"success": False, "error": "UNKNOWN_CARD"}), 404
    return jsonify({"success": True, "id": card_id})


@bp.route("/api/cards/<card_id>", methods=["GET", "OPTIONS"])
def get_card(card_id):
    """查询单张卡片状态。"""
    if request.method == "OPTIONS":
        return ("", 204)
    card = bus.get(card_id)
    if not card:
        return jsonify({"success": False, "error": "UNKNOWN_CARD"}), 404
    return jsonify({"success": True, "card": card})
