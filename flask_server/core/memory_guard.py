"""AI 工具调用镜像插件 —— 记忆接口总开关守卫

职责：给记忆系统的全部 HTTP 接口提供统一的前置拦截，
开关关闭时直接短路返回，视图函数根本不会被调用。

为什么单独成模块：记忆接口有三十余个，逐个视图函数里判断既易漏，
也会让每个函数多出三行噪音；抽到这里后，路由文件里只留一行调用，
既守住行数上限，也让「什么情况下记忆接口不可用」只有一个答案。

返回 200 而非错误码的理由：这是「功能未启用」的正常状态，不是故障。
前端据此显示为空即可，不应弹错误、也不应自动重试。

依赖：flask、memory_switch
"""
from flask import jsonify

import memory_switch


def blocked_response():
    """返回守卫结果：允许访问时返回 None，禁止时返回可直接返回的响应。

    Flask 的 before_request 钩子约定：返回 None 表示继续处理请求，
    返回响应对象表示就此短路。
    @returns None 或 (响应, 状态码)
    """
    if memory_switch.is_enabled():
        # 开关打开：不拦截，交给视图函数正常处理
        return None
    return jsonify({
        "success": False,
        "disabled": True,
        "error": "记忆系统已关闭（设置页未开启记忆检查）",
    }), 200
