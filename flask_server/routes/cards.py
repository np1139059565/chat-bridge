"""卡片路由：登记外部卡片、投递给镜像插件、确认已展示。"""
from flask import Blueprint, request, jsonify

# bus 供 AI 通道使用；command_bus 供指令通道使用。同一个类的两个实例。
from card_bus import bus, command_bus

bp = Blueprint("cards", __name__)


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
    """登记一张外部卡片并立即返回。

    外部卡片采用「发送即结束」：登记成功即返回，不等待镜像插件回填，
    因此不存在超时失败。卡片由镜像插件轮询取走后自行维护状态，
    任务进展由网页 AI 通过 push_message 主动推送给发起方。

    请求体：{ type, title, content, payload }
    成功返回：{ success: true, id, status }
    """
    data = request.get_json(force=True, silent=True) or {}
    fields = _parse_card_fields(data)
    # 字段解析失败：直接返回 400 响应
    if isinstance(fields, tuple):
        return fields

    card = bus.create(**fields)
    return jsonify({"success": True, "id": card.id, "status": card.status})


def _pending_of(target_bus):
    """取某条通道的待投递卡片。

    抽成一个函数供两个路由共用：AI 通道与指令通道行为完全一致，
    差异只在「取哪个实例」，复制一份逻辑只会让日后改一处漏一处。
    @param target_bus 目标通道实例（bus / command_bus）
    @returns Flask 响应
    """
    return jsonify({"success": True, "cards": target_bus.claim_pending()})


@bp.route("/api/cards/pending", methods=["GET", "OPTIONS"])
def pending_cards():
    """镜像插件轮询：取走 AI 通道尚未投递的卡片。"""
    return _pending_of(bus)


@bp.route("/api/commands/pending", methods=["GET", "OPTIONS"])
def pending_commands():
    """抽屉轮询：取走指令通道下发的待执行命令。

    指令与 AI 卡片是两条独立通道：指令走 command_bus，AI 走 bus。
    分开之后，指令卡片在物理上不会被镜像/网页 AI 那一侧取走，
    也就不再依赖前端「拦截并丢弃」来兜底。
    """
    return _pending_of(command_bus)


@bp.route("/api/cards/<card_id>/delivered", methods=["POST", "OPTIONS"])
def confirm_delivered(card_id):
    """确认卡片已生成并展示，此后不再投递。

    客户端把卡片渲染进列表后调用。在收到确认前，卡片可被任何客户端反复取走；
    这是卡片停止投递的唯一条件。重复调用幂等。
    """
    # 两条通道都尝试确认：抽屉对两类卡片调用的是同一个回执接口。
    # 若只确认 AI 总线，指令卡片会永远处于未确认态、被反复下发，
    # 造成同一条指令被无限重复执行——这是必须堵死的隐患。
    ok = bus.confirm_delivered(card_id) or command_bus.confirm_delivered(card_id)
    if not ok:
        return jsonify({"success": False, "error": "UNKNOWN_CARD"}), 404
    return jsonify({"success": True, "id": card_id})


@bp.route("/api/cards/<card_id>", methods=["GET", "OPTIONS"])
def get_card(card_id):
    """查询单张卡片状态。"""
    # 与确认接口同理：两条通道都查，避免指令卡片查不到
    card = bus.get(card_id) or command_bus.get(card_id)
    if not card:
        return jsonify({"success": False, "error": "UNKNOWN_CARD"}), 404
    return jsonify({"success": True, "card": card})
