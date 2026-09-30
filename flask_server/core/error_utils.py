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
    return getattr(runtime.impl, "ToolParamError", ())


def classify_error(e):
    """把异常归类，决定 AI 该「改参数重试」还是「改工具代码」。"""
    if isinstance(e, param_error_cls()):
        return "parameter"
    if isinstance(e, (KeyError, TypeError, ValueError)):
        return "parameter"
    if isinstance(e, (FileNotFoundError, NotADirectoryError, IsADirectoryError,
                      PermissionError, UnicodeDecodeError)):
        return "environment"
    # 执行超时属环境 / 运行条件问题：脚本可能死循环或等外部响应，
    # 不是工具代码缺陷，归入 environment 提示调用方调整用法而非改代码。
    if isinstance(e, subprocess.TimeoutExpired):
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
