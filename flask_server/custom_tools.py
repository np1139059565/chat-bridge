"""
AI 工具调用镜像插件 —— 自定义工具（由标准 skill 扩展）

自定义工具来自「标准 skill」：一个 skill 目录若在根目录下放了 tool.json，
就声明了它要暴露给网页 AI 的一个或多个工具。本模块负责
    1. 解析 skill 的 tool.json（按下方《skill 工具声明规范》）
    2. 把安装结果落盘到 custom_tools.yaml（本机持久化，不存浏览器）
    3. 把工具调用翻译成子进程命令并执行

=====================================================================
《skill 工具声明规范》（tool.json，UTF-8）
=====================================================================
{
  "tools": [
    {
      "name": "wx_metar",                 // 工具名，全局唯一，snake_case，仅 [A-Za-z0-9_]
      "description": "获取指定机场的 METAR 报文",   // 给 AI 看的功能说明（提示词质量关键）
      "script": "scripts/wx.py",          // 相对 skill 根目录的脚本路径（也可写绝对路径）
      "interpreter": "python",            // 可选：python / node / bash / powershell；省略按扩展名推断
      "arg_style": "flag",                // 可选：flag（默认，--名 值）/ positional（按声明顺序）
      "fixed_args": ["--json"],           // 可选：固定前置参数，每次调用都带上
      "parameters": [                    // 可选：与内置工具同构的参数表
        { "name": "stations", "type": "array",    "required": true,  "description": "机场 ICAO 代码，如 KSMO" },
        { "name": "taf",     "type": "boolean",  "required": false, "description": "同时返回 TAF" }
      ]
    }
  ]
}
- 也允许把单个工具对象直接放在顶层（省略 tools 包裹）。
- parameters 的字段与内置工具一致：name / type / required / description。

参数如何变成命令行：
- arg_style=flag（默认）：string/number → --名 值；boolean 为真 → --名；array → 每个元素一个 --名 值
- arg_style=positional：按 parameters 声明顺序，把值依次作为位置参数（boolean 为真才传 --名）
脚本输出：退出码非 0 视为失败；标准输出若是合法 JSON 则原样返回，否则包成 {"stdout": ...}。

安全说明：自定义工具 = 让网页 AI 执行本机脚本。按设计「完全信任用户安装的 skill」，
本模块不做超时 / 目录 / 沙箱限制（用户已确认）。执行失败仅按内置分类回传，不影响服务。
=====================================================================
"""
import os
import re
import json
import subprocess
from pathlib import Path

# 当前文件所在目录（flask_server/）
APP_DIR = Path(__file__).resolve().parent

CT_PATH = APP_DIR / "custom_tools.yaml"

# 项目根目录（chat-bridge/）：skill_dir 与 script 在项目内时以相对该目录的路径存储，
# 工程迁移/重命名后仍可正常解析；项目外的路径保留绝对形式。
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _to_project_rel(abs_path: Path) -> str:
    """将绝对路径转为相对项目根的字符串；不在项目根内则保留绝对路径。"""
    p = abs_path.resolve()
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def _resolve_to_abs(stored: str) -> Path:
    """将存储的路径解析为绝对路径。绝对路径直接使用；相对路径视为相对于项目根。"""
    p = Path(stored)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


# 可扫描的默认 skill 根目录（用户同意「完全信任」，这里只是提供方便的默认入口）
def _default_roots():
    roots = [
        APP_DIR.parent / "skills",                    # 项目自带 skill 模板（基础路径）
        Path.home() / ".codebuddy" / "skills",       # 用户级 skill
        Path.home() / ".codebuddy" / "skills-marketplace" / "skills",
    ]
    out = []
    for p in roots:
        try:
            if p.is_dir():
                out.append(p)
        except Exception:
            pass
    return out

DEFAULT_SKILL_ROOTS = _default_roots()

NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


# ---------- custom_tools.yaml：无 PyYAML 时的专用受限解析（本模块自有格式） ----------
def _strip_comment(s):
    """去掉行首或空白后的 # 注释，但引号内的 # 不当注释（描述里可能含 #）。"""
    out = []
    in_str = False
    q = ""
    prev = ""
    for ch in s:
        if in_str:
            out.append(ch)
            if ch == q:
                in_str = False
        elif ch in ('"', "'"):
            in_str = True
            q = ch
            out.append(ch)
        elif ch == "#" and (prev == "" or prev.isspace()):
            break
        else:
            out.append(ch)
        prev = ch
    return "".join(out).rstrip()


