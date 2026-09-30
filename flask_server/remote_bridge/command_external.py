"""远程桥接 —— 外部指令处理

外部指令来自 skill 的 tool.json 声明（见 custom_tools/commands.py），
由对应扩展自己轮询执行；宿主只负责识别与转发，不介入扩展内部。

本模块从 command_panel.py 抽出，使其保持在行数上限内。
依赖单向：command_panel 引用本模块，本模块不反向引用它。
"""
import threading

from .command_dispatch import _reply, log


def _reply_external_result(qq_client, openid, cmd, ok, data):
    """把外部指令的执行结果回执到 QQ（只做成功 / 失败两态）。

    外部指令由扩展自己执行，结果形态由扩展决定；这里只做「成功 / 失败」
    两态回执，附上可读文本，避免把原始 dict 直接抛给用户。
    """
    if not ok:
        _reply(qq_client, openid, "指令 %s 未在时限内执行（扩展未打开或未在目标页）" % cmd)
        return
    if isinstance(data, dict):
        if data.get("success") is False:
            err = data.get("error") or data.get("message") or "执行失败"
            _reply(qq_client, openid, "指令 %s 执行失败：%s" % (cmd, err))
            return
        msg = data.get("message") or data.get("text") or ""
    else:
        msg = ""
    _reply(qq_client, openid, "已执行：%s%s" % (cmd, ("，" + msg) if msg else ""))


def _run_external_command(qq_client, openid, cmd_entry):
    """执行一条外部指令：后台线程调 hub.dispatch，等结果回执。

    必须放后台线程：dispatch 会阻塞等待扩展取走（上限 FORWARD_TIMEOUT），
    若在 WebSocket 回调线程里同步等待，会把整条消息处理线卡住。
    """
    import external_tools
    provider = cmd_entry.get("provider") or ""
    tool = cmd_entry.get("tool") or ""
    params = cmd_entry.get("params") or {}
    cmd_name = cmd_entry.get("name") or ""
    if not provider or not tool:
        _reply(qq_client, openid, "指令 %s 声明不完整（缺 provider / tool）" % cmd_name)
        return
    # 先回执「已下发」，让用户即时得到反馈；最终结果由后台线程补发。
    _reply(qq_client, openid, "已下发：%s" % (cmd_entry.get("desc") or cmd_name))

    def _worker():
        try:
            ok, data = external_tools.hub.dispatch(provider, tool, params)
        except Exception as e:
            log("外部指令执行异常：", cmd_name, e)
            _reply(qq_client, openid, "指令 %s 执行异常" % cmd_name)
            return
        _reply_external_result(qq_client, openid, cmd_name, ok, data)

    threading.Thread(target=_worker, daemon=True).start()


def handle_external(qq_client, openid, msg_id, cmd):
    """尝试按外部指令处理：命中返回 True，未命中返回 False。

    外部指令来自 skill 的 tool.json 声明，由对应扩展自己执行，
    宿主只负责识别与转发（见 custom_tools/commands.py）。
    """
    try:
        import custom_tools.commands as ext_cmds
        entry = ext_cmds.resolve_external_command(cmd)
    except Exception as e:
        log("读取外部指令失败：", e)
        return False
    if not entry:
        return False
    _run_external_command(qq_client, openid, entry)
    return True
