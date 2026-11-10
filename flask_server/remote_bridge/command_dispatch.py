"""远程桥接 —— 抽屉命令下发通道

职责：把一条抽屉命令（drawer-command）经卡片总线下发到浏览器，并管理
「待回传请求」的登记与取出。从 command_panel.py 抽出，使其保持在行数上限内。

调用方是 command_panel.py；本模块不反向引用它，依赖保持单向。

- _dispatch / _dispatch_with_result：下发命令（后者额外带 request_id，
  等浏览器执行完把结果 POST 回来）
- _register_pending / take_pending：待回传请求的登记与取出
- _reply：用当前窗口回复一条 QQ 文本
- log：统一前缀打印
- _reply_ctx：线程局部标记，组合指令期间抑制中间回复

命名说明：函数名沿用原下划线前缀，整体搬运零改名，降低迁移风险。
"""
import json
import threading
import time
import uuid

from . import message_router, bridge_log

# 待回传请求表：{ request_id: {openid, expire} }
# 有些指令（列会话 / 截屏）需要浏览器执行后把结果回传，再转发到 QQ。
# 这里登记请求，浏览器完成后按 request_id 找回 openid，用被动回复发出。
_pending = {}
_pending_lock = threading.Lock()
PENDING_TTL = 60  # 请求有效期（秒），超时未回传则丢弃


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][command]", *args)


# 线程局部标记：组合指令执行期间的中间步骤，回复会被抑制，避免刷屏。
# 同时承载「当前指令来自哪条通道」（qq / wecom / weixin），
# 供下发时解析该通道绑定的站点用。用线程局部而非改所有处理函数签名：
# 指令处理函数有二十多个，逐个加参数改动面太大，且它们的签名已统一。
_reply_ctx = threading.local()


def set_channel(name):
    """标记当前线程正在处理的指令来自哪条通道。

    @param name 通道标识（qq / wecom / weixin）；空串表示来源不明
    """
    _reply_ctx.channel = str(name or "")


def current_channel():
    """取当前线程的通道标识；未设置时返回空串。"""
    return getattr(_reply_ctx, "channel", "")

# 网页版回执出口：{fn(text)}，由网页版路由注册。
# 指令处理器原本只会把回执发回 QQ；网页版没有 QQ 客户端，
# 因此在此留一个出口，让同一套指令逻辑的回执也能落到网页收件箱。
_web_reply_sink = None

# 网页版固定标识：指令回执据此判断「这条来自网页版」。
WEB_OPENID = "web-user"


def set_web_reply_sink(fn):
    """注册网页版回执出口。

    @param fn 回调，签名 fn(text)；传 None 可注销。
    """
    global _web_reply_sink
    _web_reply_sink = fn


def _reply(qq_client, openid, text, markdown=False):
    """用当前窗口回复一条文本。

    msg_seq 通过 message_router.next_seq 统一分配：
    与推送路径共用同一个计数器，避免 (msg_id, msg_seq) 重复被 QQ 判重丢弃。
    组合指令执行期间（_reply_ctx.suppress 为真）静默跳过，只由组合层统一回执。
    markdown 为真时按 Markdown 消息发送（msg_type=2），供 /help 等富文本回执。
    来自网页版的指令（openid 为 web-user）改走网页回执出口，不发 QQ。
    """
    if getattr(_reply_ctx, "suppress", False):
        return False
    # 网页版：没有 QQ 客户端，把回执交给网页出口
    if openid == WEB_OPENID:
        if _web_reply_sink:
            try:
                _web_reply_sink(text)
            except Exception as e:
                log("网页回执失败：", e)
        return True
    # 按客户端能力分流：
    # QQ 必须持有「被动回复窗口」才能发送（窗口由用户消息打开，带 msg_id 与序号）；
    # 微信 / 企微直接投递，没有窗口概念。
    # 无脑走窗口检查会让另两条通道的每条指令都因「窗口已关闭」而静默失败。
    # 属性缺失时按「需要窗口」处理并告警：宁可走保守分支，也不让新通道
    # 因漏声明而误入无窗口路径、把消息发到不该去的地方。
    needs_window = getattr(qq_client, "needs_window", None)
    if needs_window is None:
        log("客户端未声明 needs_window，按需要窗口处理：", type(qq_client).__name__)
        needs_window = True
    if needs_window:
        msg_id, seq = message_router.next_seq(openid)
        if not msg_id:
            log("窗口已关闭，无法回复")
            return False
        ok, data = qq_client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq, markdown=markdown)
    else:
        ok, data = qq_client.send_c2c(openid, text)
    if not ok:
        log("回复失败：", data)
    return ok


