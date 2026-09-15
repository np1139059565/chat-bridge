"""
AI 工具调用镜像插件 —— 自愈工具与热重载

提供两个 AI 自愈专用工具：
- read_tool_source：读取本地工具实现的源码，用于定位工具代码缺陷
- hot_reload_fix：对工具实现文件打补丁后热重载，无需重启服务；失败自动回滚

同时提供 _reload_impl()：重新加载工具实现模块并重建 TOOLS / DISPATCH。
自愈工具自身始终保留在工具表中，不受上下线开关影响。
"""
import importlib
import inspect
import sys
import traceback
from pathlib import Path

import runtime


# ---------- AI 自愈工具：读源码 / 打补丁热重载 ----------
def t_read_tool_source(p):
    """读取某个工具的当前实现源码，供 AI 定位代码缺陷。"""
    name = p.get("tool") or p.get("tool_id")
    if not name:
        raise runtime.impl.ToolParamError("缺少参数 tool")
    fn = runtime.DISPATCH.get(name)
    if not fn:
        raise runtime.impl.ToolParamError(
            "未知工具: %s（可用：%s）" % (name, ", ".join(sorted(runtime.DISPATCH.keys()))))
    try:
        src = inspect.getsource(fn)
    except Exception as e:
        raise runtime.impl.ToolParamError("无法读取该工具的源码：%s" % e)
    return {"tool": name, "file": inspect.getsourcefile(fn), "source": src}


def resolve_impl_path(p):
    """解析待修复文件路径：缺省为 tools_impl.py；相对路径视为相对服务目录。"""
    fp = p.get("file_path") or p.get("filePath")
    if not fp:
        return runtime.APP_DIR / "tools_impl.py"
    path = Path(fp)
    return path if path.is_absolute() else (runtime.APP_DIR / path)


def _apply_patch(original, p):
    """按请求生成补丁后内容。

    支持两种模式：
    - content 模式：整文件重写
    - old_str/new_str 模式：精确替换，要求 old_str 在文件中唯一
    """
    old = p.get("old_str")
    new = p.get("new_str")
    content = p.get("content")
    if content is None and not old:
        raise runtime.impl.ToolParamError("old_str/new_str 与 content 至少要提供一组")
    if content is not None:
        return content
    cnt = original.count(old)
    if cnt == 0:
        raise runtime.impl.ToolParamError("未找到 old_str（原文需与文件内容完全一致，含缩进与换行）")
    if cnt > 1:
        raise runtime.impl.ToolParamError("old_str 在文件中出现 %d 次，不唯一，请扩大上下文" % cnt)
    return original.replace(old, new or "", 1)


def _rollback(fp, original, e):
    """补丁导致模块无法加载时回滚文件并恢复可运行状态，返回失败结果。"""
    fp.write_text(original, encoding="utf-8")
    try:
        _reload_impl()
    except Exception:
        pass
    return {
        "patched": False,
        "reloaded": False,
        "rolledBack": True,
        "file": str(fp),
        "errorType": type(e).__name__,
        "error": str(e),
        "traceback": traceback.format_exc(),
        "note": "补丁导致工具模块无法加载，已自动回滚到修复前的版本。",
    }


def t_hot_reload_fix(p):
    """对本地工具代码打补丁并热重载；若补丁导致模块无法加载，自动回滚。"""
    fp = resolve_impl_path(p)
    if not fp.exists():
        raise runtime.impl.ToolParamError("文件不存在: %s" % fp)

    original = fp.read_text(encoding="utf-8")
    patched = _apply_patch(original, p)
    if patched == original:
        raise runtime.impl.ToolParamError("补丁前后内容一致，未产生任何改动")

    fp.write_text(patched, encoding="utf-8")
    try:
        _reload_impl()
        return {
            "patched": True,
            "reloaded": True,
            "file": str(fp),
            "tools": sorted(runtime.DISPATCH.keys()),
            "note": "已热重载，可立即用原参数重试该工具。",
        }
    except Exception as e:
        # 补丁把模块搞坏了：回滚文件并恢复可运行状态
        return _rollback(fp, original, e)


# 自愈工具表：始终在线，不受 config.yaml 的 enabled 开关影响
FIX_TOOLS = {
    "read_tool_source": t_read_tool_source,
    "hot_reload_fix": t_hot_reload_fix,
}

# 自愈工具元数据：并入工具目录与 get_tool_params 的返回
FIX_TOOL_META = {
    "read_tool_source": {
        "description": "读取本地工具实现的当前源码，用于定位工具代码缺陷（AI 自愈专用）",
        "parameters": [
            {"name": "tool", "type": "string", "required": True, "description": "工具名，如 read_file"},
        ],
    },
    "hot_reload_fix": {
        "description": "修复本地工具代码并热重载：对工具实现文件打补丁后重新加载，无需重启服务；失败自动回滚。",
        "parameters": [
            {"name": "file_path", "type": "string", "required": False, "description": "待修复文件，默认 tools_impl.py"},
            {"name": "old_str", "type": "string", "required": True, "description": "待替换原文（须唯一且完全匹配，含缩进）"},
            {"name": "new_str", "type": "string", "required": True, "description": "替换后的代码"},
            {"name": "content", "type": "string", "required": False, "description": "整文件重写时提供，与 old_str/new_str 二选一"},
        ],
    },
}


def _reload_impl():
    """重新加载工具实现模块，并重建 TOOLS / DISPATCH（修复类工具始终保留）。

    tools_impl 依赖 tool_helpers（通用辅助）与 tool_meta（元数据），这两个模块
    同样是 AI 自愈可能改动的对象，因此一并重载，保证补丁对三者都即时生效。
    重载顺序：先辅助与元数据，再实现模块（后者导入时会重新读取前两者）。
    """
    for mod_name in ("tool_helpers", "tool_meta"):
        mod = sys.modules.get(mod_name)
        if mod is not None:
            importlib.reload(mod)
    runtime.impl = importlib.reload(runtime.impl)
    tools = dict(runtime.impl.TOOLS)
    tools.update(FIX_TOOL_META)
    runtime.TOOLS = tools
    dispatch = dict(runtime.impl.DISPATCH)
    dispatch.update(FIX_TOOLS)
    runtime.DISPATCH = dispatch


def setup_fix_tools():
    """初始化阶段把自愈工具注册进 runtime（在首次 _reload_impl 之前调用）。"""
    runtime.FIX_TOOLS = FIX_TOOLS
    runtime.FIX_TOOL_META = FIX_TOOL_META
