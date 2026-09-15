"""自定义工具（来自标准 skill）—— 注册表与执行

职责：
1. custom_tools.yaml 的读写（load_tools / save_tools）
2. 工具的安装 / 删除 / 更新 / 查询（install / remove / update / get_tool / is_enabled）
3. 本地子进程执行（run）

安装时会与内置工具做重名冲突校验；执行失败由上层 server 分类为
parameter / environment / tool_internal。
"""
import json
import os
import subprocess
from pathlib import Path

from .loader import dump_yaml, parse_yaml, parse_skill, infer_interpreter, to_str, flag_arg
from .paths import CT_PATH, resolve_to_abs


# ---------- 读取 / 落盘 ----------
def load_tools():
    """读取 custom_tools.yaml 并转为 { 工具名: 工具字典 }；解析失败返回空字典。"""
    if not CT_PATH.exists():
        return {}
    try:
        tools = parse_yaml(CT_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print("[custom_tools] 解析 custom_tools.yaml 失败：", e)
        return {}
    out = {}
    for t in tools:
        if isinstance(t, dict) and t.get("name"):
            out[t["name"]] = t
    return out


def save_tools(tools):
    """把工具字典写回 custom_tools.yaml；失败返回 False。"""
    try:
        CT_PATH.write_text(dump_yaml(list(tools.values())), encoding="utf-8")
        return True
    except Exception as e:
        print("[custom_tools] 写回 custom_tools.yaml 失败：", e)
        return False


# ---------- 安装 / 删除 / 更新 ----------
def install(skill_dir, names=None):
    """安装一个 skill 里的工具（names 为空表示全部）。返回已安装的工具名列表。"""
    import tools_impl  # 仅用于冲突校验
    parsed = parse_skill(skill_dir)
    tools = load_tools()
    installed = []
    for t in parsed:
        if names and t["name"] not in names:
            continue
        if t["name"] in tools_impl.DISPATCH:
            raise ValueError("工具名 %s 与内置工具冲突，请改名后再安装" % t["name"])
        tools[t["name"]] = t
        installed.append(t["name"])
    if installed:
        save_tools(tools)
    return installed


def remove(name):
    """删除一个自定义工具；存在并删除成功返回 True。"""
    tools = load_tools()
    if name in tools:
        del tools[name]
        save_tools(tools)
        return True
    return False


def _normalize_param(p):
    """把单个参数项规范化为统一结构。"""
    return {
        "name": (p.get("name") or ""),
        "type": (p.get("type") or "string"),
        "required": bool(p.get("required")),
        "description": (p.get("description") or ""),
    }


def _apply_scalar_fields(t, patch):
    """应用标量字段：描述 / 解释器 / 参数风格（仅接受非空值）与 enabled 开关。"""
    for field in ("description", "interpreter", "arg_style"):
        if field in patch and patch[field] not in (None, ""):
            t[field] = patch[field]
    if "enabled" in patch:
        t["enabled"] = bool(patch["enabled"])


def _apply_list_fields(t, patch):
    """应用列表字段：参数表（逐项规范化）与固定参数。"""
    if isinstance(patch.get("parameters"), list):
        t["parameters"] = [_normalize_param(p) for p in patch["parameters"] if isinstance(p, dict)]
    if isinstance(patch.get("fixed_args"), list):
        t["fixed_args"] = list(patch["fixed_args"])


def update(name, patch):
    """部分更新一个自定义工具（描述 / 解释器 / 参数风格 / 开关 / 参数表 / 固定参数）。

    返回更新后的工具字典；工具不存在返回 None。
    """
    tools = load_tools()
    t = tools.get(name)
    if not t:
        return None
    _apply_scalar_fields(t, patch)
    _apply_list_fields(t, patch)
    save_tools(tools)
    return t


def get_tool(name):
    """按名取工具定义；不存在返回 None。"""
    return load_tools().get(name)


def is_enabled(name):
    """判断自定义工具是否已上线。"""
    t = load_tools().get(name)
    return bool(t.get("enabled")) if t else False


# ---------- 执行 ----------
def _positional_args(params, declared):
    """按声明顺序把参数值拼成位置参数（boolean 为真才追加 --名）。"""
    out = []
    for p in declared:
        nm = p.get("name")
        if nm not in params:
            continue
        val = params[nm]
        if isinstance(val, bool):
            if val:
                out.append("--" + nm)
        elif isinstance(val, list):
            for el in val:
                out.append(to_str(el))
        elif val not in (None, ""):
            out.append(to_str(val))
    return out


def _resolve_script_path(tool, skill_dir):
    """解析脚本绝对路径：绝对路径原样，相对路径相对 skill 目录。"""
    script = tool["script"]
    if Path(script).is_absolute():
        return Path(script)
    return skill_dir / script


def _flag_args(params, declared):
    """flag 风格：每个已传参数展开为 --名 值。"""
    out = []
    for p in declared:
        nm = p.get("name")
        if nm in params:
            out += flag_arg(nm, params[nm])
    return out


def _build_command(tool, params, skill_dir):
    """把工具定义与参数拼装为命令行列表。

    - arg_style=flag（默认）：string/number → --名 值；boolean 为真 → --名；array → 每个元素一个 --名 值
    - arg_style=positional：按 parameters 声明顺序，把值依次作为位置参数（boolean 为真才传 --名）
    """
    script = tool["script"]
    script_path = _resolve_script_path(tool, skill_dir)
    cmd = []
    it = tool.get("interpreter") or infer_interpreter(script)
    if it:
        cmd.append(it)
    cmd.append(str(script_path))
    # 固定前置参数
    for a in tool.get("fixed_args") or []:
        cmd.append(to_str(a))
    declared = tool.get("parameters") or []
    if (tool.get("arg_style") or "flag") == "flag":
        cmd += _flag_args(params, declared)
    else:
        cmd += _positional_args(params, declared)
    return cmd


def _validate_required(tool, params):
    """必填参数校验：缺失时抛 ValueError（服务端归类为 parameter）。"""
    for p in tool.get("parameters") or []:
        nm = p.get("name")
        if p.get("required") and (nm not in params or params[nm] in (None, "")):
            raise ValueError("缺少必填参数 %s（工具 %s）" % (nm, tool.get("name")))


def _spawn(cmd, skill_dir):
    """启动子进程执行命令；解释器或脚本缺失时转为环境类错误。"""
    try:
        # Windows 上子进程默认按 GBK 写 stdout，强制 UTF-8 以免中文乱码（mojibake）。
        child_env = dict(os.environ)
        child_env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            cmd, cwd=str(skill_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", shell=False, env=child_env,
        )
    except FileNotFoundError as e:
        # 解释器或脚本缺失 → 环境/路径类
        raise FileNotFoundError("无法启动脚本（解释器或脚本缺失）：" + str(e))


def _normalize_output(proc):
    """把子进程输出规整为结果 dict：合法 JSON 原样返回，否则包成 {"stdout": ...}。"""
    if proc.returncode != 0:
        err = (proc.stderr or "").strip() or (proc.stdout or "").strip()
        raise RuntimeError("脚本退出码 %d：%s" % (proc.returncode, err[:2000]))
    out = (proc.stdout or "").strip()
    if not out:
        return {"stdout": ""}
    try:
        return json.loads(out)
    except Exception:
        return {"stdout": out}


def run(tool, params):
    """执行一个自定义工具脚本，返回结果 dict。失败抛异常，由 server 层分类。"""
    params = params or {}
    _validate_required(tool, params)
    skill_dir = resolve_to_abs(tool["skill_dir"])
    cmd = _build_command(tool, params, skill_dir)
    proc = _spawn(cmd, skill_dir)
    return _normalize_output(proc)
