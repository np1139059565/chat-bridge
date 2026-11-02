"""外部工具提供方通道：轮询取命令、回传执行结果。

提供方通过 POST /api/ext/<provider> 与工具服务交互：
    action=poll   取走待执行命令（兼作心跳）
    action=result 回传某次工具调用的结果
"""
from flask import Blueprint, request, jsonify

from external_tools import hub, command_hub

bp = Blueprint("ext", __name__)


def _channel(target_hub, provider, data, ignore_closed=False):
    """处理一次提供方通道交互（poll / result）。

    抽成函数供 AI 工具通道与指令通道共用：两者行为完全一致，
    差异只在「操作哪个池子」，复制一份逻辑只会让日后改一处漏一处。
    @param target_hub    目标执行池（hub / command_hub）
    @param provider      提供方标识
    @param data          请求体
    @param ignore_closed 为真时无视上报的 is_open，一律按打开处理
    @returns Flask 响应
    """
    action = data.get("action")

    if action == "poll":
        # page_url 与 is_open 由扩展心跳带上：page_url 用于把命令定向到发起页面，
        # is_open 表示本页面工具（抽屉）是否打开。命令只认「目标页面工具已打开」，
        # 目标没开就直接逸散到其他页面，不再依赖时间窗猜测。
        #
        # 指令通道无视 is_open：指令由用户在 QQ / 网页主动发起，
        # 其执行不应取决于抽屉当时是否开着。若沿用 is_open，抽屉关闭期间
        # 只放行唤醒类命令，/dc（关闭抽屉）、/dt（打开设置）等永远取不走，
        # 表现为「指令已下发但未在时限内执行」。
        is_open = True if ignore_closed else bool(data.get("is_open", True))
        commands = target_hub.poll(
            provider,
            page_url=data.get("page_url") or "",
            is_open=is_open,
        )
        return jsonify({"success": True, "commands": commands})

    if action == "result":
        request_id = data.get("request_id")
        if not request_id:
            return jsonify({"success": False, "error": "INVALID_PARAMS", "message": "request_id required"}), 400
        ok = target_hub.resolve(request_id, data.get("result"))
        return jsonify({"success": bool(ok)})

    return jsonify({"success": False, "error": "UNKNOWN_ACTION", "message": action}), 400


@bp.route("/api/ext/<provider>", methods=["POST", "OPTIONS"])
def provider_channel(provider):
    """AI 工具通道：AI 调外部工具时由此下发与回传。"""
    return _channel(hub, provider, request.get_json(force=True, silent=True) or {})


@bp.route("/api/command-ext/<provider>", methods=["POST", "OPTIONS"])
def command_channel(provider):
    """指令执行通道：用户指令（如 /dc）的取命令与回传走这里。

    与 AI 工具通道物理隔离：两条链路各有自己的队列与等待表，
    指令执行失败后的善后不会动到 AI 工具共用的资源。

    ignore_closed=True：指令的执行不依赖抽屉开关状态。用户从 QQ / 网页
    主动下发指令时，抽屉可能正是关闭的（/dc 本身就是关闭抽屉）。
    """
    return _channel(command_hub, provider,
                    request.get_json(force=True, silent=True) or {},
                    ignore_closed=True)
