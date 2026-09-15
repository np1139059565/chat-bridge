"""
AI 工具调用镜像插件 —— 错误分类与定位

把工具执行异常归类为三类，决定 AI 下一步该「改参数重试」还是「改工具代码」：
- parameter     参数问题（缺失 / 类型不符 / 取值非法）
- environment   环境或路径问题（文件不存在、权限不足等）
- tool_internal 本地工具代码自身的缺陷

错误分类的关键作用：避免 AI 在「代码缺陷」上反复调整参数无效重试，
而是转向 read_tool_source + hot_reload_fix 的自愈流程。
"""
import traceback

import runtime


# ---------- 错误分类：参数问题 / 环境路径问题 / 工具内部代码缺陷 ----------
def param_error_cls():
    """取当前生效模块里的 ToolParamError。

    注意：热重载会重建该类对象，若在导入期 `from tools_impl import ToolParamError`
    绑定旧类，isinstance 会失配，导致参数错误被误判成工具代码缺陷。
    因此这里每次现取 runtime.impl 上的类对象。
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
