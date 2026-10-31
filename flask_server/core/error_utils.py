"""
AI 工具调用镜像插件 —— 错误分类与定位

把工具执行异常归类为三类，帮助 AI 与用户判断下一步动作：
- parameter     参数问题（缺失 / 类型不符 / 取值非法）
- environment   环境或路径问题（文件不存在、权限不足等）
- tool_internal 本地工具代码自身的缺陷

错误分类的关键作用：让「参数写错」与「工具实现有问题」区分开，
避免在代码缺陷上反复调整参数做无效重试。
"""
import subprocess
import traceback

import runtime


# ---------- 错误分类：参数问题 / 环境路径问题 / 工具内部代码缺陷 ----------
def param_error_cls():
    """取当前生效模块里的 ToolParamError。

    通过 runtime.impl 现取类对象，避免导入期绑定旧引用导致 isinstance 失配，
    把参数错误误判成工具代码缺陷。
    """
    # 兜底返回 None 而非空元组：isinstance(e, ()) 恒为 False，会让参数错误
    # 一路落到 tool_internal，把 AI 引向「改工具代码」的错误方向。
    # 取不到类时显式返回 None，由 classify_error 跳过这一档判断。
    return getattr(runtime.impl, "ToolParamError", None)


def classify_error(e):
    """把异常归类，决定 AI 该「改参数重试」还是「改工具代码」。"""
    # 参数异常类可能取不到（impl 未注入或未定义该类），此时跳过这一档判断
    _pec = param_error_cls()
    if _pec is not None and isinstance(e, _pec):
        return "parameter"
    if isinstance(e, (KeyError, TypeError, ValueError)):
        return "parameter"
    if isinstance(e, (FileNotFoundError, NotADirectoryError, IsADirectoryError,
                      PermissionError, UnicodeDecodeError)):
        return "environment"
    # 执行超时属环境 / 运行条件问题：脚本可能死循环、跑得慢、或等外部响应，
    # 不是工具代码缺陷，归入 environment 提示调用方调整用法而非改代码。
    # 两种超时都要覆盖：
    #   subprocess.TimeoutExpired —— 自定义脚本 / 命令类工具超时；
    #   TimeoutError（内置，3.10 上为 OSError 子类，3.11 起与 futures.TimeoutError 合并）
    #     —— 内置工具经 _run_with_timeout 兜底超时抛出。
    # 漏判后者会把「工具跑得慢」误报成「工具代码缺陷」，把 AI 引向改代码的错误方向。
    if isinstance(e, (subprocess.TimeoutExpired, TimeoutError)):
        return "environment"
    return "tool_internal"


def error_location(exc_tb):
    """从 traceback 里挑出最有价值的那一帧：优先工具实现模块内的最后一帧。"""
    try:
        frames = traceback.extract_tb(exc_tb)
        if not frames:
            return None
        picked = None
        # 从后往前找属于本服务目录的帧，即工具实现内部的出错位置
        for f in reversed(frames):
            if f.filename.startswith(runtime.APP_DIR_STR):
                picked = f
                break
        if picked is None:
            picked = frames[-1]
        return {
            "file": picked.filename,
            "line": picked.lineno,
            "function": picked.name,
            "source": (picked.line or "").strip(),
        }
    except Exception:
        return None
