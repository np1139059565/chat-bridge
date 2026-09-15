"""
AI 工具调用镜像插件 —— 错误响应辅助

统一「工具已下线」「工具执行异常」两类失败的返回结构，保证前端与 AI 拿到的
字段一致：success / tool / error / errorType / origin / originLabel /
location / traceback / hint / available。
"""
import sys
import traceback

from flask import jsonify

import runtime
from error_utils import classify_error, error_location


def disabled_resp(name):
    """工具已下线：给出可用工具列表与提示，告诉 AI 改参数无效、需换工具或上线。"""
    return jsonify(
        success=False, tool=name,
        error="工具已下线（disabled）: %s" % name,
        errorType="ToolDisabled", origin="disabled",
        originLabel=runtime.ORIGIN_LABEL["disabled"],
        available=[k for k in runtime.TOOLS if runtime.is_tool_enabled(k)],
        hint=runtime.HINTS["disabled"],
    ), 200


def exception_payload(e, include_tool=None):
    """构造异常响应体：分类 + 定位 + 完整堆栈 + 提示。

    工具调用失败与 /hot_fix 失败共用同一结构，便于 AI 用同一套规则解读。
    @param e 捕获到的异常
    @param include_tool 需要回填的 tool 字段；None 表示不含该字段
    """
    tb_str = traceback.format_exc()
    origin = classify_error(e)
    payload = {
        "success": False,
        "error": "%s: %s" % (type(e).__name__, e),
        "errorType": type(e).__name__,
        "origin": origin,
        "originLabel": runtime.ORIGIN_LABEL.get(origin, origin),
        "location": error_location(sys.exc_info()[2]),
        "traceback": tb_str,
        "hint": runtime.HINTS.get(origin, ""),
    }
    if include_tool is not None:
        payload["tool"] = include_tool
    return payload


def tool_error(name, e):
    """工具执行异常：回传完整堆栈 + 分类，让 AI 区分「参数错」与「代码缺陷」。

    自定义脚本抛出的异常也走同一分类（ValueError→parameter 等）。
    """
    return jsonify(exception_payload(e, include_tool=name)), 200
