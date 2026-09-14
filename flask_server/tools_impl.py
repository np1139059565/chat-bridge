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
import json
import fnmatch
import sys
import shlex
import tempfile
import subprocess
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
    "list_rules": {
        "description": "列出本机可用的规则文件（规则名 + 摘要），供 AI 判断该读取哪条规则",
        "parameters": [],
    },
    "read_rule": {
        "description": "按规则名读取某条规则的完整内容（如 self-healing 异常自愈规则）",
        "parameters": [
            {"name": "name", "type": "string", "required": True, "description": "规则名（不含扩展名），先用 list_rules 获取"},
        ],
    },
    "run_command": {
        "description": "执行本地命令（按指定脚本语言选择解释器；支持的语言由后端配置决定）",
        "parameters": [
            {"name": "language", "type": "string", "required": True, "description": "脚本语言类型，如 python / shell / cmd / powershell / git 等（以 get_tool_params 返回的支持列表为准）"},
            {"name": "command", "type": "string", "required": True, "description": "要执行的命令或代码块内容"},
            {"name": "cwd", "type": "string", "required": False, "description": "工作目录，默认使用当前工程目录"},
            {"name": "timeout", "type": "integer", "required": False, "description": "超时秒数，默认 60 秒"},
        ],
    },
}


# ---------- 各工具实现 ----------
# 工程根目录（flask_server 的上一级）：相对路径以此为基准解析，
# 使 AI 可用 skills/xxx、extend/xxx 这类相对工程根的写法读取文件。
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _abspath(p):
    p = Path(p)
    if p.is_absolute():
        return p
    return (PROJECT_ROOT / p).resolve()


# 参数别名：调用方可能用 path / file 等写法指代 filePath，统一归一到规范名，
# 避免因别名导致「缺参」报错。
_PARAM_ALIASES = {
    "path": "filePath",
    "file": "filePath",
    "file_path": "filePath",
    "filepath": "filePath",
    "target_file": "filePath",
}


def _normalize_aliases(p):
    """把别名参数归一到规范参数名（仅补缺失项，不覆盖已有值）。"""
    if not isinstance(p, dict):
        return p
    for alias, real in _PARAM_ALIASES.items():
        if alias in p and real not in p:
            p[real] = p.get(alias)
    return p


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


# ---------- 结果 JSON 体积上限 ----------
# 各工具返回的 JSON 序列化后不得超过该字符数（默认 10 万，可在 config.yaml 的
# limits.max_json_chars 覆盖）。超限时不截断，而是返回参数错误并提示 AI 缩小范围，
# 避免把不完整的结果喂给 AI 导致误判。
DEFAULT_MAX_JSON_CHARS = 100000


def _max_json_chars():
    """读取 config.yaml 中 limits.max_json_chars；未配置时返回默认值。"""
    cfg_path = Path(__file__).resolve().parent / "config.yaml"
    try:
        import yaml
        with cfg_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        v = (data.get("limits") or {}).get("max_json_chars")
        if v is not None:
            v = int(v)
            if v > 0:
                return v
    except Exception:
        pass
    return DEFAULT_MAX_JSON_CHARS


def _dump_len(obj):
    """对象序列化为 JSON 后的字符数（无法序列化时按极大值处理）。"""
    try:
        return len(json.dumps(obj, ensure_ascii=False))
    except Exception:
        return 10 ** 12


def enforce_size_limit(result, guidance, max_chars=None):
    """校验工具结果的 JSON 体积；超限时返回错误，提示 AI 缩小范围后重试。

    - 不截断：宁可报错，也不把不完整的结果喂给 AI，避免其据此做出错误判断。
    - guidance：针对该工具的收敛建议（如缩小搜索范围 / 分段读取）。
    - 未超限时原样返回 result；超限时抛 ToolParamError（服务端归类为 parameter，
      提示 AI 这是调用范围问题，应调整参数而非修改工具代码）。
    """
    limit = max_chars if max_chars is not None else _max_json_chars()
    size = _dump_len(result)
    if size <= limit:
        return result
    raise ToolParamError(
        "结果体积约 %d 字符，超过上限 %d 字符。%s" % (size, limit, guidance)
    )


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
    # 结果超限不截断，改为报错并提示 AI 缩小搜索范围
    return enforce_size_limit(
        {"count": len(matches), "matches": matches},
        "请缩小搜索范围后重试：用更精确的 pattern、加 glob 限定文件类型，或把 path 指向更具体的子目录。",
    )


def t_read_file(p):
    _normalize_aliases(p)
    _require(p, "filePath")
    fp = _abspath(p.get("filePath"))
    offset = int(p.get("offset", 1) or 1)
    limit = p.get("limit")
    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    start = max(0, offset - 1)
    end = len(lines) if limit is None else start + int(limit)
    # 结果超限不截断，改为报错并提示 AI 减少读取行数
    return enforce_size_limit(
        {"path": str(fp), "content": "".join(lines[start:end]), "total_lines": len(lines)},
        "请减少读取行数后重试：用 offset 指定起始行、limit 指定读取行数，分段读取；"
        "本次读取约 %d 行（文件共 %d 行），请改读更少的行。" % (max(0, end - start), len(lines)),
    )