def _parse_scalar(v):
    v = v.strip()
    if not v:
        return None
    if v[0] in ('"', "'") and v[-1] == v[0]:
        inner = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        return inner
    low = v.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def _q(s):
    s = str(s).replace("\\", "\\\\").replace('"', '\\"')
    return '"' + s + '"'


def _parse_yaml(text):
    """解析 custom_tools.yaml：tools 下是工具列表，每个工具含可选 fixed_args / parameters 子列表。"""
    tools = []
    cur_tool = None
    cur_param = None
    list_section = None  # 'fixed_args' | 'parameters' | None
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        is_item = body.startswith("- ")
        if indent == 0:
            k, _, val = body.partition(":")
            if k.strip() == "tools" and val.strip() == "":
                cur_tool, cur_param, list_section = None, None, None
            continue
        if is_item:
            rest = body[2:].strip()
            if indent <= 4:  # 新的工具条目：  - name: ...
                if cur_tool is not None:
                    tools.append(cur_tool)
                cur_tool = {}
                cur_param = None
                list_section = None
                if rest:
                    k, _, val = rest.partition(":")
                    cur_tool[k.strip()] = _parse_scalar(val)
                continue
            # 子列表条目（indent >= 6）
            if list_section == "parameters":
                cur_param = {}
                cur_tool.setdefault("parameters", []).append(cur_param)
                if rest:
                    k, _, val = rest.partition(":")
                    cur_param[k.strip()] = _parse_scalar(val)
            elif list_section == "fixed_args":
                cur_tool.setdefault("fixed_args", []).append(_parse_scalar(rest))
            continue
        # key: value
        k, _, val = body.partition(":")
        key = k.strip()
        value = val.strip()
        if cur_param is not None:
            cur_param[key] = _parse_scalar(value)
            continue
        if cur_tool is None:
            continue
        if value == "":
            list_section = key  # 进入 fixed_args 或 parameters 子列表
            continue
        if list_section == "parameters" and cur_param is not None:
            cur_param[key] = _parse_scalar(value)
        else:
            cur_tool[key] = _parse_scalar(value)
    if cur_tool is not None:
        tools.append(cur_tool)
    return tools


def _dump_yaml(tools):
    out = [
        "# AI 工具调用镜像 · 自定义工具（由标准 skill 安装）",
        "# 本文件由插件自动维护；建议通过设置页修改，手工编辑请严格保持缩进。",
        "tools:",
    ]
    for t in tools:
        out.append("  - name: " + _q(t.get("name", "")))
        for key in ("description", "skill_name", "skill_prompt", "skill_dir", "script", "interpreter", "arg_style", "executor", "provider"):
            if t.get(key) not in (None, ""):
                out.append("    %s: %s" % (key, _q(t[key])))
        # silent 为布尔标记，仅在为真时写出
        if t.get("silent"):
            out.append("    silent: true")
        out.append("    enabled: %s" % ("true" if t.get("enabled") else "false"))
        fa = t.get("fixed_args") or []
        if fa:
            out.append("    fixed_args:")
            for a in fa:
                out.append("      - %s" % _q(a))
        params = t.get("parameters") or []
        if params:
            out.append("    parameters:")
            for p in params:
                out.append("      - name: " + _q(p.get("name", "")))
                if p.get("type"):
                    out.append("        type: " + _q(p["type"]))
                out.append("        required: %s" % ("true" if p.get("required") else "false"))
                if p.get("description"):
                    out.append("        description: " + _q(p["description"]))
    return "\n".join(out) + "\n"