def _maybe_attach_screenshot(payload, openid, screenshot):
    """按需给命令载荷挂上「自动截图回传」字段，返回是否挂了。

    页面操作类指令：动作执行完自动截图回传，便于在 QQ 端核对界面变化。
    组合指令执行期间（_reply_ctx.suppress）强制关闭，避免大量截图刷屏。
    @param payload    命令载荷（就地修改）
    @param openid     发起指令的用户
    @param screenshot 调用方是否要求截图
    @returns 是否挂上了截图回传
    """
    want_shot = bool(screenshot and openid and not getattr(_reply_ctx, "suppress", False))
    if want_shot:
        payload["request_id"] = _register_pending(openid)
        payload["auto_screenshot"] = True
    return want_shot


def _resolve_target(action, openid):
    """解析当前通道绑定的目标页面；取不到就回执失败并返回空串。

    所有下发入口（_dispatch / _dispatch_with_result）都必须先过这一关。
    抽成公共函数的理由：两个入口原先各自处理，_dispatch 有页面归属、
    _dispatch_with_result 则完全没有 target_page，卡片在总线里是公开的，
    任何页面的抽屉都能取走——比前者更危险。收在一处才不会再次分叉。

    @param action 动作名（仅用于日志）
    @param openid 发起指令的用户（失败回执的接收方）
    @returns {string} 目标页面地址；无法确定时返回空串（此时已发过失败回执）
    """
    import channel_binding
    channel = current_channel()
    target = channel_binding.get(channel) if channel else ""
    if target:
        return target
    why = ("当前通道未绑定页面" if channel else "指令来源通道未知")
    log("拒绝下发抽屉命令", action, "原因=" + why, "通道=" + (channel or "空"))
    # 失败必须让用户看得见。调用方在下发后普遍会紧跟一句「已下发：xxx」，
    # 那句是假回执——卡片根本没进总线。这里在下发层直接补一条明确的失败
    # 说明并带上绑定方法，用户才不会对着一句「已下发」干等。
    # 组合指令期间 suppress 为真，_reply 会静默跳过，由组合层统一回执。
    client = _client_for_channel(channel)
    try:
        _reply(client, openid,
               "指令未执行：%s。\n请先发 /bind 选择一个页面后再试。" % why)
    except Exception as e:
        log("失败回执发送异常：", e)
    return ""


def _client_for_channel(channel):
    """按通道名取对应的客户端实例，供失败回执使用。

    延迟导入避免与包初始化形成循环。QQ 用 bridge.client，企微 / 微信用各自客户端。
    网页版不受影响：openid 为 web-user 时 _reply 直接走网页出口，不碰客户端。

    @param channel 通道名（qq / wecom / weixin）
    @returns 客户端实例；取不到时为 None
    """
    try:
        # 注意：包内 bridge 是模块级单例对象（__init__.py 里 bridge = RemoteBridge()），
        # 不是子模块。写成 from . import bridge as m 再取 m.bridge 会去访问单例的
        # .bridge 属性，必然 AttributeError，失败回执就永远发不出去。
        # 用 import remote_bridge 后直接取模块属性，语义才正确。
        import remote_bridge
        inst = remote_bridge.bridge
        if channel == "wecom":
            return inst.wecom_client
        if channel == "weixin":
            return inst.wx_client
        return inst.client
    except Exception as e:
        log("取通道客户端失败：", e)
        return None


