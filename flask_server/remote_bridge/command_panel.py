"""远程桥接 —— QQ 指令处理与指令面板注册

职责：
1. 处理以「/」开头的 QQ 消息，按类型分流：
   - 控制类（/start /stop）：切换桥接层开关
   - 查询类（/status）：读本地状态直接回复
   - 转发类（/ask 内容）：包装成卡片投给网页 AI
   - 工具类（/run 工具 参数）：经外部工具提供方通道下发
2. 把设置页配置的指令列表注册到 QQ 的指令面板 / 自定义菜单

【待核对】指令面板与自定义菜单的接口路径、请求体结构以官方文档为准，
本文件按通行结构实现，接入前请对照官网确认。
"""
import json

from . import bridge_store, message_router


def log(*args):
    """统一前缀打印。"""
    print("[bridge][command]", *args)


# 内置指令：不依赖设置页配置即可用
BUILTIN = {
    "/start": "开启消息推送",
    "/stop": "暂停消息推送",
    "/status": "查看当前状态",
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


def _status_text():
    """组装当前状态文本。"""
    cfg = bridge_store.get_config()
    push = cfg.get("push") or {}
    lines = [
        "桥接状态：" + ("开启" if cfg.get("enabled") else "关闭"),
        "推送：用户=%s 工具=%s AI=%s 思考=%s" % (
            "开" if push.get("user") else "关",
            "开" if push.get("tool") else "关",
            "开" if push.get("ai") else "关",
            "开" if push.get("thinking") else "关",
        ),
    ]
    return "\n".join(lines)


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

    if cmd == "/start":
        bridge_store.save_config({"enabled": True})
        _reply(qq_client, openid, "已开启消息推送")
        return True
    if cmd == "/stop":
        bridge_store.save_config({"enabled": False})
        _reply(qq_client, openid, "已暂停消息推送")
        return True
    if cmd == "/status":
        _reply(qq_client, openid, _status_text())
        return True
    if cmd == "/help":
        _reply(qq_client, openid, _help_text())
        return True
    if cmd == "/ask":
        # 转发类：把内容包装成卡片投给网页 AI
        if not arg:
            _reply(qq_client, openid, "用法：/ask 你的问题")
            return True
        from .qq_gateway import QqGateway
        QqGateway()._deliver_as_card(openid, arg, msg_id)
        _reply(qq_client, openid, "已转发给网页 AI")
        return True
    if cmd == "/run":
        # 工具类：经外部工具提供方通道下发
        _reply(qq_client, openid, "工具类指令暂未开放")
        return True

    # 未知指令：交还调用方当普通消息处理
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
