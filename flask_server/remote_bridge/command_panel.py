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


# 内置指令表：完整命令名 → { desc 说明, aliases 快捷键列表 }
#
# 命名规则：主命令用完整英文名（如 /clear-sessions），快捷键作别名（如 /css）。
# 展示格式统一为「快捷键 — 描述（完整名）」，见 _help_text。
BUILTIN = {
    "/clear-sessions": {"desc": "清空所有会话", "aliases": ["/css"]},
    "/clear-messages": {"desc": "清空当前会话的消息列表", "aliases": ["/cms"]},
    "/copy-system-prompt": {"desc": "复制 System Prompt 并发送给 AI", "aliases": ["/csp"]},
    "/re-time": {"desc": "设置自动回传延迟（秒）", "aliases": ["/rt"]},
    "/switch-auto": {"desc": "自动回传开关（/sa on|off，不带则切换）", "aliases": ["/sa"]},
    "/sessions": {"desc": "列出会话列表", "aliases": ["/ls"]},
    "/switch-session": {"desc": "按序号切换会话（如 /ss 1）", "aliases": ["/ss"]},
    "/screenshot": {"desc": "截取浏览器屏幕", "aliases": ["/sp"]},
    "/copy": {"desc": "复制最新卡片结果并回传 AI", "aliases": ["/cp"]},
    "/reparse": {"desc": "重新解析当前网页对话", "aliases": ["/rp"]},
    "/rerun": {"desc": "重新执行最新卡片并回传", "aliases": ["/rr"]},
    "/restart": {"desc": "重启服务端", "aliases": ["/rs"]},
    "/refush": {"desc": "刷新浏览器并打开抽屉", "aliases": ["/rf"]},
    "/help": {"desc": "显示指令列表", "aliases": ["/h"]},
}

# 别名 → 主命令 的反查表：一次构建，之后直接查
_ALIAS_MAP = {}
for _main, _info in BUILTIN.items():
    for _a in _info.get("aliases") or []:
        _ALIAS_MAP[_a] = _main


def resolve_cmd(cmd):
    """把别名解析为主命令名；非别名原样返回。"""
    if cmd in BUILTIN:
        return cmd
    return _ALIAS_MAP.get(cmd, cmd)


# 线程局部标记：组合指令执行期间的中间步骤，回复会被抑制，避免刷屏。
_reply_ctx = threading.local()


def _reply(qq_client, openid, text):
    """用当前窗口回复一条文本。

    msg_seq 通过 message_router.next_seq 统一分配：
    与推送路径共用同一个计数器，避免 (msg_id, msg_seq) 重复被 QQ 判重丢弃。
    组合指令执行期间（_reply_ctx.suppress 为真）静默跳过，只由组合层统一回执。
    """
    if getattr(_reply_ctx, "suppress", False):
        return False
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


