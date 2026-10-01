"""AI 工具调用镜像插件 —— run_command 工具实现

本模块承载 run_command 的语言配置与执行逻辑，从 tools_impl.py 拆出，
使实现文件保持在文件行数上限内，并让「按语言执行命令」这一独立关注点自成一体。

对外接口：
- RUN_COMMAND_SUPPORTED_LANGUAGES  默认支持的语言列表（config_store 会读取）
- RUN_COMMAND_TIMEOUT              默认超时（秒）
- t_run_command(p)                 工具入口（签名与其它 t_xxx 一致）

依赖：tool_helpers（ToolParamError / abspath）
"""
import os
import shlex
import subprocess
import sys
from pathlib import Path

from tool_helpers import ToolParamError, abspath as _abspath


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


def _resolve_timeout(raw):
    """解析命令超时（秒）：未传用默认值，非正整数抛参数错误。

    显式区分「未传」与「传了非法值」：以前用 `or` 兜底会把 0 静默替换成默认值，
    调用方以为已关闭或缩短超时，实际仍按 60 秒执行，行为与预期不符。
    """
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return RUN_COMMAND_TIMEOUT
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ToolParamError("timeout 必须是正整数（秒），收到：%r" % (raw,))
    if value <= 0:
        raise ToolParamError("timeout 必须大于 0（秒），收到：%d" % value)
    return value


def _prepare_run(p):
    """校验并准备执行参数，返回 (lang, cwd_path, cmd, timeout)。"""
    from tool_helpers import require as _require
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
    timeout = _resolve_timeout(p.get("timeout"))
    return lang, cwd_path, cmd, timeout


def _spawn_run(cmd, cwd_path, timeout):
    """启动子进程执行命令；解释器缺失转为环境类错误，超时返回 None。

    走 proc_runner 而非 subprocess.run：后者超时只杀直接子进程，
    若子进程派生了持有输出管道的孙进程（git 交互、编辑器等），
    超时会一直被拖到孙进程退出才返回——超时保护形同虚设。
    proc_runner 超时杀整棵进程树，确保超时真正生效。
    """
    from proc_runner import run_with_tree_timeout
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = run_with_tree_timeout(cmd, cwd=str(cwd_path), timeout=timeout, env=env)
    if res.timed_out:
        return None
    # ProcResult 是 namedtuple，本身即带 returncode/stdout/stderr，
    # 与 _run_result 期望的字段一致，直接返回即可。
    return res


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
