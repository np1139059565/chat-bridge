"""自定义工具（来自标准 skill）—— 解析层

职责：
1. custom_tools.yaml 的受限解析与写出（tools 列表 + 可选 fixed_args / parameters 子列表）
2. skill 目录的 tool.json 解析与规范化（parse_skill）
3. 命令拼装辅助：解释器推断、参数转字符串

YAML 标量级处理（去注释 / 标量转换 / 引号转义）复用 yaml_utils，
与 config.yaml 侧共用同一套规则。
"""
import json
import os
import subprocess
from pathlib import Path

import yaml_utils
from .paths import NAME_RE, resolve_to_abs, to_project_rel


# ---------- custom_tools.yaml：无 PyYAML 时的专用受限解析（本模块自有格式） ----------
def strip_comment(s):
    """去掉行首或空白后的 # 注释，但引号内的 # 不当注释（描述里可能含 #）。

    实现已下沉到 yaml_utils.strip_comment，与 config.yaml 侧共用同一套规则。
    """
    return yaml_utils.strip_comment(s)


def parse_scalar(v):
    """把 YAML 标量字符串转成 Python 值。

    实现已下沉到 yaml_utils.coerce_scalar，与 config.yaml 侧共用同一套规则。
    """
    return yaml_utils.coerce_scalar(v)


def quote(s):
    """把字符串转义并包上双引号，用于写出 YAML 标量。

    实现已下沉到 yaml_utils.quote，与 config.yaml 侧共用同一套规则。
    """
    return yaml_utils.quote(s)


def _new_parse_ctx():
    """创建解析上下文：承载当前工具、当前参数与所在子列表。"""
    return {
        "tools": [],          # 已完成的工具列表
        "cur_tool": None,     # 正在解析的工具
        "cur_param": None,    # 正在解析的参数项（parameters 子列表中）
        "list_section": None, # 'fixed_args' | 'parameters' | None
    }


def _flush_tool(ctx):
    """把当前正在解析的工具收尾并放进结果列表。"""
    if ctx["cur_tool"] is not None:
        ctx["tools"].append(ctx["cur_tool"])


def _parse_tool_item(rest, indent, ctx):
    """处理以 '- ' 开头的行：新工具条目，或 fixed_args / parameters 的子项。"""
    if indent <= 4:
        # 新工具条目：  - name: xxx
        _flush_tool(ctx)
        ctx["cur_tool"] = {}
        ctx["cur_param"] = None
        ctx["list_section"] = None
        if rest:
            k, _, val = rest.partition(":")
            ctx["cur_tool"][k.strip()] = parse_scalar(val)
        return
    # 子列表条目（缩进 >= 6）
    if ctx["cur_tool"] is None:
        return
    if ctx["list_section"] == "parameters":
        ctx["cur_param"] = {}
        ctx["cur_tool"].setdefault("parameters", []).append(ctx["cur_param"])
        if rest:
            k, _, val = rest.partition(":")
            ctx["cur_param"][k.strip()] = parse_scalar(val)
    elif ctx["list_section"] == "fixed_args":
        ctx["cur_tool"].setdefault("fixed_args", []).append(parse_scalar(rest))


def _parse_key_value(body, ctx):
    """处理 'key: value' 行，写入当前参数或当前工具的对应位置。"""
    k, _, val = body.partition(":")
    key = k.strip()
    value = val.strip()
    # 参数项内部的字段
    if ctx["cur_param"] is not None:
        ctx["cur_param"][key] = parse_scalar(value)
        return
    if ctx["cur_tool"] is None:
        return
    # 空值表示进入子列表（fixed_args / parameters）
    if value == "":
        ctx["list_section"] = key
        return
    if ctx["list_section"] == "parameters" and ctx["cur_param"] is not None:
        ctx["cur_param"][key] = parse_scalar(value)
    else:
        ctx["cur_tool"][key] = parse_scalar(value)


def parse_yaml(text):
    """解析 custom_tools.yaml：tools 下是工具列表，每个工具含可选 fixed_args / parameters 子列表。"""
    ctx = _new_parse_ctx()
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        # 顶格行：只识别 tools: 起始
        if indent == 0:
            k, _, val = body.partition(":")
            if k.strip() == "tools" and val.strip() == "":
                ctx["cur_tool"] = None
                ctx["cur_param"] = None
                ctx["list_section"] = None
            continue
        if body.startswith("- "):
            _parse_tool_item(body[2:].strip(), indent, ctx)
            continue
        _parse_key_value(body, ctx)
    _flush_tool(ctx)
    return ctx["tools"]


