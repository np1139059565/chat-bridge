"""投递队列路由：登记投递项、取走待投递项、确认已展示。"""
from flask import Blueprint, request, jsonify

# bus 供 常规通道使用；command_bus 供指令通道使用。同一个类的两个实例。
from delivery_queue import bus, command_bus

bp = Blueprint("cards", __name__)


def _parse_card_fields(data):
    """解析投递字段；content 非法时返回错误响应，否则返回字段字典。"""
    content = data.get("content")
    # content 必须是字符串：该字段即投递正文
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
    """登记一条投递项并立即返回。

    登记采用「发送即结束」：登记成功即返回，不等待接收方回填，
    因此不存在超时失败。投递项由接收方轮询取走后自行维护状态，
    任务进展由接收端通过独立通道主动推送给发起方。

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
    """取某条通道的待投递项（按页面归属过滤）。

    抽成一个函数供两个路由共用：常规通道与指令通道行为完全一致，
    差异只在「取哪个实例」，复制一份逻辑只会让日后改一处漏一处。

    页面归属：请求方用 ?page=<页面地址> 声明自己是谁。声明后只取
    「不限页面」与「目标就是本页」的投递项，其他页面的投递项取不到——
    这是多路接收端并存时指令不串台的落地。未声明页面时退化为
    只取不限页面的投递项（宁可不给，也不串台）。

    @param target_bus 目标通道实例（bus / command_bus）
    @returns Flask 响应
    """
    page = (request.args.get("page") or "").strip()  # 取请求方声明的页面地址
    # 兜底登记：正常情况下抽屉打开时已显式上报上线，这里只是补一次。
    # register 是幂等的（集合重复加入无副作用），因此每次轮询都调用不会出错，
    # 但「是否在线」不由轮询决定——只有显式下线才把页面移出列表。
    if page:
        import page_registry
        page_registry.register(page)
    return jsonify({"success": True, "cards": target_bus.claim_pending(page)})


@bp.route("/api/cards/pending", methods=["GET", "OPTIONS"])
def pending_items():
    """接收端轮询：取走常规通道尚未投递的投递项。

    附带「旧版扩展」检测：本接口是旧扩展唯一的取件入口。若此时指令通道里
    仍有待取命令，说明扩展还没重载、取不到指令（指令已迁到 /api/commands/pending）。
    这种情况指令会静默失效，用户只会觉得「指令没反应」，极难定位，故显式告警。
    """
    _warn_if_stale_client()
    # 取证日志：记录「哪个页面取走了哪几条投递项」。
    # 用途是判断多标签页串台的实际形态与频率——队列目前是「谁先取到算谁的」，
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

    为什么不做双写兼容：把指令同时放进常规通道，等于又让指令流经
    常规通道的取件路径，正是本次隔离要根除的问题。宁可显式告警、要求重载扩展，
    也不为兼容而破坏隔离。
    """
    try:
        pending = command_bus.claim_pending()
        if not pending:
            return
        # 只告警不吞掉：这些命令仍在 command_bus 里，等新扩展来取
        import app_log
        app_log.warn(
            "[isolation] 检测到旧版扩展：指令通道有 %d 条待取命令，但本接口只返回常规投递项。"
            "请重新加载扩展以启用 /api/commands/pending。" % len(pending))
    except Exception:
        # 检测本身绝不能影响取件
        pass


@bp.route("/api/pages/online", methods=["POST", "OPTIONS"])
def page_online():
    """页面显式上线：抽屉打开时立即上报，不等任何轮询或超时。

    请求体：{ page: 页面地址 }
    与轮询中的兜底登记不同，这是页面进入在线集合的正规入口，
    打开抽屉的那一刻就生效。
    """
    data = request.get_json(force=True, silent=True) or {}  # 解析请求体
    page = str(data.get("page") or "").strip()              # 取页面地址并去空白
    if not page:                                             # 缺地址无法登记
        return jsonify({"success": False, "error": "PAGE_REQUIRED"}), 400
    import page_registry                                     # 延迟导入：避免循环依赖
    page_registry.register(page)                             # 加入在线集合
    return jsonify({"success": True, "page": page})         # 回执带地址便于核对


@bp.route("/api/pages/offline", methods=["POST", "OPTIONS"])
def page_offline():
    """页面显式下线：抽屉关闭或页面卸载时立即上报。

    请求体：{ page: 页面地址 }
    下线不依赖任何超时判定——页面被浏览器节流时仍然是在线的，
    只有明确关闭才从在线集合移除。
    """
    data = request.get_json(force=True, silent=True) or {}  # 解析请求体
    page = str(data.get("page") or "").strip()              # 取页面地址并去空白
    if not page:                                             # 缺地址无从注销
        return jsonify({"success": False, "error": "PAGE_REQUIRED"}), 400
    import page_registry                                     # 延迟导入
    page_registry.unregister(page)                           # 移出在线集合
    return jsonify({"success": True, "page": page})         # 回执带地址


@bp.route("/api/commands/pending", methods=["GET", "OPTIONS"])
def pending_commands():
    """接收端轮询：取走指令通道下发的待执行投递项。

    指令项与常规投递项是两条独立通道：指令走 command_bus，常规走 bus。
    分开之后，指令项在物理上不会被常规接收端那一侧取走，
    也就不再依赖前端「拦截并丢弃」来兜底。
    """
    return _pending_of(command_bus)


@bp.route("/api/cards/<card_id>/delivered", methods=["POST", "OPTIONS"])
def confirm_delivered(card_id):
    """确认投递项已展示，此后不再投递。

    接收端展示后调用。在收到确认前，投递项可被任何接收端反复取走；
    这是投递项停止投递的唯一条件。重复调用幂等。
    """
    # 两条通道都尝试确认：接收端对两类投递项调用的是同一个回执接口。
    # 若只确认常规队列，指令项会永远处于未确认态、被反复下发，
    # 造成同一条指令被无限重复执行——这是必须堵死的隐患。
    ok = bus.confirm_delivered(card_id) or command_bus.confirm_delivered(card_id)
    if not ok:
        return jsonify({"success": False, "error": "UNKNOWN_CARD"}), 404
    return jsonify({"success": True, "id": card_id})


@bp.route("/api/cards/<card_id>", methods=["GET", "OPTIONS"])
def get_card(card_id):
    """查询单条投递项状态。"""
    # 与确认接口同理：两条通道都查，避免指令项查不到
    card = bus.get(card_id) or command_bus.get(card_id)
    if not card:
        return jsonify({"success": False, "error": "UNKNOWN_CARD"}), 404
    return jsonify({"success": True, "card": card})