# ---------- 读取 / 落盘 ----------
def load_tools():
    if not CT_PATH.exists():
        return {}
    try:
        tools = _parse_yaml(CT_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print("[custom_tools] 解析 custom_tools.yaml 失败：", e)
        return {}
    out = {}
    for t in tools:
        if isinstance(t, dict) and t.get("name"):
            out[t["name"]] = t
    return out


def save_tools(tools):
    try:
        CT_PATH.write_text(_dump_yaml(list(tools.values())), encoding="utf-8")
        return True
    except Exception as e:
        print("[custom_tools] 写回 custom_tools.yaml 失败：", e)
        return False


# ---------- 命令拼装 ----------
def _infer_interpreter(script):
    ext = Path(script).suffix.lower()
    return {".py": "python", ".js": "node", ".sh": "bash",
            ".ps1": "powershell", ".rb": "ruby"}.get(ext, "")


def _to_str(v):
    return "" if v is None else str(v)


def _flag_arg(name, val):
    flag = "--" + name
    if isinstance(val, bool):
        return [flag] if val else []
    if isinstance(val, list):
        r = []
        for el in val:
            r += [flag, _to_str(el)]
        return r
    if val in (None, ""):
        return []
    return [flag, _to_str(val)]


# ---------- skill 解析 / 安装 ----------
def parse_skill(skill_dir):
    """解析一个 skill 目录的 tool.json，返回规范化后的工具字典列表（已校验）。"""
    d = _resolve_to_abs(skill_dir)
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
    if isinstance(spec, dict) and "tools" in spec:
        raw_list = spec["tools"]
    elif isinstance(spec, list):
        raw_list = spec
    else:
        raw_list = [spec]
    if not isinstance(raw_list, list):
        raw_list = [raw_list]

    seen = set()
    tools = []
    for raw in raw_list:
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
        desc = (raw.get("description") or "").strip()
        if not desc:
            raise ValueError("工具 %s 缺少 description" % name)
        executor = (raw.get("executor") or "script").strip()
        script = (raw.get("script") or "").strip()
        sp = Path(script) if script else Path()
        script_path = None
        # executor=external 的工具不在本地执行，无需脚本文件
        if executor == "external":
            if not (raw.get("provider") or provider):
                raise ValueError("工具 %s 为 external，但缺少 provider" % name)
        else:
            if not script:
                raise ValueError("工具 %s 缺少 script" % name)
            if sp.is_absolute():
                if not sp.exists():
                    raise FileNotFoundError("工具 %s 的 script 不存在：" % name + str(sp))
                script_path = sp
            else:
                script_path = d / script
                if not script_path.exists():
                    raise FileNotFoundError("工具 %s 的 script 不存在：" % name + str(script_path))
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
        stored_script = ""
        if script_path is not None:
            stored_script = str(script_path.resolve()) if sp.is_absolute() else script
        tools.append({
            "name": name,
            "description": desc,
            "skill_name": d.name,
            "skill_prompt": skill_prompt,
            "skill_dir": _to_project_rel(d),
            "script": stored_script,
            "interpreter": raw.get("interpreter") or (_infer_interpreter(script) if script else ""),
            "arg_style": raw.get("arg_style") or "flag",
            "fixed_args": raw.get("fixed_args") or [],
            "parameters": params,
            # executor=external 的工具不在本地执行，转发给 provider
            "executor": executor,
            "provider": (raw.get("provider") or provider),
            # silent：一次性副作用工具（如推送消息），其调用结果不回传网页 AI，
            # 也不在扩展侧生成卡片；仅完成动作本身。
            "silent": bool(raw.get("silent")),
            "enabled": False,
        })
    return tools


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
    tools = load_tools()
    if name in tools:
        del tools[name]
        save_tools(tools)
        return True
    return False


def update(name, patch):
    tools = load_tools()
    t = tools.get(name)
    if not t:
        return None
    for field in ("description", "interpreter", "arg_style"):
        if field in patch and patch[field] not in (None, ""):
            t[field] = patch[field]
    if "enabled" in patch:
        t["enabled"] = bool(patch["enabled"])
    if isinstance(patch.get("parameters"), list):
        t["parameters"] = [{
            "name": (p.get("name") or ""),
            "type": (p.get("type") or "string"),
            "required": bool(p.get("required")),
            "description": (p.get("description") or ""),
        } for p in patch["parameters"] if isinstance(p, dict)]
    if isinstance(patch.get("fixed_args"), list):
        t["fixed_args"] = list(patch["fixed_args"])
    save_tools(tools)
    return t


def get_tool(name):
    return load_tools().get(name)


def is_enabled(name):
    t = load_tools().get(name)
    return bool(t.get("enabled")) if t else False


def run(tool, params):
    """执行一个自定义工具脚本，返回结果 dict。失败抛异常，由 server 层分类。"""
    params = params or {}
    # 必填校验（缺参抛 ValueError → 被分类为 parameter）
    for p in tool.get("parameters") or []:
        nm = p.get("name")
        if p.get("required") and (nm not in params or params[nm] in (None, "")):
            raise ValueError("缺少必填参数 %s（工具 %s）" % (nm, tool.get("name")))
    skill_dir = _resolve_to_abs(tool["skill_dir"])
    script_path = Path(tool["script"]) if Path(tool["script"]).is_absolute() else (skill_dir / tool["script"])
    cmd = []
    it = tool.get("interpreter") or _infer_interpreter(tool["script"])
    if it:
        cmd.append(it)
    cmd.append(str(script_path))
    for a in tool.get("fixed_args") or []:
        cmd.append(_to_str(a))
    style = tool.get("arg_style") or "flag"
    for p in tool.get("parameters") or []:
        nm = p.get("name")
        if nm not in params:
            continue
        val = params[nm]
        if style == "flag":
            cmd += _flag_arg(nm, val)
        elif isinstance(val, bool):
            if val:
                cmd.append("--" + nm)
        elif isinstance(val, list):
            for el in val:
                cmd.append(_to_str(el))
        elif val not in (None, ""):
            cmd.append(_to_str(val))
    try:
        # Windows 上子进程默认按 GBK 写 stdout，强制 UTF-8 以免中文乱码（mojibake）。
        child_env = dict(os.environ)
        child_env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            cmd, cwd=str(skill_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", shell=False, env=child_env,
        )
    except FileNotFoundError as e:
        # 解释器或脚本缺失 → 环境/路径类
        raise FileNotFoundError("无法启动脚本（解释器或脚本缺失）：" + str(e))
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


# ---------- 给前端 / server 用的只读视图 ----------
def external_providers():
    """汇总【已上线】的 executor=external 工具，按 provider 分组，用于注册到提供方注册表。

    未上线的外部工具不注册，因此即使提供方在线也不会并入 /tools。
    """
    groups = {}
    for t in load_tools().values():
        if (t.get("executor") or "script") != "external":
            continue
        if not t.get("enabled"):
            continue
        provider = (t.get("provider") or "").strip()
        if not provider:
            continue
        entry = {
            "name": t.get("name"),
            "description": t.get("description", ""),
            "parameters": t.get("parameters") or [],
        }
        if t.get("silent"):
            entry["silent"] = True
        groups.setdefault(provider, []).append(entry)
    return groups


def prompt_sections():
    """收集各技能的统一说明（tool.json 的 prompt 字段）。

    生效条件：该技能下有至少一个工具处于上线状态。
    返回 [ { skill, text } ]，技能名取 skill_name。
    """
    sections = {}
    for t in load_tools().values():
        if not t.get("enabled"):
            continue
        text = (t.get("skill_prompt") or "").strip()
        if not text:
            continue
        skill = t.get("skill_name") or ""
        sections[skill] = text
    return [{"skill": k, "text": v} for k, v in sections.items()]


def public_meta(tool):
    meta = {
        "name": tool.get("name"),
        "description": tool.get("description", ""),
        "parameters": tool.get("parameters") or [],
    }
    # silent：一次性副作用工具，其结果不回传网页 AI
    if tool.get("silent"):
        meta["silent"] = True
    return meta


def all_meta():
    """已上线的自定义工具（用于 /tools 合并进 System Prompt）。

    上线即在此返回，与执行端是否在线无关：executor=external 的工具若提供方离线，
    调用时返回离线错误，但不从工具列表撤出。
    """
    return [public_meta(t) for t in load_tools().values() if t.get("enabled")]


def all_meta_full():
    """全部自定义工具（含未上线），用于设置页管理 UI。"""
    return [{
        "name": t.get("name"),
        "description": t.get("description", ""),
        "skill_name": t.get("skill_name", ""),
        "skill_dir": t.get("skill_dir", ""),
        "script": t.get("script", ""),
        "interpreter": t.get("interpreter", ""),
        "arg_style": t.get("arg_style", ""),
        "enabled": bool(t.get("enabled")),
        "parameters": t.get("parameters") or [],
        "fixed_args": t.get("fixed_args") or [],
    } for t in load_tools().values()]


def scan_dir(d):
    """扫描某目录下的可安装 skill（含 tool.json 的子目录）。"""
    root_in = Path(d)
    if not root_in.is_absolute():
        root_in = PROJECT_ROOT / root_in
    root = root_in
    if not root.is_dir():
        raise ValueError("目录不存在：" + str(root))
    results = []
    for sub in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda x: x.name):
        tf = sub / "tool.json"
        if not tf.exists():
            continue
        try:
            parsed = parse_skill(sub)
            installed = load_tools()
            results.append({
                "skill_dir": _to_project_rel(sub),
                "skill_name": sub.name,
                "tools": [{
                    "name": t["name"],
                    "description": t["description"],
                    "installed": t["name"] in installed,
                } for t in parsed],
            })
        except Exception as e:
            results.append({
                "skill_dir": _to_project_rel(sub),
                "skill_name": sub.name,
                "error": str(e),
                "tools": [],
            })
    return results
