"""AI 工具调用镜像插件 —— 本地工具实现

约定：
- 参数不合法（缺失 / 类型错 / 取值非法）请抛 ToolParamError；
  其他异常一律视为「工具内部代码缺陷」，调用方据此区分处理。

TOOLS 元数据在 tool_meta.py；不随调用变化的通用辅助（参数校验、路径解析、
体积控制）在 tool_helpers.py，并在此处重导出，保证 impl.ToolParamError 等既有引用不变。
run_command 的语言配置与执行逻辑在 run_command_impl.py，此处重导出其公开名。
"""
import os
import re
import fnmatch
from pathlib import Path

from tool_meta import TOOLS
from tool_helpers import (
    ToolParamError,  # 重导出：服务侧通过 runtime.impl.ToolParamError 判定参数错误
    SKILLS_ROOT,
    abspath as _abspath,
    resolve_skill_file as _resolve_skill_file,
    list_skills,
    normalize_aliases as _normalize_aliases,
    require as _require,
    enforce_size_limit,
)
# run_command 已拆到独立模块，重导出其公开名，保持 config_store / get_tool_params 既有引用不变
from run_command_impl import (
    RUN_COMMAND_SUPPORTED_LANGUAGES,
    RUN_COMMAND_TIMEOUT,
    t_run_command,
    _load_run_command_languages,
)


# 工具目录：元数据定义在 tool_meta.py，此处直接引用，保持「声明」与「实现」分离

# ---------- 各工具实现 ----------
def t_list_dir(p):
    """列出目录下的文件与子目录，跳过点文件与忽略模式。"""
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


def _match_name(name, pattern):
    """文件名通配符匹配：统一转小写比较，跨平台都忽略大小写差异。"""
    return fnmatch.fnmatch(name.lower(), str(pattern).lower())


def t_search_file(p):
    """按文件名通配符递归（或单层）搜索文件；匹配不区分大小写。

    先列出目录下的文件、再自行比对通配符，而不是把 pattern 交给 rglob/glob：
    后者的大小写敏感行为随操作系统而异，自行比对可保证各平台一致。
    """
    _require(p, "target_directory", "pattern")
    root = _abspath(p.get("target_directory"))
    pattern = p.get("pattern", "*")
    recursive = p.get("recursive", True)
    ig = p.get("ignore_globs") or []
    gen = root.rglob("*") if recursive else root.glob("*")
    matches = []
    for f in gen:
        if not f.is_file():
            continue
        if not _match_name(f.name, pattern):
            continue
        if any(_match_name(f.name, g) for g in ig):
            continue
        matches.append(str(f))
    return {"matches": matches, "count": len(matches)}


# 单次 search_content 的结果条数上限：超出后停止继续收集，交给体积上限进一步把关
_SEARCH_MATCH_LIMIT = 200


def _context_lines(lines, lineno, count, before):
    """取某一行上 / 下各若干行作为上下文。

    @param lines  文件全部行（不含换行符）
    @param lineno 目标行号（从 1 开始）
    @param count  上下各取多少行
    @param before True 取上方，False 取下方
    @return [{line, text}]，已按行号范围裁剪，不会越出文件
    """
    out = []
    if before:
        start = max(1, lineno - count)
        for n in range(start, lineno):
            out.append({"line": n, "text": lines[n - 1]})
    else:
        end = min(len(lines), lineno + count)
        for n in range(lineno + 1, end + 1):
            out.append({"line": n, "text": lines[n - 1]})
    return out