# 写出工具时按固定顺序输出的字符串字段
_TOOL_STR_FIELDS = ("description", "skill_name", "skill_prompt", "skill_dir",
                    "script", "interpreter", "arg_style", "executor", "provider")


def _dump_tool_entry(t):
    """把单个工具序列化为 YAML 行片段列表。"""
    out = ["  - name: " + quote(t.get("name", ""))]
    # 非空字符串字段按固定顺序写出，保证 diff 稳定
    for key in _TOOL_STR_FIELDS:
        if t.get(key) not in (None, ""):
            out.append("    %s: %s" % (key, quote(t[key])))
    # silent 为布尔标记，仅在为真时写出
    if t.get("silent"):
        out.append("    silent: true")
    out.append("    enabled: %s" % ("true" if t.get("enabled") else "false"))
    out += _dump_fixed_args(t.get("fixed_args") or [])
    out += _dump_params(t.get("parameters") or [])
    return out


def _dump_fixed_args(fa):
    """写出 fixed_args 子列表；为空时返回空列表。"""
    if not fa:
        return []
    out = ["    fixed_args:"]
    for a in fa:
        out.append("      - %s" % quote(a))
    return out


def _dump_params(params):
    """写出 parameters 子列表；为空时返回空列表。"""
    if not params:
        return []
    out = ["    parameters:"]
    for p in params:
        out.append("      - name: " + quote(p.get("name", "")))
        if p.get("type"):
            out.append("        type: " + quote(p["type"]))
        out.append("        required: %s" % ("true" if p.get("required") else "false"))
        if p.get("description"):
            out.append("        description: " + quote(p["description"]))
    return out


def dump_yaml(tools):
    """把工具列表写回 custom_tools.yaml 的文本形式（保持既有缩进约定）。"""
    out = [
        "# AI 工具调用镜像 · 自定义工具（由标准 skill 安装）",
        "# 本文件由插件自动维护；建议通过设置页修改，手工编辑请严格保持缩进。",
        "tools:",
    ]
    for t in tools:
        out += _dump_tool_entry(t)
    return "\n".join(out) + "\n"


# ---------- 命令拼装辅助 ----------
def infer_interpreter(script):
    """按脚本扩展名推断解释器；未知扩展名返回空串。"""
    ext = Path(script).suffix.lower()
    return {".py": "python", ".js": "node", ".sh": "bash",
            ".ps1": "powershell", ".rb": "ruby"}.get(ext, "")


def to_str(v):
    """把参数值转成命令行字符串（None 视为空串）。"""
    return "" if v is None else str(v)


def flag_arg(name, val):
    """把参数转成 --名 值 形式的命令行片段（boolean 为真只给标志）。"""
    flag = "--" + name
    if isinstance(val, bool):
        return [flag] if val else []
    if isinstance(val, list):
        r = []
        for el in val:
            r += [flag, to_str(el)]
        return r
    if val in (None, ""):
        return []
    return [flag, to_str(val)]