def _restart_server(delay=3.0):
    """延迟 3 秒重启服务（最简实现）。

    步骤：
      1. 起一个与父进程彻底脱离的子进程，让它 sleep 3 秒后启动新服务；
      2. 父进程立即退出，把端口让出来。

    关键：Windows 上必须用 DETACHED_PROCESS 才能真脱离。
    之前的 start_new_session 在 Windows 上是空操作，子进程会随父进程一起
    被终止，新服务起不来、端口无人监听，抽屉所有接口随之全断。
    """
    import subprocess
    import sys
    # 子进程：等 3 秒 → 用原解释器与原参数 execv 启动服务
    code = "import time,os,sys;time.sleep(%s);os.execv(sys.executable,%r)" % (
        delay, [sys.executable] + list(sys.argv))
    kw = {
        "cwd": os.getcwd(),
        "close_fds": True,                 # 不继承监听 socket，避免端口被占
        "stdin": subprocess.DEVNULL,       # 与控制台解耦
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kw["creationflags"] = 0x00000008   # DETACHED_PROCESS：真正脱离父进程
    else:
        kw["start_new_session"] = True
    subprocess.Popen([sys.executable, "-c", code], **kw)
    # 父进程立即退出，端口让给 3 秒后的新进程
    os._exit(0)


def _run_combo(qq_client, openid, msg_id, entry):
    """执行一条组合指令：按顺序逐条执行 steps，每条间隔 1 秒。

    中间步骤的回复被抑制（_reply_ctx.suppress），只在开头与结尾各回一条，
    避免多条指令叠加后把 QQ 刷屏。执行放在后台线程，不阻塞 WebSocket 回调。
    @param entry 组合指令对象，含 steps（指令文本数组）
    """
    steps = [s for s in (entry.get("steps") or []) if str(s).strip()]
    label = entry.get("label") or entry.get("name") or "组合"
    if not steps:
        _reply(qq_client, openid, "组合指令「%s」没有步骤" % label)
        return
    _reply(qq_client, openid, "开始执行「%s」，共 %d 步" % (label, len(steps)))

    def _worker():
        _reply_ctx.suppress = True
        ok = 0
        try:
            for i, s in enumerate(steps):
                try:
                    # 递归复用统一的指令处理；组合中不再嵌套组合（避免递归失控）
                    handle_command(qq_client, openid, msg_id, str(s).strip())
                    ok += 1
                except Exception as e:
                    log("组合步骤失败：", s, e)
                # 最后一步不必再等
                if i < len(steps) - 1:
                    time.sleep(1.0)
        finally:
            _reply_ctx.suppress = False
        _reply(qq_client, openid, "「%s」执行完毕（%d/%d 步）" % (label, ok, len(steps)))

    threading.Thread(target=_worker, daemon=True).start()


def _help_text():
    """组装指令列表文本。格式统一为「快捷键 — 描述（完整名）」。

    每个指令都有快捷键（aliases）。若某指令没有别名，就直接显示完整名。
    """
    lines = ["可用指令："]
    for name, info in BUILTIN.items():
        al = info.get("aliases") or []
        short = al[0] if al else name          # 取首个快捷键作为展示主键
        if short != name:
            lines.append("%s — %s（%s）" % (short, info.get("desc", ""), name))
        else:
            lines.append("%s — %s" % (name, info.get("desc", "")))
    customs = bridge_store.get_config().get("commands") or []
    if customs:
        lines.append("")
        lines.append("自定义指令：")
        for c in customs:
            tag = "[组合] " if c.get("steps") else ""
            lines.append("%s — %s%s" % (c.get("name", ""), tag, c.get("label", "")))
    return "\n".join(lines)


def handle_command(qq_client, openid, msg_id, text):
    """处理一条指令消息。返回 True 表示已处理（不再当普通消息投递）。"""
    parts = text.strip().split(None, 1)
    # 先解析别名：/sp → /screenshot、/ls → /sessions 等，
    # 之后的分支一律按主命令名判断。
    cmd = resolve_cmd(parts[0].lower())
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/clear-sessions":
        _dispatch("clear_all_sessions")
        _reply(qq_client, openid, "已下发：清空所有会话")
        return True
    if cmd == "/clear-messages":
        _dispatch("clear_messages")
        _reply(qq_client, openid, "已下发：清空当前会话的消息列表")
        return True
    if cmd == "/switch-auto":
        # 支持显式指定开关：/sa on、/sa off；不带参数则切换。
        # 显式形式在组合指令里更可靠——切换执行两次等于没执行，
        # 而 on/off 是幂等的，重跑结果一致。
        a = (arg or "").strip().lower()
        if a in ("on", "1", "true", "开", "开启"):
            _dispatch("set_auto_send", {"on": True})
            _reply(qq_client, openid, "已下发：开启自动回传")
        elif a in ("off", "0", "false", "关", "关闭"):
            _dispatch("set_auto_send", {"on": False})
            _reply(qq_client, openid, "已下发：关闭自动回传")
        elif a == "":
            _dispatch("toggle_auto_send")
            _reply(qq_client, openid, "已下发：切换自动回传开关")
        else:
            _reply(qq_client, openid, "用法：/sa [on|off]，不带参数则切换")
        return True
    if cmd == "/sessions":
        _dispatch_with_result("list_sessions", {}, openid)
        return True
    if cmd == "/switch-session":
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
    if cmd == "/screenshot":
        # 别名 /sp 已在入口经 resolve_cmd 归一为此命令
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
    if cmd == "/copy-system-prompt":
        _dispatch("copy_system_prompt")
        _reply(qq_client, openid, "已下发：复制 System Prompt 并发送给 AI")
        return True
    if cmd == "/re-time":
        if not arg:
            _reply(qq_client, openid, "用法：/rt 秒数（如 /rt 5）")
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

    # 自定义指令：按命令名或别名匹配。
    # 两类：
    #  · 组合指令（含 steps）：逐条执行其指令列表，间隔 1 秒；
    #  · 点击指令：下发「点击元素」，失败时在 QQ 里提示。
    for c in (bridge_store.get_config().get("commands") or []):
        names = [c.get("name") or ""] + (c.get("aliases") or [])
        if cmd not in [str(n).lower() for n in names if n]:
            continue
        steps = c.get("steps") or []
        if steps:
            _run_combo(qq_client, openid, msg_id, c)
        else:
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
    # 内置：只注册主命令，别名不重复占位（QQ 面板最多 20 个元素）
    for name, info in BUILTIN.items():
        commands.append({"name": name, "desc": info.get("desc", "")})
    # 自定义：组合与点击指令一并注册
    for c in (cfg.get("commands") or []):
        tag = "[组合] " if (c.get("steps") or []) else ""
        commands.append({"name": c.get("name", ""), "desc": tag + (c.get("label") or "")})
    if not commands:
        return
    # [待核对] 注册接口：此处仅打印待注册内容，接入时替换为真实 HTTP 调用
    log("待注册指令面板：", json.dumps(commands, ensure_ascii=False))
