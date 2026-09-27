"""远程桥接 —— QQ 指令处理与指令面板注册

职责：
1. 处理以「/」开头的 QQ 消息
2. 内置指令：通过卡片总线下发到抽屉执行
   （清空会话 / 消息、复制 System Prompt、设置回传延迟）
3. 自定义指令：点击用户预先选定的网页元素

设计说明：
- 指令的「执行」都在浏览器侧完成——会话数据、System Prompt、
  网页元素都在抽屉与页面里，后端只负责识别指令、下发命令。
- 下发通道复用卡片总线：创建一张 type=drawer-command 的卡片，
  抽屉轮询取到后按 action 执行，而非发送给网页 AI。

【待核对】指令面板与自定义菜单的接口路径、请求体结构以官方文档为准。
"""
import json
import os
import threading
import time
import uuid

from . import bridge_store, message_router

# 待回传请求表：{ request_id: {openid, expire} }
# 有些指令（列会话 / 截屏）需要浏览器执行后把结果回传，再转发到 QQ。
# 这里登记请求，浏览器完成后按 request_id 找回 openid，用被动回复发出。
_pending = {}
_pending_lock = threading.Lock()
PENDING_TTL = 60  # 请求有效期（秒），超时未回传则丢弃


def log(*args):
    """统一前缀打印。"""
    print("[bridge][command]", *args)


# 内置指令表：命令名 → 说明
BUILTIN = {
    "/css": "清空所有会话",
    "/cms": "清空当前会话的消息列表",
    "/csp": "复制 System Prompt 并发送给 AI",
    "/rtime": "设置自动回传延迟（秒）",
    "/stime": "切换自动回传开关",
    "/sessions": "列出会话列表",
    "/ss": "按序号切换会话（如 /ss 1）",
    "/screenshot": "截取浏览器屏幕（同 /sp）",
    "/sp": "截取浏览器屏幕（/screenshot 快捷）",
    "/copy": "复制最新卡片结果并回传 AI",
    "/reparse": "重新解析当前网页对话",
    "/rerun": "重新执行最新卡片并回传",
    "/restart": "重启服务端",
    "/refush": "刷新浏览器并打开抽屉",
    "/help": "显示指令列表",
}


def _reply(qq_client, openid, text):
    """用当前窗口回复一条文本。

    msg_seq 通过 message_router.next_seq 统一分配：
    与推送路径共用同一个计数器，避免 (msg_id, msg_seq) 重复被 QQ 判重丢弃。
    """
    msg_id, seq = message_router.next_seq(openid)
    if not msg_id:
        log("窗口已关闭，无法回复")
        return False
    ok, data = qq_client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq)
    if not ok:
        log("回复失败：", data)
    return ok


def _dispatch(action, params=None):
    """把一条抽屉命令通过卡片总线下发。

    卡片类型为 drawer-command：抽屉轮询取到后按 action 执行本地动作，
    不发送给网页 AI。
    @param action 动作名：clear_all_sessions / clear_messages /
                  copy_system_prompt / toggle_auto_send / set_delay / click_element
    @param params 动作参数
    """
    import card_bus
    payload = {"action": action, "params": params or {}}
    card = card_bus.bus.create(
        source="bridge",
        card_type="drawer-command",
        title="远程指令",
        content=json.dumps(payload, ensure_ascii=False),
        payload=payload,
    )
    log("已下发抽屉命令", action, "id=" + card.id[:8])
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


def _restart_server(delay=1.5):
    """重启当前服务进程。

    做法：起一个独立子进程，让它先等一会儿（等父进程退出、端口释放），
    再以同样的解释器与参数重执行服务；父进程随即退出。

    为什么不用 os.execv 原地重执行：execv 会继承已打开的 fd，
    包括监听 5000 端口的 socket。新进程带着这个 socket 再去 bind 同一端口，
    会因「地址已占用」失败，服务当场失联——这正是上一版 /restart 把服务
    搞挂的原因。改用独立子进程 + close_fds，彻底避开 fd 继承。
    """
    import subprocess
    import sys
    # 子进程要执行的代码：等待 → 用原解释器与原参数 execv 自身
    child_code = (
        "import time, os, sys;"
        "time.sleep(%s);"
        "os.execv(sys.executable, [sys.executable] + %r)"
    ) % (delay, list(sys.argv))
    try:
        subprocess.Popen(
            [sys.executable, "-c", child_code],
            cwd=os.getcwd(),
            close_fds=True,           # 不继承监听 socket，避免端口占用
            start_new_session=True,   # 脱离当前会话，父进程退出不影响它
        )
    except Exception as e:
        log("重启失败：", e)
        return
    # 父进程立即退出：释放端口与所有资源，交给子进程拉起新服务。
    # 用 _exit 而非 exit：跳过清理钩子，避免与子进程启动竞争。
    os._exit(0)