def _collect_file_matches(f, regex, glob, context, current_total):
    """在单个文件内按正则收集匹配行，可附带匹配行上下各若干行。

    @param context       匹配行上下各附带的上下文行数；0 表示只返回匹配行本身
    @param current_total 本次搜索已收集的匹配总数（含此前文件）
    @return 该文件新增的匹配列表；文件不可读或不符合 glob 时为空

    截断语义与原实现一致：一旦总数达到上限，本文件内层循环即停止，
    但外层仍会继续遍历后续文件（每文件最多再贡献一条）。
    """
    if glob and not fnmatch.fnmatch(f.name, glob):
        return []
    try:
        text = f.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    lines = text.splitlines()
    hits = []
    for i, line in enumerate(lines, 1):
        if regex.search(line):
            hit = {"file": str(f), "line": i, "text": line}
            # context 大于 0 时才附带上下文，避免默认结果无谓变大
            if context > 0:
                hit["contextBefore"] = _context_lines(lines, i, context, True)
                hit["contextAfter"] = _context_lines(lines, i, context, False)
            hits.append(hit)
            if current_total + len(hits) >= _SEARCH_MATCH_LIMIT:
                break
    return hits


def t_search_content(p):
    """按正则搜索文件内容，返回匹配行；结果超限时改为报错并提示缩小范围。"""
    _require(p, "pattern")
    pattern = p.get("pattern", "")
    path = p.get("path", ".")
    glob = p.get("glob")
    case = p.get("caseSensitive", False)
    # 上下文行数：非法或负数一律按 0 处理（只返回匹配行本身）
    try:
        context = int(p.get("contextAround") or 0)
    except (TypeError, ValueError):
        context = 0
    context = max(0, context)
    regex = re.compile(pattern, 0 if case else re.IGNORECASE)
    root = _abspath(path)
    files = root.rglob("*") if root.is_dir() else [root]
    matches = []
    for f in files:
        if not f.is_file():
            continue
        matches += _collect_file_matches(f, regex, glob, context, len(matches))
    return enforce_size_limit(
        {"count": len(matches), "matches": matches},
        "请缩小搜索范围后重试：用更精确的 pattern、加 glob 限定文件类型，或把 path 指向更具体的子目录。",
    )


def _read_text_segment(fp, offset, limit):
    """按行读取文件片段（fp 为绝对路径），返回内容与行数。"""
    offset = int(offset or 1)
    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    start = max(0, offset - 1)
    end = len(lines) if limit is None else start + int(limit)
    return {
        "path": str(fp),
        "content": "".join(lines[start:end]),
        "total_lines": len(lines),
        "_read_lines": max(0, end - start),
    }


def t_read_file(p):
    """读取文件内容，支持 offset / limit 分段。

    路径口径与写文件类工具保持一致：绝对路径原样使用，相对路径以工程根为基准解析。
    """
    _normalize_aliases(p)
    _require(p, "filePath")
    fp = _abspath(p.get("filePath"))
    res = _read_text_segment(fp, p.get("offset", 1), p.get("limit"))
    read_lines = res.pop("_read_lines")
    total = res["total_lines"]
    return enforce_size_limit(
        res,
        "请减少读取行数后重试：用 offset 指定起始行、limit 指定读取行数，分段读取；"
        "本次读取约 %d 行（文件共 %d 行），请改读更少的行。" % (read_lines, total),
    )


def t_list_skills(p):
    """列出本机可用的 skill：返回 [{ name, summary }]。"""
    return {"skills": list_skills(), "skillsDir": str(SKILLS_ROOT)}


def t_read_skill(p):
    """读取某个 skill 目录下的文档：按 skill 名 + skill 内相对路径定位。

    这是「按名字读取 skill 文档」的专用通道，替代以往用 read_file 传
    「skills/xxx/SKILL.md」相对路径的耦合做法。
    """
    _require(p, "skill", "file")
    fp = _resolve_skill_file(p.get("skill"), p.get("file"))
    if not fp.is_file():
        raise ToolParamError("文件不存在：%s（skill=%s）" % (p.get("file"), p.get("skill")))
    res = _read_text_segment(fp, p.get("offset", 1), p.get("limit"))
    read_lines = res.pop("_read_lines")
    total = res["total_lines"]
    res["skill"] = str(p.get("skill")).strip()
    res["file"] = str(p.get("file")).strip()
    return enforce_size_limit(
        res,
        "请减少读取行数后重试：用 offset 指定起始行、limit 指定读取行数，分段读取；"
        "本次读取约 %d 行（文件共 %d 行），请改读更少的行。" % (read_lines, total),
    )


