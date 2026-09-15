"""AI 工具调用镜像插件 —— 本地工具实现（支持热重载）

单独拆出本模块的原因：
1. AI 自愈时可直接改写本文件，再用 hot_reload_fix 热重载，无需重启 Flask 服务；
2. 热重载失败可整体回滚，不会把服务本身搞挂。

约定：
- 参数不合法（缺失 / 类型错 / 取值非法）请抛 ToolParamError；
  其他异常一律视为「工具内部代码缺陷」，AI 会据此决定改参数还是改代码。

本文件保留「可整体热重载的单元」语义：TOOLS 元数据、t_xxx 实现与 DISPATCH 都在此处。
不随调用变化的通用辅助（参数校验、路径解析、体积控制）已下沉到 tool_helpers，
并在此处重导出，保证 impl.ToolParamError 等既有引用不变。
"""
import os
import re
import fnmatch
import sys
import shlex
import subprocess
from pathlib import Path

from tool_meta import TOOLS
from tool_helpers import (
    ToolParamError,  # 重导出：服务侧通过 runtime.impl.ToolParamError 判定参数错误
    PROJECT_ROOT,
    SKILLS_ROOT,
    abspath as _abspath,
    require_abspath as _require_abspath,
    resolve_skill_file as _resolve_skill_file,
    normalize_aliases as _normalize_aliases,
    require as _require,
    enforce_size_limit,
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


def t_search_file(p):
    """按文件名通配符递归（或单层）搜索文件。"""
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


# 单次 search_content 的结果条数上限：超出后停止继续收集，交给体积上限进一步把关
_SEARCH_MATCH_LIMIT = 200


def _collect_file_matches(f, regex, glob, current_total):
    """在单个文件内按正则收集匹配行。

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
    hits = []
    for i, line in enumerate(text.splitlines(), 1):
        if regex.search(line):
            hits.append({"file": str(f), "line": i, "text": line})
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
    regex = re.compile(pattern, 0 if case else re.IGNORECASE)
    root = _abspath(path)
    files = root.rglob("*") if root.is_dir() else [root]
    matches = []
    for f in files:
        if not f.is_file():
            continue
        matches += _collect_file_matches(f, regex, glob, len(matches))
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
    """读取文件内容（仅接受绝对路径），支持 offset / limit 分段。"""
    _normalize_aliases(p)
    _require(p, "filePath")
    fp = _require_abspath(p.get("filePath"))
    res = _read_text_segment(fp, p.get("offset", 1), p.get("limit"))
    read_lines = res.pop("_read_lines")
    total = res["total_lines"]
    return enforce_size_limit(
        res,
        "请减少读取行数后重试：用 offset 指定起始行、limit 指定读取行数，分段读取；"
        "本次读取约 %d 行（文件共 %d 行），请改读更少的行。" % (read_lines, total),
    )


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
    """按工具 id 返回其参数定义；run_command 额外附带可选语言列表。"""
    tid = p.get("tool_id") or p.get("tool")
    if tid not in TOOLS:
        return {"error": "未知工具 id", "available": list(TOOLS.keys())}
    entry = TOOLS[tid]
    resp = {"tool": tid, "description": entry["description"], "parameters": entry["parameters"]}
    if tid == "run_command":
        resp["languages"] = _load_run_command_languages()
        resp["note"] = "language 参数只接受上述 languages 列表中的值；command 内容按所选语言执行。"
    return resp


# ---------- run_command 的语言配置 ----------
# 默认支持的语言：后端可通过 config.yaml 的 tools.run_command.languages 覆盖。
# 注意「默认列表」与「解释器映射」是两个独立概念：
#   - 前者决定 AI 能否用某语言（可在设置页勾选）；
#   - 后者决定该语言实际怎么被调用，二者需同时具备才能执行。
RUN_COMMAND_SUPPORTED_LANGUAGES = ["cmd", "powershell", "shell", "git", "python"]

# 默认超时（秒）：单次命令执行超过该时长即返回超时结果，避免长时间挂起。
RUN_COMMAND_TIMEOUT = 60

# 语言 → 解释器命令前缀。
# 映射值为调用解释器时的首段命令；命令正文以参数形式追加在末尾（git 例外，见 _build_run_command）。
#   - cmd        ：以 /c 执行整段命令字符串
#   - powershell ：-Command 后接整段脚本，禁用 profile 与交互以保证可重复
#   - shell      ：bash -lc，登录式 shell 以便加载常用环境变量
#   - git        ：命令正文需按子命令风格分词（如 git status --short）
#   - python     ：当前解释器 -c，保证与后端运行环境一致
RUN_COMMAND_LANGUAGE_COMMANDS = {
    "cmd": ["cmd", "/d", "/s", "/c"],
    "powershell": ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"],
    "shell": ["bash", "-lc"],
    "git": ["git"],
    "python": [sys.executable, "-c"],
}

# 语言别名：把 bash / sh / pwsh 等写法归一到规范语言名
LANG_ALIASES = {
    "bash": "shell", "sh": "shell", "shell": "shell",
    "pwsh": "powershell", "powershell": "powershell", "ps1": "powershell",
    "cmd": "cmd", "bat": "cmd", "dos": "cmd",
    "git": "git",
    "python": "python", "py": "python",
}


def _normalize_langs(langs):
    """把语言列表规范化为小写、去空的字符串列表；非法输入返回 None。"""
    if not isinstance(langs, list) or not langs:
        return None
    return [str(x).strip().lower() for x in langs if str(x).strip()]


def _read_langs_from_yaml():
    """从 config.yaml 读取 tools.run_command.languages；失败或未配置时返回 None。"""
    # 配置文件读取统一走 yaml_utils.load_config_dict，避免多处重复实现
    import yaml_utils
    data = yaml_utils.load_config_dict()
    return _normalize_langs(((data.get("tools") or {}).get("run_command") or {}).get("languages"))


def _load_run_command_languages():
    """读取 config.yaml 中 tools.run_command.languages；失败或未配置时返回默认列表。"""
    langs = _read_langs_from_yaml()
    if langs:
        return langs
    return list(RUN_COMMAND_SUPPORTED_LANGUAGES)


def _resolve_run_lang(raw_lang):
    """把语言别名归一为规范名，并校验其在当前支持列表内。"""
    lang = LANG_ALIASES.get(raw_lang, raw_lang)
    supported = _load_run_command_languages()
    if lang not in supported:
        raise ToolParamError(
            "不支持的语言 %s；当前 run_command 支持：%s。若要使用请先在设置卡片中勾选该语言。"
            % (raw_lang, ", ".join(supported))
        )
    return lang


def _resolve_run_cwd(cwd):
    """解析工作目录：未指定时用当前进程目录；指定时必须存在。"""
    if not cwd:
        return Path.cwd()
    cwd_path = _abspath(cwd)
    if not cwd_path.is_dir():
        raise ToolParamError("工作目录不存在：%s" % cwd_path)
    return cwd_path


def _build_run_command(lang, cmd_prefix, command):
    """拼装命令列表：git 按子命令风格分词，其余语言整段作为单个参数。"""
    if lang != "git":
        return list(cmd_prefix) + [str(command)]
    try:
        command_parts = shlex.split(str(command), posix=False)
    except ValueError as e:
        raise ToolParamError("git 命令解析失败：%s" % e)
    if not command_parts:
        raise ToolParamError("git 命令不能为空")
    return list(cmd_prefix) + command_parts


def _prepare_run(p):
    """校验并准备执行参数，返回 (lang, cwd_path, cmd, timeout)。"""
    _require(p, "language", "command")
    raw_lang = str(p.get("language") or "").strip().lower()
    command = p.get("command", "")
    if not str(command).strip():
        raise ToolParamError("command 不能为空")
    lang = _resolve_run_lang(raw_lang)
    cmd_prefix = RUN_COMMAND_LANGUAGE_COMMANDS.get(lang)
    if not cmd_prefix:
        raise ToolParamError("语言 %s 暂未配置解释器映射" % lang)
    cwd_path = _resolve_run_cwd(p.get("cwd") or "")
    cmd = _build_run_command(lang, cmd_prefix, command)
    timeout = int(p.get("timeout") or RUN_COMMAND_TIMEOUT)
    return lang, cwd_path, cmd, timeout


def _spawn_run(cmd, cwd_path, timeout):
    """启动子进程执行命令；解释器缺失转为环境类错误，超时返回 None。"""
    try:
        return subprocess.run(
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
        return None


def _run_result(lang, cwd_path, proc):
    """把子进程结果规整为统一返回结构。"""
    return {
        "ok": proc.returncode == 0,
        "language": lang,
        "exitCode": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "cwd": str(cwd_path),
    }


def t_run_command(p):
    """按指定语言执行命令，返回退出码与输出；超时返回 ok=False。"""
    lang, cwd_path, cmd, timeout = _prepare_run(p)
    proc = _spawn_run(cmd, cwd_path, timeout)
    if proc is None:
        # 超时：返回结构化的失败结果，交由上层原样回传
        return {
            "ok": False,
            "language": lang,
            "exitCode": None,
            "stdout": "",
            "stderr": "命令执行超时（%s 秒）" % timeout,
            "cwd": str(cwd_path),
        }
    return _run_result(lang, cwd_path, proc)


# 工具名 → 实现函数的派发表（自愈工具由服务侧在 _reload_impl 时并入）
DISPATCH = {
    "list_dir": t_list_dir,
    "search_file": t_search_file,
    "search_content": t_search_content,
    "read_file": t_read_file,
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
