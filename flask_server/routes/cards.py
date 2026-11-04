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
    """镜像插件轮询：取走 AI 通道尚未投递的卡片。

    附带「旧版扩展」检测：本接口是旧扩展唯一的取件入口。若此时指令通道里
    仍有待取命令，说明扩展还没重载、取不到指令（指令已迁到 /api/commands/pending）。
    这种情况指令会静默失效，用户只会觉得「指令没反应」，极难定位，故显式告警。
    """
    _warn_if_stale_client()
    # 取证日志：记录「哪个页面取走了哪几张卡」。
    # 用途是判断多标签页串台的实际形态与频率——卡片机制目前是「谁先取到算谁的」，
    # 缺少页面归属概念，改之前需先有真实数据，否则容易改错方向。
    # 仅记录，不影响任何行为。
    resp = _pending_of(bus)
    try:
        import app_log
        client = (request.args.get("client") or "(未标注)").strip()
        cards = resp.get_json().get("cards") or []
        # 只在真取到卡片时记录，避免每 5 秒的轮询刷屏
        if cards:
            app_log.info("[cards] 取件 client=%s 条数=%d ids=%s"
                         % (client, len(cards), ",".join(c["id"][:8] for c in cards)))
    except Exception:
        # 取证日志绝不能影响取件
        pass
    return resp


def _warn_if_stale_client():
    """旧扩展仍在轮询旧接口、而指令通道有积压时告警。

    为什么不做双写兼容：把指令同时放进 AI 通道，等于又让指令流经
    AI 的取件路径，正是本次隔离要根除的问题。宁可显式告警、要求重载扩展，
    也不为兼容而破坏隔离。
    """
    try:
        pending = command_bus.claim_pending()
        if not pending:
            return
        # 只告警不吞掉：这些命令仍在 command_bus 里，等新扩展来取
        import app_log
        app_log.warn(
            "[isolation] 检测到旧版扩展：指令通道有 %d 条待取命令，但本接口只返回 AI 卡片。"
            "请重新加载扩展以启用 /api/commands/pending。" % len(pending))
    except Exception:
        # 检测本身绝不能影响取件
        pass


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
