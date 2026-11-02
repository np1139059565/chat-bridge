"""AI 工具调用镜像插件 —— 外部工具转发

职责：把 executor=external 的工具调用转发给提供方（如页面调试扩展），
等其回传结果，并把错误统一包装成 HTTP 200 + body 内的错误分类。

为什么独立成模块：外部工具转发涉及「入队 — 定向 — 逸散 — 回传」一整套
与本地工具完全不同的执行模型，和「内置 / 自定义工具的分派」不是同一关注点；
放在 routes/tools.py 会让该文件超出仓库行数上限。
"""
from flask import jsonify

import runtime
import external_tools


def validate_external_params(name, ctool, params):
    """校验外部工具的必填参数。

    外部工具由提供方（扩展）执行，转发前必须在此拦截缺失 / 空的必填参数，
    否则错误参数会被原样转发、扩展侧取不到值也不报错，导致「静默失败」：
    调用方以为成功，实际动作未生效。
    @param name  工具名
    @param ctool 工具定义（含 parameters）
    @param params 调用方传入的参数
    @returns 错误响应；参数合法返回 None
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


def external_error(name, error, errorType, hint):
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


def call_external(name, ctool, params, page_url="", host_page_url=""):
    """转发给外部提供方并等待回传。

    在线与否只作展示，不参与执行判断：请求一律入队等待，由提供方来取走执行。
    等待上限仅作保险丝，防止提供方始终不来取时无限期挂起。
    @param name          工具名
    @param ctool         工具定义（含 provider / silent / parameters）
    @param params        调用参数
    @param page_url      目标页面地址：该页在定向窗口内独占命令，超时未取走才逸散
    @param host_page_url 本页面地址：逸散阶段优先回投本页面
    """
    param_err = validate_external_params(name, ctool, params)
    if param_err is not None:
        return param_err
    provider = (ctool.get("provider") or "").strip()
    if not provider:
        return external_error(
            name, "外部工具未声明提供方: %s" % name, "ProviderMissing",
            "该外部工具缺少 provider 声明，无法确定执行方。")
    silent = bool(ctool.get("silent"))
    # 转发耗时埋点：区分「提供方没取走」与「提供方执行慢」
    import time as _t
    import app_log
    _t0 = _t.perf_counter()
    ok, data = external_tools.hub.dispatch(
        provider, name, params, silent=silent,
        page_url=page_url, host_page_url=host_page_url)
    _ms = (_t.perf_counter() - _t0) * 1000.0
    app_log.info("[tool]", "%s(外部) 等待=%.0fms 结果=%s" % (name, _ms, "成功" if ok else "未取走"))
    if not ok:
        return external_error(
            name, "外部工具未在等待时限内被执行: %s" % name, "ForwardTimeout",
            "请求已排队但执行方未在时限内取走。请确认调试扩展已打开并停留在目标页面。")
    # 截图类结果：把 dataURL 原图保存到本地，并把落盘信息附回结果。
    # 保存放后端做（内容脚本无文件系统权限）。
    if isinstance(data, dict) and data.get("data") and isinstance(data["data"], dict):
        shot = data["data"].get("screenshot")
        if isinstance(shot, str) and shot.startswith("data:image/"):
            import screenshot_store
            saved = screenshot_store.save_data_url(shot)
            if saved:
                data["data"]["saved"] = saved
    # silent 仅随结果回传，供前端决定不在抽屉生成工具卡片；结果本身照常回传。
    return jsonify(success=True, tool=name, result=data, silent=silent)
