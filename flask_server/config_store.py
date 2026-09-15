"""
AI 工具调用镜像插件 —— 配置读写

负责 config.yaml 的读取、合并与回写：
- load_yaml_config / mini_yaml_load：读取并解析（优先 PyYAML，回退内置解析器）
- init_config：把解析结果合并成完整 CONFIG，并补齐每个工具的 enabled 开关
- save_config_to_yaml：回写文件（优先 PyYAML 整文件重写，回退按行原地修补）

YAML 标量级处理（去注释 / 标量转换 / 引号转义）已下沉到 yaml_utils，
与 custom_tools.yaml 侧共用同一套规则。
"""
import re

import runtime
import yaml_utils

try:
    import yaml
except ImportError:
    yaml = None


# ---------- 读取 ----------
def _mini_parse_indented(body, section, data):
    """处理缩进行：按当前所在区块写入对应子字典。"""
    if ":" not in body:
        return
    k, _, v = body.strip().partition(":")
    key = k.strip()
    if section == "flask":
        data["flask"][key] = yaml_utils.coerce_scalar(v)
    elif section == "site_profiles":
        data["site_profiles"][key] = yaml_utils.coerce_scalar(v)
    elif section == "tools":
        # tools 区块内的条目形如 <name>: {enabled: true}
        enabled = True
        m = re.search(r"enabled\s*:\s*(true|false)", v, re.I)
        if m:
            enabled = m.group(1).lower() == "true"
        data["tools"][key] = {"enabled": enabled}


def _mini_parse_toplevel(body, data):
    """处理顶格行：判断是「进入新区块」还是「顶层键值对」。

    @return 新的当前区块名；不是区块起始行时返回 None
    """
    if ":" not in body:
        return None
    k, _, v = body.strip().partition(":")
    k, v = k.strip(), v.strip()
    if v == "":
        return k          # 进入块映射
    data[k] = yaml_utils.coerce_scalar(v)
    return None


def mini_yaml_load(text):
    """极简 YAML 解析：仅支持本插件 config.yaml 的结构（块映射 + 行内流映射）。

    无 PyYAML 时的兜底；若装了 PyYAML 则优先用它（见 load_yaml_config）。
    """
    data = {"flask": {}, "tools": {}, "site_profiles": {}, "default_profile": "glm"}
    section = None
    for ln in text.splitlines():
        body = ln.split("#", 1)[0].rstrip()  # 去注释
        if not body.strip():
            continue
        if (len(body) - len(body.lstrip())) != 0:
            _mini_parse_indented(body, section, data)
            continue
        new_section = _mini_parse_toplevel(body, data)
        section = new_section
    return data


def load_yaml_config():
    """读取 config.yaml；优先 PyYAML，失败或未安装时回退内置解析器。"""
    if not runtime.CONFIG_PATH.exists():
        return {}
    text = runtime.CONFIG_PATH.read_text(encoding="utf-8")
    if yaml:
        try:
            return yaml.safe_load(text) or {}
        except Exception as e:
            print("[config] PyYAML 解析失败，回退到内置解析：", e)
    return mini_yaml_load(text)


def _tool_entry_for(name, entry):
    """构造单个内置工具的配置项：补齐 enabled；run_command 额外补齐支持语言。"""
    new_entry = {"enabled": bool(entry.get("enabled", True))}
    if name == "run_command":
        default_langs = getattr(runtime.impl, "RUN_COMMAND_SUPPORTED_LANGUAGES",
                                ["cmd", "powershell", "shell", "git", "python"])
        langs = entry.get("languages") or default_langs
        new_entry["languages"] = [str(x).strip().lower() for x in langs if str(x).strip()]
    return new_entry


def init_config():
    """把 YAML（或默认）合并成完整 CONFIG，并保证所有用户工具都有 enabled 开关。"""
    raw = load_yaml_config()
    cfg = {
        "flask": raw.get("flask", {}) or {},
        "limits": raw.get("limits", {}) or {},
        "default_profile": raw.get("default_profile", "glm"),
        "site_profiles": raw.get("site_profiles", {}) or {},
        "tools": raw.get("tools", {}) or {},
    }
    # 关键字段兜底默认值
    cfg["flask"].setdefault("host", "127.0.0.1")
    cfg["flask"].setdefault("port", 5000)
    # 工具结果 JSON 体积上限，未配置时取默认 10 万字符
    cfg["limits"].setdefault("max_json_chars", 100000)
    # 为每个内置工具补齐开关；自愈工具始终在线，不受开关影响
    for name in runtime.TOOLS:
        if name in runtime.FIX_TOOLS:
            continue
        cfg["tools"][name] = _tool_entry_for(name, cfg["tools"].get(name) or {})
    return cfg


# ---------- 回写 ----------
def _detect_section(body, current):
    """判断顶格行是否开启新区块；是则返回区块名，否则返回当前区块。"""
    if not body.strip() or (len(body) - len(body.lstrip())) != 0 or ":" not in body:
        return current
    head, tail = body.split(":", 1)
    return head.strip() if tail.strip() == "" else None


def _patch_flask_line(ln, CONFIG):
    """flask 区块：改写 port 行；不匹配返回 None。"""
    m = re.match(r"^(\s*port\s*:\s*)(\d+)", ln)
    if not m:
        return None
    return m.group(1) + str(int(CONFIG["flask"]["port"]))


def _patch_tools_line(ln, CONFIG):
    """tools 区块：改写 <name>: {enabled: ...} 行或 languages 行；不匹配返回 None。"""
    tm = re.match(r"^\s*([A-Za-z0-9_-]+)\s*:\s*\{\s*enabled\s*:\s*(true|false)", ln)
    if tm and tm.group(1) in CONFIG["tools"]:
        name = tm.group(1)
        en = bool(CONFIG["tools"][name].get("enabled", True))
        prefix = re.match(r"^(\s*[A-Za-z0-9_-]+\s*:\s*\{\s*enabled\s*:\s*)", ln).group(1)
        return prefix + ("true" if en else "false") + " }"
    # run_command 的 languages 列表：整行替换为当前生效值
    if ln.lstrip().startswith("languages:") and "run_command" in CONFIG["tools"]:
        langs = CONFIG["tools"]["run_command"].get("languages", [])
        return "    languages: [" + ", ".join(langs) + "]"
    return None


def _patch_yaml_by_line(lines, CONFIG):
    """无 PyYAML 时的兜底：按行原地修补，保留注释与缩进。"""
    out, section = [], None
    for ln in lines:
        body = ln.split("#", 1)[0].rstrip()
        section = _detect_section(body, section)
        patched = None
        if section == "flask":
            patched = _patch_flask_line(ln, CONFIG)
        elif section == "tools":
            patched = _patch_tools_line(ln, CONFIG)
        out.append(patched if patched is not None else ln)
    return out


def save_config_to_yaml():
    """回写 config.yaml。优先用 PyYAML 整文件重写；无 PyYAML 时按行原地修补，
    保留注释与缩进（只改 port、tools.<name>.enabled 与 run_command 的语言列表）。"""
    if not runtime.CONFIG_PATH.exists():
        return False
    CONFIG = runtime.CONFIG
    try:
        if yaml:
            with open(runtime.CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(CONFIG, f, allow_unicode=True, sort_keys=False)
            return True
        # 兜底：行内修补，保留注释
        lines = runtime.CONFIG_PATH.read_text(encoding="utf-8").splitlines()
        out = _patch_yaml_by_line(lines, CONFIG)
        runtime.CONFIG_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except Exception as e:
        print("[config] 写回 config.yaml 失败：", e)
        return False
