"""
路由：工具目录与工具调用

- GET  /tools   返回已上线工具清单（内置 + 自定义 + 外部提供方）
- POST /tool    调用工具（内置 / 自定义脚本 / 外部提供方）
"""
from flask import Blueprint, jsonify, request

import runtime
import custom_tools as ct
import external_tools
import screenshot_store
from responses import disabled_resp, tool_error

bp = Blueprint("tools", __name__)


def _save_screenshot_data_url(data_url):
    """把截图 dataURL 保存到本地，返回 {name, path}；失败返回 None。

    存盘实现已抽到公共模块 screenshot_store，与 QQ「/sp」指令共用同一套
    目录与命名，避免同一目录下两种格式混杂。
    """
    return screenshot_store.save_data_url(data_url)


@bp.route("/tools", methods=["GET"])
def tools():
    """返回工具目录。

    只返回「已上线」的工具；下线工具不出现在 System Prompt，也无法调用。
    自定义工具（来自 skill）合并进来；executor=external 的工具由其提供方并入。
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
    """调用内置工具。未注册或已下线时返回 None，交由调用方继续分派。"""
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


def _validate_external_params(name, ctool, params):
    """校验外部工具的必填参数。

    外部工具由提供方（扩展）执行，转发前必须在此拦截缺失 / 空的必填参数，
    否则错误参数会被原样转发、扩展侧取不到值也不报错，导致「静默失败」：
    调用方以为成功，实际动作未生效。返回错误响应；参数合法返回 None。
    """
    missing = []
    for p in ctool.get("parameters") or []:
        if not p.get("required"):
            continue
        pname = p.get("name")
        val = (params or {}).get(pname)
        if val is None or (isinstance(val, str) and val.strip() == ""):
            missing.append(pname)
    if not missing:
        return None
    return jsonify(
        success=False, tool=name,
        error="缺少必填参数：%s" % "、".join(missing),
        errorType="ToolParamError", origin="parameter",
        originLabel=runtime.ORIGIN_LABEL.get("parameter", "parameter"),
        hint=runtime.HINTS["parameter"],
    ), 200


def _external_error(name, error, errorType, hint):
    """构造外部工具的环境类错误响应（HTTP 200，错误在 body）。

    外部工具的失败多与环境有关（提供方未声明、执行方未及时取走），
    统一归类为 environment，提示调用方检查环境而非改参数。
    """
    return jsonify(
        success=False, tool=name,
        error=error, errorType=errorType, origin="environment",
        originLabel=runtime.ORIGIN_LABEL.get("environment", "environment"),
        hint=hint,
    ), 200


def _call_external(name, ctool, params, page_url="", host_page_url=""):
    """转发给外部提供方并等待回传。

    在线与否只作展示，不参与执行判断：请求一律入队等待，由提供方来取走执行。
    等待上限（FORWARD_TIMEOUT）仅作保险丝，防止提供方始终不来取时无限期挂起。
    page_url 为目标页面地址：该页在定向窗口内独占命令，超时未取走才逸散。
    host_page_url 为本页面地址（承载对话、把 AI 代码块转成卡片的顶层页）：
    逸散阶段优先回投本页面，本页面没开 debug-chrome 才随机投给其他页面。
    """
    param_err = _validate_external_params(name, ctool, params)
    if param_err is not None:
        return param_err
    provider = (ctool.get("provider") or "").strip()
    if not provider:
        return _external_error(
            name, "外部工具未声明提供方: %s" % name, "ProviderMissing",
            "该外部工具缺少 provider 声明，无法确定执行方。")
    silent = bool(ctool.get("silent"))
    ok, data = external_tools.hub.dispatch(
        provider, name, params, silent=silent,
        page_url=page_url, host_page_url=host_page_url)
    if not ok:
        return _external_error(
            name, "外部工具未在等待时限内被执行: %s" % name, "ForwardTimeout",
            "请求已排队但执行方未在时限内取走。请确认调试扩展已打开并停留在目标页面。")
    # 截图类结果：把 dataURL 原图保存到本地，并把落盘信息附回结果。
    # 保存放后端做（内容脚本无文件系统权限），路径与 QQ「/sp」指令一致，
    # 均为 flask_server/screenshots/，便于用户统一查找。
    if isinstance(data, dict) and data.get("data") and isinstance(data["data"], dict):
        shot = data["data"].get("screenshot")
        if isinstance(shot, str) and shot.startswith("data:image/"):
            saved = _save_screenshot_data_url(shot)
            if saved:
                data["data"]["saved"] = saved
    # silent 仅随结果回传，供前端决定不在抽屉生成工具卡片；结果本身照常回传。
    return jsonify(success=True, tool=name, result=data, silent=silent)


def _call_custom(name, params, page_url="", host_page_url=""):
    """调用自定义工具（来自标准 skill 的 tool.json）。未注册返回 None。

    executor=external 走提供方转发；executor=script 走本地子进程执行。
    page_url / host_page_url 仅对 external 工具有意义：透传给命令队列用于定向与逸散。
    """
    ctool = ct.get_tool(name)
    if not ctool:
        return None
    if not ct.is_enabled(name):
        return disabled_resp(name)
    if (ctool.get("executor") or "script") == "external":
        return _call_external(name, ctool, params, page_url=page_url, host_page_url=host_page_url)
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
    # page_url：本次调用的目标页面地址（AI 在参数里指定的那个页面）。
    # 后端让该页在定向窗口内独占命令，超时未取走才逸散。
    page_url = data.get("page_url") or ""
    # host_page_url：本页面地址（承载对话、把 AI 代码块转成卡片的顶层页）。
    # 逸散阶段优先回投本页面，本页面没开 debug-chrome 才随机投给其他页面。
    host_page_url = data.get("host_page_url") or ""

    # 1) 内置工具
    resp = _call_builtin(name, params)
    if resp is not None:
        return resp
    # 2) 自定义工具
    resp = _call_custom(name, params, page_url=page_url, host_page_url=host_page_url)
    if resp is not None:
        return resp
    # 3) 未知工具
    return _unknown_tool(name)
