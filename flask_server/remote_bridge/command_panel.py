"""远程桥接 —— QQ 指令处理与执行

职责：
1. 处理以「/」开头的 QQ 消息
2. 内置指令：通过卡片总线下发到抽屉执行
   （清空会话 / 消息、复制 System Prompt、设置回传延迟等）
3. 自定义指令：点击用户预先选定的网页元素，或按序执行组合指令
4. 需要回传结果的指令（列会话 / 截屏）：登记待回传请求，
   等浏览器 POST 回来后再转发到 QQ

设计说明：
- 指令的「执行」都在浏览器侧完成——会话数据、System Prompt、
  网页元素都在抽屉与页面里，后端只负责识别指令、下发命令。
- 下发通道复用卡片总线：创建一张 type=drawer-command 的卡片，
  抽屉轮询取到后按 action 执行，而非发送给网页 AI。
- 指令表、别名解析、合法性校验与面板注册在 command_registry.py；
  本模块只负责「指令怎么执行」。

内置指令采用表驱动：命令名 → 处理函数，见 _BUILTIN_HANDLERS。
新增内置指令只需写一个处理函数并登记到表中，无需改动分发逻辑。
"""
import json
import os
import threading
import time
import uuid

from . import bridge_store, message_router
# 指令表与静态知识来自 command_registry；register_panel / validate_command
# 在此重导出，保持 __init__.py 与 routes/bridge.py 的既有引用不变。
from .command_registry import (
    BUILTIN, resolve_cmd, help_text, register_panel, validate_command,
)

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
                  copy_system_prompt / toggle_auto_send / set_delay 等
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


def _combo_interval(entry):
    """取组合指令的步骤间隔（秒）。

    读 entry.interval，未配置或非法时用默认 1 秒；下限 0.2 秒，
    避免配置成 0 导致步骤挤在一起、抽屉来不及响应。
    """
    try:
        interval = float(entry.get("interval", 1.0))
    except (TypeError, ValueError):
        interval = 1.0
    return max(0.2, interval)


def _run_combo_steps(qq_client, openid, msg_id, steps, interval):
    """在抑制回复的状态下逐步执行组合指令，返回成功步数。"""
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
                time.sleep(interval)
    finally:
        _reply_ctx.suppress = False
    return ok


def _run_combo(qq_client, openid, msg_id, entry):
    """执行一条组合指令：按顺序逐条执行 steps，每条间隔若干秒。

    中间步骤的回复被抑制（_reply_ctx.suppress），只在开头与结尾各回一条，
    避免多条指令叠加后把 QQ 刷屏。执行放在后台线程，不阻塞 WebSocket 回调。
    @param entry 组合指令对象，含 steps（指令文本数组）
    """
    steps = [s for s in (entry.get("steps") or []) if str(s).strip()]
    label = entry.get("label") or entry.get("name") or "组合"
    if not steps:
        _reply(qq_client, openid, "组合指令「%s」没有步骤" % label)
        return
    interval = _combo_interval(entry)
    _reply(qq_client, openid, "开始执行「%s」，共 %d 步，间隔 %.1f 秒"
           % (label, len(steps), interval))

    def _worker():
        ok = _run_combo_steps(qq_client, openid, msg_id, steps, interval)
        _reply(qq_client, openid, "「%s」执行完毕（%d/%d 步）" % (label, ok, len(steps)))

    threading.Thread(target=_worker, daemon=True).start()


# ---------- 内置指令处理函数 ----------
# 每个函数对应一条内置指令，签名统一为 (qq_client, openid, arg, msg_id)。
# 返回 None 即可；需要即时回执的自行调用 _reply。

def _h_clear_sessions(qq_client, openid, arg, msg_id):
    """清空所有会话。"""
    _dispatch("clear_all_sessions")
    _reply(qq_client, openid, "已下发：清空所有会话")


