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

from . import message_router

# 待回传请求表：{ request_id: {openid, expire} }
# 有些指令（列会话 / 截屏）需要浏览器执行后把结果回传，再转发到 QQ。
# 这里登记请求，浏览器完成后按 request_id 找回 openid，用被动回复发出。
_pending = {}
_pending_lock = threading.Lock()
PENDING_TTL = 60  # 请求有效期（秒），超时未回传则丢弃


def log(*args):
    """统一前缀打印。"""
    print("[bridge][command]", *args)


# 线程局部标记：组合指令执行期间的中间步骤，回复会被抑制，避免刷屏。
_reply_ctx = threading.local()


def _reply(qq_client, openid, text, markdown=False):
    """用当前窗口回复一条文本。

    msg_seq 通过 message_router.next_seq 统一分配：
    与推送路径共用同一个计数器，避免 (msg_id, msg_seq) 重复被 QQ 判重丢弃。
    组合指令执行期间（_reply_ctx.suppress 为真）静默跳过，只由组合层统一回执。
    markdown 为真时按 Markdown 消息发送（msg_type=2），供 /help 等富文本回执。
    """
    if getattr(_reply_ctx, "suppress", False):
        return False
    msg_id, seq = message_router.next_seq(openid)
    if not msg_id:
        log("窗口已关闭，无法回复")
        return False
    ok, data = qq_client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq, markdown=markdown)
    if not ok:
        log("回复失败：", data)
    return ok


def _dispatch(action, params=None, openid="", screenshot=False):
    """把一条抽屉命令通过卡片总线下发。

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
    import card_bus
    payload = {"action": action, "params": params or {}}
    # 页面操作类指令：动作执行完自动截图回传，便于在 QQ 端核对界面变化。
    want_shot = bool(screenshot and openid and not getattr(_reply_ctx, "suppress", False))
    if want_shot:
        payload["request_id"] = _register_pending(openid)
        payload["auto_screenshot"] = True
    card = card_bus.bus.create(
        source="bridge",
        card_type="drawer-command",
        title="远程指令",
        content=json.dumps(payload, ensure_ascii=False),
        payload=payload,
    )
    log("已下发抽屉命令", action, "截图=" + ("是" if want_shot else "否"), "id=" + card.id[:8])
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
    import card_bus
    rid = _register_pending(openid)
    payload = {"action": action, "params": params or {}, "request_id": rid}
    card = card_bus.bus.create(
        source="bridge",
        card_type="drawer-command",
        title="远程指令",
        content=json.dumps(payload, ensure_ascii=False),
        payload=payload,
    )
    log("已下发抽屉命令（待回传）", action, "id=" + card.id[:8], "rid=" + rid[:8])
    return card
