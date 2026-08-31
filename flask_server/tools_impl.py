"""AI 工具调用镜像插件 —— 本地工具实现（支持热重载）

单独拆出本模块的原因：
1. AI 自愈时可直接改写本文件，再用 hot_reload_fix 热重载，无需重启 Flask 服务；
2. 热重载失败可整体回滚，不会把服务本身搞挂。

约定：
- 参数不合法（缺失 / 类型错 / 取值非法）请抛 ToolParamError；
  其他异常一律视为「工具内部代码缺陷」，AI 会据此决定改参数还是改代码。
"""
import os
import re
import fnmatch
from pathlib import Path


class ToolParamError(Exception):
    """参数错误：调用方传入的参数不合法，调整参数即可重试。

    与「工具内部代码缺陷」区分开，便于 AI 判断该改参数还是该修代码。
    """


# ---------- 工具目录（与插件内置目录保持一致） ----------
TOOLS = {
    "list_dir": {
        "description": "列出指定目录下的文件和子目录（不含点文件）",
        "parameters": [
            {"name": "target_directory", "type": "string", "required": True, "description": "要列出的目录路径（相对或绝对）"},
            {"name": "ignore_globs", "type": "array", "required": False, "description": "要忽略的通配符模式列表"},
        ],
    },
    "search_file": {
        "description": "按文件名通配符模式递归搜索文件，支持忽略特定模式",
        "parameters": [
            {"name": "target_directory", "type": "string", "required": True, "description": "搜索根目录"},
            {"name": "pattern", "type": "string", "required": True, "description": "文件名通配符，如 *.js"},
            {"name": "recursive", "type": "boolean", "required": False, "description": "是否递归子目录，默认 true"},
            {"name": "caseSensitive", "type": "boolean", "required": False, "description": "是否区分大小写"},
            {"name": "ignore_globs", "type": "array", "required": False, "description": "忽略模式列表"},
        ],
    },
    "search_content": {
        "description": "基于正则在文件内容中搜索匹配（支持上下文、类型过滤）",
        "parameters": [
            {"name": "pattern", "type": "string", "required": True, "description": "正则表达式"},
            {"name": "path", "type": "string", "required": False, "description": "搜索路径，默认当前目录"},
            {"name": "glob", "type": "string", "required": False, "description": "文件名过滤，如 *.py"},
            {"name": "contextAround", "type": "integer", "required": False, "description": "上下文字节数/行数"},
            {"name": "caseSensitive", "type": "boolean", "required": False, "description": "是否区分大小写"},
        ],
    },
    "read_file": {
        "description": "读取本地文件内容，支持指定偏移与行数",
        "parameters": [
            {"name": "filePath", "type": "string", "required": True, "description": "文件路径"},
            {"name": "offset", "type": "integer", "required": False, "description": "起始行（从 1 开始）"},
            {"name": "limit", "type": "integer", "required": False, "description": "读取行数"},
        ],
    },
    "read_lints": {
        "description": "读取工作区或指定文件的 linter 诊断信息（错误/警告）",
        "parameters": [
            {"name": "paths", "type": "array", "required": False, "description": "文件或目录路径"},
            {"name": "severity", "type": "array", "required": False, "description": "过滤严重级别"},
        ],
    },
    "replace_in_file": {
        "description": "在已有文件中进行精确字符串替换（用于最小化改动）",
        "parameters": [
            {"name": "filePath", "type": "string", "required": True, "description": "文件路径"},
            {"name": "old_str", "type": "string", "required": True, "description": "待替换原文（须唯一）"},
            {"name": "new_str", "type": "string", "required": True, "description": "替换后的文本"},
        ],
    },
    "write_to_file": {
        "description": "创建或覆盖写入完整文件内容",
        "parameters": [
            {"name": "filePath", "type": "string", "required": True, "description": "文件路径"},
            {"name": "content", "type": "string", "required": True, "description": "完整文件内容"},
        ],
    },
    "delete_file": {
        "description": "删除指定路径的文件",
        "parameters": [
            {"name": "target_file", "type": "string", "required": True, "description": "要删除的文件路径"},
        ],
    },
    "get_tool_params": {
        "description": "根据工具 id 查询其参数、说明与用法",
        "parameters": [
            {"name": "tool_id", "type": "string", "required": True, "description": "工具名称/id"},
        ],
    },
}


# ---------- 各工具实现 ----------
def _abspath(p):
    p = Path(p)
    return p if p.is_absolute() else Path(os.path.abspath(p))