def _h_clear_messages(qq_client, openid, arg, msg_id):
    """清空当前会话的消息列表。"""
    _dispatch("clear_messages")
    _reply(qq_client, openid, "已下发：清空当前会话的消息列表")


def _h_copy_system_prompt(qq_client, openid, arg, msg_id):
    """复制 System Prompt 并发送给 AI。"""
    _dispatch("copy_system_prompt")
    _reply(qq_client, openid, "已下发：复制 System Prompt 并发送给 AI")


def _h_switch_auto(qq_client, openid, arg, msg_id):
    """自动回传开关：/sa on、/sa off，不带参数则切换。

    显式形式在组合指令里更可靠——切换执行两次等于没执行，
    而 on/off 是幂等的，重跑结果一致。
    """
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


def _h_re_time(qq_client, openid, arg, msg_id):
    """设置自动回传延迟（秒）。"""
    if not arg:
        _reply(qq_client, openid, "用法：/rt 秒数（如 /rt 5）")
        return
    try:
        secs = float(arg)
    except ValueError:
        _reply(qq_client, openid, "秒数必须是数字")
        return
    if secs <= 0:
        _reply(qq_client, openid, "秒数必须大于 0")
        return
    _dispatch("set_delay", {"seconds": secs})
    _reply(qq_client, openid, "已下发：设置自动回传延迟 %s 秒" % secs)


def _h_sessions(qq_client, openid, arg, msg_id):
    """列出会话列表（需浏览器回传结果）。"""
    _dispatch_with_result("list_sessions", {}, openid)


def _h_switch_session(qq_client, openid, arg, msg_id):
    """按序号切换会话（如 /ss 1）。"""
    if not arg:
        _reply(qq_client, openid, "用法：/ss 序号（序号来自 /sessions）")
        return
    try:
        idx = int(arg.strip())
    except ValueError:
        _reply(qq_client, openid, "序号必须是整数")
        return
    if idx <= 0:
        _reply(qq_client, openid, "序号必须大于 0")
        return
    _dispatch("switch_session", {"index": idx})
    _reply(qq_client, openid, "已下发：切换会话 #%d" % idx)


def _h_screenshot(qq_client, openid, arg, msg_id):
    """截取浏览器屏幕（需浏览器回传结果）。"""
    _dispatch_with_result("screenshot", {}, openid)


def _h_copy(qq_client, openid, arg, msg_id):
    """复制最新卡片结果并回传 AI。"""
    _dispatch("copy_latest", {})
    _reply(qq_client, openid, "已下发：复制最新结果并回传")


def _h_reparse(qq_client, openid, arg, msg_id):
    """重新解析当前网页对话。"""
    _dispatch("reparse", {})
    _reply(qq_client, openid, "已下发：重新解析对话")


def _h_rerun(qq_client, openid, arg, msg_id):
    """重新执行最新卡片并回传。"""
    _dispatch("rerun_latest", {})
    _reply(qq_client, openid, "已下发：重新执行最新卡片")


def _h_restart(qq_client, openid, arg, msg_id):
    """重启服务端：先回执再重启（进程随后退出）。"""
    _reply(qq_client, openid, "正在重启服务端…")
    _restart_server()


def _h_md(qq_client, openid, arg, msg_id):
    """采集当前 AI 回复的 Markdown 原文（手动触发一次）。"""
    sel = bridge_store.get_config().get("md_selector") or ""
    if not sel:
        _reply(qq_client, openid, "未配置 Markdown 选择器（设置页可填）"); return
    _dispatch("collect_md", {"selector": sel})
    _reply(qq_client, openid, "已下发：采集 Markdown")


def _h_refush(qq_client, openid, arg, msg_id):
    """刷新浏览器并打开抽屉。"""
    _dispatch("refresh_page", {})
    _reply(qq_client, openid, "已下发：刷新浏览器并打开抽屉")