def _dispatch(action, params=None, openid="", screenshot=False):
    """把一条抽屉命令通过卡片总线下发。

    【隔离铁律】本函数是指令的唯一源头。指令面向用户（QQ / 网页），
    其卡片类型固定为 drawer-command、回执走 /api/bridge/result，
    【任何情况都不得流向 AI】——不产生工具卡片、不进 /tool、不回传 AI。
    与 AI 工具（走 external-call 卡片、结果回传 AI）是两条独立链路。
    详见 docs/command-tool-isolation.md。

    卡片类型为 drawer-command：抽屉轮询取到后按 action 执行本地动作，
    不发送给网页 AI。
    @param action 动作名：clear_all_sessions / clear_messages /
                  copy_system_prompt / toggle_auto_send / set_delay 等
    @param params 动作参数
    @param openid 发起指令的用户；需要截图回传时用于登记待回传请求
    @param screenshot 是否在动作执行后自动截一张图回传 QQ。
                      页面操作类指令用它在手机上观察界面结果；
                      组合指令执行期间（_reply_ctx.suppress）强制关闭，避免大量截图刷屏。
    """
    import delivery_queue
    # 页面归属：指令只投给「当前通道绑定的那个页面」，无目标页一律不下发。
    #
    # 为什么不再允许「未绑定就不限页面」：卡片总线的规则是 target_page 为空
    # 时任何页面的抽屉都能取走。多开网页时，卡片会被后台标签页抢先执行，
    # 用户眼前的页面毫无变化，手机上却收到「已执行」的回执；更糟的是指令
    # 落到了另一个 AI 站点，操作了完全不该动的页面。
    # 宁可失败也不兜底：找不到目标页就明确报错，让用户去绑定后再试。
    target = _resolve_target(action, openid)
    if not target:
        return None
    payload = {"action": action, "params": params or {}}
    payload["target_page"] = target
    want_shot = _maybe_attach_screenshot(payload, openid, screenshot)
    card = delivery_queue.command_bus.create(
        source="bridge",
        card_type="drawer-command",
        title="远程指令",
        content=json.dumps(payload, ensure_ascii=False),
        payload=payload,
        target_page=target,
    )
    log("已下发抽屉命令", action, "截图=" + ("是" if want_shot else "否"),
        "目标页=" + (target or "不限"), "id=" + card.id[:8])
    return card


def _register_pending(openid):
    """登记一个待回传请求，返回 request_id。

    用于「浏览器执行后要把结果发回 QQ」的指令（列会话 / 截屏）。
    """
    rid = str(uuid.uuid4())
    with _pending_lock:
        # 顺手清理超期请求
        now = time.time()
        for k in [k for k, v in _pending.items() if v.get("expire", 0) < now]:
            _pending.pop(k, None)
        _pending[rid] = {"openid": openid, "expire": now + PENDING_TTL}
    return rid


def take_pending(request_id):
    """取出并删除一个待回传请求；不存在或已过期返回 None。"""
    with _pending_lock:
        item = _pending.pop(request_id, None)
    if not item:
        return None
    if item.get("expire", 0) < time.time():
        return None
    return item


def _dispatch_with_result(action, params, openid):
    """下发一条需要回传结果的抽屉命令。

    与 _dispatch 的区别：额外带 request_id，浏览器执行完把结果 POST 回来，
    后端据此找回 openid 并转发到 QQ。
    """
    import delivery_queue
    # 页面归属：与 _dispatch 同一把关。此前这里完全没设 target_page，
    # 卡片在总线里是公开的，任何页面的抽屉都能取走——比 _dispatch 的旧行为更危险。
    # 无目标页时 _resolve_target 已发过失败回执，这里直接返回。
    target = _resolve_target(action, openid)
    if not target:
        return None
    rid = _register_pending(openid)
    payload = {"action": action, "params": params or {}, "request_id": rid,
               "target_page": target}
    card = delivery_queue.command_bus.create(
        source="bridge",
        card_type="drawer-command",
        title="远程指令",
        content=json.dumps(payload, ensure_ascii=False),
        payload=payload,
        target_page=target,
    )
    log("已下发抽屉命令（待回传）", action, "id=" + card.id[:8], "rid=" + rid[:8])
    return card