def t_read_lints(p):
    # 本地服务未集成 linter，返回空诊断即可
    return enforce_size_limit(
        {"diagnostics": [], "note": "本地服务未集成 linter，返回空诊断。"},
        "请缩小 paths / severity 范围后重试。",
    )


def t_replace_in_file(p):
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
    _normalize_aliases(p)
    _require(p, "filePath", "content")
    fp = _abspath(p.get("filePath"))
    content = p.get("content", "")
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return {"written": True, "file": str(fp), "bytes": len(content.encode("utf-8"))}


def t_delete_file(p):
    _normalize_aliases(p)
    _require(p, "target_file")
    fp = _abspath(p.get("target_file"))
    os.remove(fp)
    return {"deleted": True, "file": str(fp)}


def t_list_rules(p):
    import rules
    return {"rules": rules.list_rules(), "rulesDir": str(rules.RULES_DIR)}


def t_read_rule(p):
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
    tid = p.get("tool_id") or p.get("tool")
    if tid not in TOOLS:
        return {"error": "未知工具 id", "available": list(TOOLS.keys())}
    entry = TOOLS[tid]
    resp = {"tool": tid, "description": entry["description"], "parameters": entry["parameters"]}
    if tid == "run_command":
        resp["languages"] = _load_run_command_languages()
        resp["note"] = "language 参数只接受上述 languages 列表中的值；command 内容按所选语言执行。"
    return resp


# run_command 默认支持的语言：后端可通过 config.yaml 的 tools.run_command.languages 覆盖。
# 映射值为调用解释器时的首段命令；命令正文以参数/参数文件/标准输入方式传入。
RUN_COMMAND_SUPPORTED_LANGUAGES = ["cmd", "powershell", "shell", "git", "python"]
RUN_COMMAND_TIMEOUT = 60
RUN_COMMAND_LANGUAGE_COMMANDS = {
    "cmd": ["cmd", "/d", "/s", "/c"],
    "powershell": ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"],
    "shell": ["bash", "-lc"],
    "git": ["git"],
    "python": [sys.executable, "-c"],
}

LANG_ALIASES = {
    "bash": "shell", "sh": "shell", "shell": "shell",
    "pwsh": "powershell", "powershell": "powershell", "ps1": "powershell",
    "cmd": "cmd", "bat": "cmd", "dos": "cmd",
    "git": "git",
    "python": "python", "py": "python",
}


def _load_run_command_languages():
    """读取 config.yaml 中 tools.run_command.languages；失败或未配置时返回默认列表。"""
    cfg_path = Path(__file__).resolve().parent / "config.yaml"
    try:
        import yaml
        with cfg_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        langs = ((data.get("tools") or {}).get("run_command") or {}).get("languages")
        if isinstance(langs, list) and langs:
            return [str(x).strip().lower() for x in langs if str(x).strip()]
    except Exception:
        pass
    return list(RUN_COMMAND_SUPPORTED_LANGUAGES)


def t_run_command(p):
    _require(p, "language", "command")
    raw_lang = str(p.get("language") or "").strip().lower()
    command = p.get("command", "")
    if not str(command).strip():
        raise ToolParamError("command 不能为空")

    lang = LANG_ALIASES.get(raw_lang, raw_lang)
    supported = _load_run_command_languages()
    if lang not in supported:
        raise ToolParamError(
            "不支持的语言 %s；当前 run_command 支持：%s。若要使用请先在设置卡片中勾选该语言。"
            % (raw_lang, ", ".join(supported))
        )

    cmd_prefix = RUN_COMMAND_LANGUAGE_COMMANDS.get(lang)
    if not cmd_prefix:
        raise ToolParamError("语言 %s 暂未配置解释器映射" % lang)

    cwd = p.get("cwd") or ""
    if cwd:
        cwd_path = _abspath(cwd)
        if not cwd_path.is_dir():
            raise ToolParamError("工作目录不存在：%s" % cwd_path)
    else:
        cwd_path = Path.cwd()

    # git 命令是“子命令风格”，需要把命令字符串按 shell 分词后拼接；
    # 其余语言都遵循“解释器 + 标志 + 完整命令字符串”的形式，不拆分正文。
    if lang == "git":
        try:
            command_parts = shlex.split(str(command), posix=False)
        except ValueError as e:
            raise ToolParamError("git 命令解析失败：%s" % e)
        if not command_parts:
            raise ToolParamError("git 命令不能为空")
        cmd = list(cmd_prefix) + command_parts
    else:
        cmd = list(cmd_prefix) + [str(command)]

    timeout = int(p.get("timeout") or RUN_COMMAND_TIMEOUT)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            timeout=timeout,
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
    except FileNotFoundError as e:
        raise FileNotFoundError("无法启动命令（解释器或程序缺失）：%s" % e)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "language": lang,
            "exitCode": None,
            "stdout": "",
            "stderr": "命令执行超时（%s 秒）" % timeout,
            "cwd": str(cwd_path),
        }

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    return {
        "ok": proc.returncode == 0,
        "language": lang,
        "exitCode": proc.returncode,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
        "cwd": str(cwd_path),
    }


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
    "list_rules": t_list_rules,
    "read_rule": t_read_rule,
    "run_command": t_run_command,
}