# ---------- skill 解析 ----------
def _read_tool_spec(d):
    """读取并解析 skill 目录下的 tool.json。

    @param d skill 目录的绝对路径
    @return (spec, provider, skill_prompt)：原始 JSON、顶层 provider、顶层 prompt
    """
    if not d.is_dir():
        raise ValueError("目录不存在：" + str(d))
    tf = d / "tool.json"
    if not tf.exists():
        raise FileNotFoundError("该目录不是可安装 skill（缺少 tool.json）：" + str(d))
    try:
        spec = json.loads(tf.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError("tool.json 解析失败：" + str(e))
    # 顶层 provider：声明该 skill 的工具由哪个外部提供方执行（可空）
    # 顶层 prompt：技能统一说明，供 System Prompt 注入（可空）
    provider = ""
    skill_prompt = ""
    if isinstance(spec, dict):
        provider = (spec.get("provider") or "").strip()
        skill_prompt = (spec.get("prompt") or "").strip()
    return spec, provider, skill_prompt


def _normalize_raw_list(spec):
    """把 tool.json 的三种写法（{tools:[...]} / [...] / 单个对象）统一成工具对象列表。"""
    if isinstance(spec, dict) and "tools" in spec:
        raw_list = spec["tools"]
    elif isinstance(spec, list):
        raw_list = spec
    else:
        raw_list = [spec]
    if not isinstance(raw_list, list):
        raw_list = [raw_list]
    return raw_list


def _parse_tool_params(raw, name):
    """解析并校验单个工具的参数表，返回规范化后的参数列表。"""
    params = []
    for p in (raw.get("parameters") or []):
        pname = (p.get("name") if isinstance(p, dict) else None) or ""
        if not pname:
            raise ValueError("工具 %s 存在缺少 name 的参数" % name)
        if not NAME_RE.match(pname):
            raise ValueError("工具 %s 的参数名非法：" % name + pname)
        params.append({
            "name": pname,
            "type": (p.get("type") or "string"),
            "required": bool(p.get("required")),
            "description": (p.get("description") or ""),
        })
    return params


def _resolve_tool_script(raw, name, executor, provider, d):
    """解析工具的脚本路径并做存在性校验。

    executor=external 的工具不在本地执行，无需脚本文件，返回 (None, "")。
    其余情况返回 (script_path 或 None, 落盘用的 script 字符串)。
    """
    script = (raw.get("script") or "").strip()
    if executor == "external":
        if not (raw.get("provider") or provider):
            raise ValueError("工具 %s 为 external，但缺少 provider" % name)
        return None, ""
    if not script:
        raise ValueError("工具 %s 缺少 script" % name)
    sp = Path(script)
    if sp.is_absolute():
        # 绝对路径：要求文件存在，落盘时存绝对形式
        if not sp.exists():
            raise FileNotFoundError("工具 %s 的 script 不存在：" % name + str(sp))
        return sp, str(sp.resolve())
    # 相对路径：相对 skill 目录解析，落盘时按原样存储（跟随 skill_dir 解析）
    script_path = d / script
    if not script_path.exists():
        raise FileNotFoundError("工具 %s 的 script 不存在：" % name + str(script_path))
    return script_path, script


def _validate_tool_name(raw, seen):
    """校验工具对象与工具名：是对象、名非空、命名合法、同 skill 内不重复。

    @return 规范化后的工具名
    """
    if not isinstance(raw, dict):
        raise ValueError("tool.json 中的工具必须是对象")
    name = (raw.get("name") or "").strip()
    if not name:
        raise ValueError("tool.json 中存在缺少 name 的工具")
    if not NAME_RE.match(name):
        raise ValueError("工具名非法（仅允许字母数字下划线）：" + name)
    if name in seen:
        raise ValueError("同一 skill 内工具名重复：" + name)
    seen.add(name)
    return name


def _resolve_interpreter(raw, script):
    """确定解释器：显式声明优先，否则按脚本扩展名推断；无脚本时返回空串。"""
    declared = raw.get("interpreter")
    if declared:
        return declared
    if script:
        return infer_interpreter(script)
    return ""


def _build_tool_entry(raw, d, provider, skill_prompt, seen):
    """校验并构建单个工具的规范化字典（工具名由 _validate_tool_name 解析）。"""
    name = _validate_tool_name(raw, seen)
    desc = (raw.get("description") or "").strip()
    if not desc:
        raise ValueError("工具 %s 缺少 description" % name)
    executor = (raw.get("executor") or "script").strip()
    script = (raw.get("script") or "").strip()
    # 脚本路径解析（含存在性校验与 external 分支）
    _, stored_script = _resolve_tool_script(raw, name, executor, provider, d)
    return {
        "name": name,
        "description": desc,
        "skill_name": d.name,
        "skill_prompt": skill_prompt,
        "skill_dir": to_project_rel(d),
        "script": stored_script,
        "interpreter": _resolve_interpreter(raw, script),
        "arg_style": raw.get("arg_style") or "flag",
        "fixed_args": raw.get("fixed_args") or [],
        "parameters": _parse_tool_params(raw, name),
        # executor=external 的工具不在本地执行，转发给 provider
        "executor": executor,
        "provider": (raw.get("provider") or provider),
        # silent：一次性副作用工具（如推送消息），其调用结果不回传网页 AI，
        # 也不在扩展侧生成卡片；仅完成动作本身。
        "silent": bool(raw.get("silent")),
        "enabled": False,
    }


def parse_skill(skill_dir):
    """解析一个 skill 目录的 tool.json，返回规范化后的工具字典列表（已校验）。"""
    d = resolve_to_abs(skill_dir)
    spec, provider, skill_prompt = _read_tool_spec(d)
    raw_list = _normalize_raw_list(spec)
    seen = set()
    tools = []
    for raw in raw_list:
        # 单工具构建：命名、描述、脚本、参数、executor 等字段的校验都收敛在此
        tools.append(_build_tool_entry(raw, d, provider, skill_prompt, seen))
    return tools