def _require(p, *names):
    """校验必填参数；缺失 / 空串时抛 ToolParamError，并明确告知正确参数名，
    避免 AI 臆造别名（如把 target_directory 写成 path）后工具静默用默认值、返回成功却结果错误，
    导致自愈流程因「没抛异常」而永远不触发。"""
    for n in names:
        v = p.get(n)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            raise ToolParamError(
                "缺少必填参数 %s。注意：本工具参数名就是 %s（请先用 get_tool_params 核对准确参数名，"
                "不要臆造 path / file 等别名）" % (n, n)
            )
    return True


def t_list_dir(p):
    _require(p, "target_directory")
    d = _abspath(p.get("target_directory"))
    ig = p.get("ignore_globs") or []
    items = []
    for name in sorted(os.listdir(d)):
        if name.startswith("."):
            continue
        if any(fnmatch.fnmatch(name, g) for g in ig):
            continue
        full = d / name
        items.append({"name": name, "type": "directory" if full.is_dir() else "file"})
    return {"directory": str(d), "items": items}


def t_search_file(p):
    _require(p, "target_directory", "pattern")
    root = _abspath(p.get("target_directory"))
    pattern = p.get("pattern", "*")
    recursive = p.get("recursive", True)
    ig = p.get("ignore_globs") or []
    gen = root.rglob(pattern) if recursive else root.glob(pattern)
    matches = []
    for f in gen:
        if f.is_file():
            if any(fnmatch.fnmatch(f.name, g) for g in ig):
                continue
            matches.append(str(f))
    return {"matches": matches, "count": len(matches)}


def t_search_content(p):
    _require(p, "pattern")
    pattern = p.get("pattern", "")
    path = p.get("path", ".")
    glob = p.get("glob")
    case = p.get("caseSensitive", False)
    regex = re.compile(pattern, 0 if case else re.IGNORECASE)
    root = _abspath(path)
    files = root.rglob("*") if root.is_dir() else [root]
    matches = []
    for f in files:
        if not f.is_file():
            continue
        if glob and not fnmatch.fnmatch(f.name, glob):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                matches.append({"file": str(f), "line": i, "text": line})
                if len(matches) >= 200:
                    break
    return {"count": len(matches), "matches": matches}


def t_read_file(p):
    _require(p, "filePath")
    fp = _abspath(p.get("filePath"))
    offset = int(p.get("offset", 1) or 1)
    limit = p.get("limit")
    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    start = max(0, offset - 1)
    end = len(lines) if limit is None else start + int(limit)
    return {"path": str(fp), "content": "".join(lines[start:end]), "total_lines": len(lines)}


def t_read_lints(p):
    # 本地服务未集成 linter，返回空诊断即可
    return {"diagnostics": [], "note": "本地服务未集成 linter，返回空诊断。"}


def t_replace_in_file(p):
    _require(p, "filePath", "old_str")
    fp = _abspath(p.get("filePath"))
    old = p.get("old_str")
    new = p.get("new_str", "")
    if old == "":
        raise ToolParamError("old_str 不能为空")
    content = Path(fp).read_text(encoding="utf-8")
    cnt = content.count(old)
    if cnt == 0:
        raise ToolParamError("未找到 old_str（原文需与文件内容完全一致，含缩进与换行）")
    if cnt > 1:
        raise ToolParamError("old_str 在文件中出现 %d 次，不唯一，请扩大上下文" % cnt)
    content = content.replace(old, new, 1)
    Path(fp).write_text(content, encoding="utf-8")
    return {"replaced": True, "file": str(fp)}


def t_write_to_file(p):
    _require(p, "filePath", "content")
    fp = _abspath(p.get("filePath"))
    content = p.get("content", "")
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return {"written": True, "file": str(fp), "bytes": len(content.encode("utf-8"))}


def t_delete_file(p):
    _require(p, "target_file")
    fp = _abspath(p.get("target_file"))
    os.remove(fp)
    return {"deleted": True, "file": str(fp)}


def t_get_tool_params(p):
    tid = p.get("tool_id") or p.get("tool")
    if tid not in TOOLS:
        return {"error": "未知工具 id", "available": list(TOOLS.keys())}
    entry = TOOLS[tid]
    return {"tool": tid, "description": entry["description"], "parameters": entry["parameters"]}


DISPATCH = {
    "list_dir": t_list_dir,
    "search_file": t_search_file,
    "search_content": t_search_content,
    "read_file": t_read_file,
    "read_lints": t_read_lints,
    "replace_in_file": t_replace_in_file,
    "write_to_file": t_write_to_file,
    "delete_file": t_delete_file,
    "get_tool_params": t_get_tool_params,
}