def t_read_lints(p):
    """读取 linter 诊断：本地服务未集成 linter，返回空诊断。"""
    return enforce_size_limit(
        {"diagnostics": [], "note": "本地服务未集成 linter，返回空诊断。"},
        "请缩小 paths / severity 范围后重试。",
    )


def t_replace_in_file(p):
    """在文件中做精确字符串替换，要求 old_str 唯一。"""
    _normalize_aliases(p)
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
    """创建或覆盖写入完整文件内容（父目录不存在时自动创建）。"""
    _normalize_aliases(p)
    _require(p, "filePath", "content")
    fp = _abspath(p.get("filePath"))
    content = p.get("content", "")
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return {"written": True, "file": str(fp), "bytes": len(content.encode("utf-8"))}


def t_delete_file(p):
    """删除指定文件。"""
    _normalize_aliases(p)
    _require(p, "target_file")
    fp = _abspath(p.get("target_file"))
    os.remove(fp)
    return {"deleted": True, "file": str(fp)}


def t_list_rules(p):
    """列出可用规则文件。"""
    import rules
    return {"rules": rules.list_rules(), "rulesDir": str(rules.RULES_DIR)}


def t_read_rule(p):
    """按规则名读取规则全文。"""
    import rules
    _require(p, "name")
    name = str(p.get("name")).strip()
    if not rules.valid_name(name):
        raise ToolParamError("规则名非法：%s（仅允许字母、数字、下划线、连字符）" % name)
    try:
        content = rules.read_rule(name)
    except FileNotFoundError:
        available = [r["name"] for r in rules.list_rules()]
        raise ToolParamError("规则不存在：%s（可用规则：%s）" % (name, ", ".join(available) or "无"))
    return {"name": name, "content": content}


def t_get_tool_params(p):
    """按工具 id 返回其参数定义。

    查询范围与 /tools 目录来源保持一致（内置 + 自定义 + 外部）：
    外部工具（executor=external，如 debug_chrome 提供的 get_element_style）
    注册在 custom_tools 中而不在 TOOLS 里，只查 TOOLS 会一律返回「未知工具 id」，
    与设置页显示「已安装且在线」相互矛盾。
    """
    tid = p.get("tool_id") or p.get("tool")
    # 1) 内置工具
    if tid in TOOLS:
        entry = TOOLS[tid]
        resp = {"tool": tid, "description": entry["description"], "parameters": entry["parameters"]}
        if tid == "run_command":
            resp["languages"] = _load_run_command_languages()
            resp["note"] = "language 参数只接受上述 languages 列表中的值；command 内容按所选语言执行。"
        return resp
    # 2) 自定义 / 外部工具（来自标准 skill 的 tool.json）
    import custom_tools as ct
    ctool = ct.get_tool(tid)
    if ctool:
        return {
            "tool": tid,
            "description": ctool.get("description") or "",
            "parameters": ctool.get("parameters") or [],
            "executor": ctool.get("executor") or "script",
            "provider": ctool.get("provider") or "",
        }
    # 3) 都查不到：可用清单同样合并三类，避免提示信息与实际可调用范围不符
    available = sorted(set(
        list(TOOLS.keys()) + [t["name"] for t in ct.all_meta_full()]
    ))
    return {"error": "未知工具 id", "available": available}


# 工具名 → 实现函数的派发表
DISPATCH = {
    "list_dir": t_list_dir,
    "search_file": t_search_file,
    "search_content": t_search_content,
    "read_file": t_read_file,
    "list_skills": t_list_skills,
    "read_skill": t_read_skill,
    "read_lints": t_read_lints,
    "replace_in_file": t_replace_in_file,
    "write_to_file": t_write_to_file,
    "delete_file": t_delete_file,
    "get_tool_params": t_get_tool_params,
    "list_rules": t_list_rules,
    "read_rule": t_read_rule,
    "run_command": t_run_command,
}