def _help_text():
    """组装指令列表文本。"""
    lines = ["可用指令："]
    for name, desc in BUILTIN.items():
        lines.append("%s — %s" % (name, desc))
    for c in (bridge_store.get_config().get("commands") or []):
        lines.append("%s — %s" % (c.get("name", ""), c.get("label", "")))
    return "\n".join(lines)


def handle_command(qq_client, openid, msg_id, text):
    """处理一条指令消息。返回 True 表示已处理（不再当普通消息投递）。"""
    parts = text.strip().split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/css":
        _dispatch("clear_all_sessions")
        _reply(qq_client, openid, "已下发：清空所有会话")
        return True
    if cmd == "/cms":
        _dispatch("clear_messages")
        _reply(qq_client, openid, "已下发：清空当前会话的消息列表")
        return True
    if cmd == "/stime":
        _dispatch("toggle_auto_send")
        _reply(qq_client, openid, "已下发：切换自动回传开关")
        return True
    if cmd == "/sessions":
        _dispatch_with_result("list_sessions", {}, openid)
        return True
    if cmd == "/ss":
        if not arg:
            _reply(qq_client, openid, "用法：/ss 序号（序号来自 /sessions）")
            return True
        try:
            idx = int(arg.strip())
        except ValueError:
            _reply(qq_client, openid, "序号必须是整数")
            return True
        if idx <= 0:
            _reply(qq_client, openid, "序号必须大于 0")
            return True
        _dispatch("switch_session", {"index": idx})
        _reply(qq_client, openid, "已下发：切换会话 #%d" % idx)
        return True
    if cmd == "/screenshot" or cmd == "/sp":
        _dispatch_with_result("screenshot", {}, openid)
        return True
    if cmd == "/copy":
        _dispatch("copy_latest", {})
        _reply(qq_client, openid, "已下发：复制最新结果并回传")
        return True
    if cmd == "/reparse":
        _dispatch("reparse", {})
        _reply(qq_client, openid, "已下发：重新解析对话")
        return True
    if cmd == "/rerun":
        _dispatch("rerun_latest", {})
        _reply(qq_client, openid, "已下发：重新执行最新卡片")
        return True
    if cmd == "/restart":
        _reply(qq_client, openid, "正在重启服务端…")
        _restart_server()
        return True
    if cmd == "/refush":
        _dispatch("refresh_page", {})
        _reply(qq_client, openid, "已下发：刷新浏览器并打开抽屉")
        return True
    if cmd == "/csp":
        _dispatch("copy_system_prompt")
        _reply(qq_client, openid, "已下发：复制 System Prompt 并发送给 AI")
        return True
    if cmd == "/rtime":
        if not arg:
            _reply(qq_client, openid, "用法：/rtime 秒数（如 /rtime 5）")
            return True
        try:
            secs = float(arg)
        except ValueError:
            _reply(qq_client, openid, "秒数必须是数字")
            return True
        if secs <= 0:
            _reply(qq_client, openid, "秒数必须大于 0")
            return True
        _dispatch("set_delay", {"seconds": secs})
        _reply(qq_client, openid, "已下发：设置自动回传延迟 %s 秒" % secs)
        return True
    if cmd == "/help":
        _reply(qq_client, openid, _help_text())
        return True

    # 自定义指令：在配置里按命令名匹配，命中则下发「点击元素」。
    # 用 _dispatch_with_result：元素可能找不到或不唯一，失败时要在 QQ 里提示。
    for c in (bridge_store.get_config().get("commands") or []):
        if (c.get("name") or "").lower() == cmd:
            _dispatch_with_result("click_element", {
                "selector": c.get("selector", ""),
                "page_url": c.get("page_url", ""),
            }, openid)
            return True

    # 未命中任何指令：交还调用方当普通消息处理
    return False


def register_panel(qq_client):
    """把配置的指令注册到 QQ 指令面板 / 自定义菜单。

    【待核对】接口路径与请求体以官方文档为准。
    本函数在桥接启动时调用；失败仅记录，不影响消息收发。
    """
    cfg = bridge_store.get_config()
    commands = []
    for name, desc in BUILTIN.items():
        commands.append({"name": name, "desc": desc})
    for c in (cfg.get("commands") or []):
        commands.append({"name": c.get("name", ""), "desc": c.get("label", "")})
    if not commands:
        return
    # [待核对] 注册接口：此处仅打印待注册内容，接入时替换为真实 HTTP 调用
    log("待注册指令面板：", json.dumps(commands, ensure_ascii=False))
