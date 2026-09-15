"""
路由：工具目录与工具调用

- GET  /tools   返回已上线工具清单（内置 + 自定义 + 外部提供方）
- POST /tool    调用工具（内置 / 自愈 / 自定义脚本 / 外部提供方）
"""
from flask import Blueprint, jsonify, request

import runtime
import custom_tools as ct
import external_tools
from responses import disabled_resp, tool_error

bp = Blueprint("tools", __name__)


@bp.route("/tools", methods=["GET"])
def tools():
    """返回工具目录。

    只返回「已上线」的工具；下线工具不出现在 System Prompt，也无法调用。
    自愈工具（read_tool_source / hot_reload_fix）永远在线；自定义工具（来自 skill）合并进来。
    executor=external 的工具由其提供方在线时并入。
    """
    builtin = []
    for k, v in runtime.TOOLS.items():
        if not runtime.is_tool_enabled(k):
            continue
        item = {"name": k, **v}
        if k == "run_command":
            # 语言列表来自配置，随 config.yaml 变化
            item["languages"] = runtime.CONFIG.get("tools", {}).get("run_command", {}).get("languages", [])
        builtin.append(item)
    runtime.refresh_external_providers()
    custom = ct.all_meta()
    external = external_tools.hub.provider_tools()
    # 外部工具若已由 custom 列出（自定义工具视图），避免重复
    seen = {t.get("name") for t in custom}
    external = [t for t in external if t.get("name") not in seen]
    return jsonify({"tools": builtin + custom + external})


def _call_builtin(name, params):
    """调用内置工具（含自愈工具）。未注册或已下线时返回 None，交由调用方继续分派。"""
    fn = runtime.DISPATCH.get(name)
    if not fn:
        return None
    if not runtime.is_tool_enabled(name):
        return disabled_resp(name)
    try:
        result = fn(params)
        return jsonify(success=True, tool=name, result=result)
    except Exception as e:
        return tool_error(name, e)


def _call_external(name, ctool, params):
    """转发给外部提供方并阻塞等待回传；提供方离线或转发失败时返回错误响应。"""
    provider = (ctool.get("provider") or "").strip()
    if not provider or not external_tools.hub.is_online(provider):
        return jsonify(
            success=False, tool=name,
            error="提供方离线，无法执行外部工具: %s" % name,
            errorType="ProviderOffline", origin="environment",
            originLabel=runtime.ORIGIN_LABEL.get("environment", "environment"),
            hint="该工具由其提供方（扩展）执行，需提供方上线轮询后重试。",
        ), 200
    silent = bool(ctool.get("silent"))
    ok, data = external_tools.hub.dispatch(provider, name, params, silent=silent)
    if not ok:
        return jsonify(
            success=False, tool=name,
            error="外部工具转发失败: %s" % data,
            errorType="ForwardError", origin="environment",
            originLabel=runtime.ORIGIN_LABEL.get("environment", "environment"),
            hint="提供方未在超时内回传结果，请确认扩展在线后重试。",
        ), 200
    # silent 工具：入队即结束，其结果不回传网页 AI
    return jsonify(success=True, tool=name, result=data, silent=silent)


def _call_custom(name, params):
    """调用自定义工具（来自标准 skill 的 tool.json）。未注册返回 None。

    executor=external 走提供方转发；executor=script 走本地子进程执行。
    """
    ctool = ct.get_tool(name)
    if not ctool:
        return None
    if not ct.is_enabled(name):
        return disabled_resp(name)
    if (ctool.get("executor") or "script") == "external":
        return _call_external(name, ctool, params)
    try:
        result = ct.run(ctool, params)
        return jsonify(success=True, tool=name, result=result)
    except Exception as e:
        return tool_error(name, e)


def _unknown_tool(name):
    """未知工具响应：附带可用工具清单与提示，便于 AI 更正工具名。"""
    return jsonify(
        success=False, tool=name,
        error="未知工具: %s" % name,
        errorType="UnknownTool",
        origin="unknown_tool",
        originLabel=runtime.ORIGIN_LABEL["unknown_tool"],
        available=list(sorted(set(list(runtime.DISPATCH.keys()) + [t["name"] for t in ct.all_meta_full()]))),
        hint=runtime.HINTS["unknown_tool"],
    ), 404


@bp.route("/tool", methods=["POST", "OPTIONS"])
def tool():
    """调用工具。按优先级依次尝试：内置 → 自定义 → 未知工具。"""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("tool") or data.get("name")
    params = data.get("parameters") or data.get("arguments") or {}

    # 1) 内置工具（含自愈工具）
    resp = _call_builtin(name, params)
    if resp is not None:
        return resp
    # 2) 自定义工具
    resp = _call_custom(name, params)
    if resp is not None:
        return resp
    # 3) 未知工具
    return _unknown_tool(name)
