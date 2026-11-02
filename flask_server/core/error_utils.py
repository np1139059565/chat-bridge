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


def _declared_param_names(tool_name):
    """取某内置工具声明过的参数名集合；取不到时返回空集合。

    用途：区分「调用方漏传已声明的参数」与「工具实现引用了不存在的键」。
    只查内置工具表：自定义 / 外部工具走各自的执行通道，不经过本分类器。
    @param tool_name 工具名；None 或未知工具返回空集合
    @returns 参数名集合
    """
    if not tool_name:
        return set()
    # 先查内置工具表
    entry = runtime.TOOLS.get(tool_name) or {}
    params = entry.get("parameters") or []
    # 内置表没查到：再查自定义 / 外部工具表。
    # 外部工具（如 debug_chrome 提供的）注册在 custom_tools 而不在 runtime.TOOLS，
    # 只查内置表会让它们声明的参数永远取不到，KeyError 一律落到保守分支，
    # 实现里的键名写错会被误报成「调用方参数写错」。
    if not params:
        try:
            import custom_tools as ct
            ctool = ct.get_tool(tool_name) or {}
            params = ctool.get("parameters") or []
        except Exception:
            # 自定义工具表不可用时保持空集合，退回原有保守口径
            params = []
    names = set()
    for p in params:
        # 参数定义形如 {"name": "path", ...}；缺 name 的条目跳过
        n = p.get("name") if isinstance(p, dict) else None
        if n:
            names.add(n)
    return names


def classify_error(e, tool_name=None):
    """把异常归类，决定 AI 该「改参数重试」还是「改工具代码」。

    @param e         捕获到的异常
    @param tool_name 出错工具名；用于 KeyError 的精确判别，未知时可传 None
    """
    # 参数异常类可能取不到（impl 未注入或未定义该类），此时跳过这一档判断
    _pec = param_error_cls()
    if _pec is not None and isinstance(e, _pec):
        return "parameter"
    # KeyError 精确判别：缺失的键是工具声明过的参数 → 调用方漏传；
    # 不是声明过的参数 → 实现里键名写错（代码缺陷），不能引向「改参数」。
    # 这是唯一能在分类器层面可靠区分的异常类型；
    # TypeError / ValueError 保持原判（见下方说明），不在此处猜测。
    if isinstance(e, KeyError):
        key = e.args[0] if e.args else None
        declared = _declared_param_names(tool_name)
        # 声明过、或工具名未知（无从判别）时，按参数问题处理，保持原有保守口径
        if key in declared or not declared:
            return "parameter"
        return "tool_internal"
    if isinstance(e, (TypeError, ValueError)):
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
    # 功能未启用类异常：记忆系统被总开关关闭时抛 MemoryDisabled。
    # 这是配置状态问题（去设置页打开开关即可），不是工具代码缺陷；
    # 若不单列，RuntimeError 会一路落到 tool_internal，把调用方引向「改代码」。
    if _is_disabled_error(e):
        return "environment"
    return "tool_internal"


def _is_disabled_error(e):
    """判断异常是否表示「某功能未启用」。

    按类名识别而非直接 import：记忆模块在总开关关闭时不应被强行导入，
    且同类语义的异常可能分散在不同模块，统一按「类名以 Disabled 结尾」识别。
    @param e 捕获到的异常
    @returns 属于未启用类异常返回 True
    """
    for cls in type(e).__mro__:
        if cls.__name__.endswith("Disabled"):
            return True
    return False


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