def _h_help(qq_client, openid, arg, msg_id):
    """显示指令列表。"""
    _reply(qq_client, openid, help_text())


# 内置指令分发表：主命令名 → 处理函数。
# 命令名与说明集中在 command_registry.BUILTIN，此处只登记执行入口，
# 两张表的键必须一致（由 _check_handler_table 在导入时自检）。
_BUILTIN_HANDLERS = {
    "/clear-sessions": _h_clear_sessions,
    "/clear-messages": _h_clear_messages,
    "/copy-system-prompt": _h_copy_system_prompt,
    "/re-time": _h_re_time,
    "/switch-auto": _h_switch_auto,
    "/sessions": _h_sessions,
    "/switch-session": _h_switch_session,
    "/screenshot": _h_screenshot,
    "/copy": _h_copy,
    "/reparse": _h_reparse,
    "/rerun": _h_rerun,
    "/restart": _h_restart,
    "/refush": _h_refush,
    "/md": _h_md,
    "/help": _h_help,
}


def _check_handler_table():
    """导入时自检：指令表与处理函数表的命令名必须一一对应。

    两张表分离后，新增指令若只改了一处就会「可见但不可用」（或反之），
    这种错配在运行时才暴露会很难查，故在导入期直接报错拦住。
    """
    missing = sorted(set(BUILTIN) - set(_BUILTIN_HANDLERS))
    extra = sorted(set(_BUILTIN_HANDLERS) - set(BUILTIN))
    if missing or extra:
        raise RuntimeError(
            "内置指令表与处理函数表不一致：缺少处理函数 %s；多余处理函数 %s"
            % (missing or "无", extra or "无")
        )


_check_handler_table()


def _match_custom(cmd):
    """按命令名或别名查找自定义指令；未命中返回 None。"""
    for c in (bridge_store.get_config().get("commands") or []):
        names = [c.get("name") or ""] + (c.get("aliases") or [])
        if cmd in [str(n).lower() for n in names if n]:
            return c
    return None


def _run_custom(qq_client, openid, msg_id, entry):
    """执行一条自定义指令：组合 / 采集 / 点击三类。

    - 组合（含 steps）：逐条执行其指令列表
    - 采集（collect 为真）：点按钮取 Markdown，挂到最新 AI 消息上
    - 点击：下发点击元素，并把结果回传 QQ
    """
    if entry.get("steps"):
        _run_combo(qq_client, openid, msg_id, entry)
        return
    if entry.get("collect"):
        # 采集类：点按钮取 Markdown，内容留给后续推送用，不回传 QQ
        _dispatch("collect_md", {"selector": entry.get("selector", "")})
        _reply(qq_client, openid, "已下发：采集 Markdown 原文")
        return
    _dispatch_with_result("click_element", {
        "selector": entry.get("selector", ""),
        "page_url": entry.get("page_url", ""),
    }, openid)


def _handle_custom(qq_client, openid, msg_id, cmd):
    """按命令名或别名匹配自定义指令。命中返回 True，未命中返回 False。"""
    entry = _match_custom(cmd)
    if not entry:
        return False
    _run_custom(qq_client, openid, msg_id, entry)
    return True


def handle_command(qq_client, openid, msg_id, text):
    """处理一条指令消息。返回 True 表示已处理（不再当普通消息投递）。

    流程：解析出命令名与参数 → 先查内置指令表 → 再查自定义指令。
    别名（/sp → /screenshot 等）在解析阶段归一为主命令名。
    """
    parts = text.strip().split(None, 1)
    cmd = resolve_cmd(parts[0].lower())
    arg = parts[1] if len(parts) > 1 else ""
    fn = _BUILTIN_HANDLERS.get(cmd)
    if fn:
        fn(qq_client, openid, arg, msg_id)
        return True
    # 未命中内置指令：尝试自定义指令；仍未命中则交还调用方当普通消息处理
    return _handle_custom(qq_client, openid, msg_id, cmd)
