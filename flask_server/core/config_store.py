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


def _load_one(path):
    """读取单个 YAML 文件；优先 PyYAML，失败或未安装时回退内置解析器。
    文件不存在返回空字典。
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml:
        try:
            return yaml.safe_load(text) or {}
        except Exception as e:
            print("[config] PyYAML 解析失败，回退到内置解析：", e)
    return mini_yaml_load(text)


def load_yaml_config():
    """读取 config.yaml 与 config_runtime.yaml 并合并。

    config.yaml          —— 定义（入库）：站点映射、工具清单、主机地址等
    config_runtime.yaml  —— 运行时（不入库）：端口、工具上下线、语言清单
    合并顺序：运行时字段覆盖定义中的同名字段。
    """
    base = _load_one(runtime.CONFIG_PATH)
    rt = _load_one(runtime.CONFIG_RUNTIME_PATH)
    if not rt:
        return base
    # flask 区块逐字段合并：运行时只覆盖 port，host 仍以定义文件为准
    if isinstance(rt.get("flask"), dict):
        base.setdefault("flask", {})
        base["flask"].update(rt["flask"])
    # tools 区块逐工具合并：运行时只覆盖 enabled 与 languages
    if isinstance(rt.get("tools"), dict):
        base.setdefault("tools", {})
        for name, ent in rt["tools"].items():
            if isinstance(ent, dict):
                base["tools"].setdefault(name, {}).update(ent)
    return base


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
    # 为每个内置工具补齐开关
    for name in runtime.TOOLS:
        cfg["tools"][name] = _tool_entry_for(name, cfg["tools"].get(name) or {})
    return cfg


# ---------- 回写 ----------
def _scalar_text(v):
    """把标量转成 YAML 文本（布尔小写、其余原样）。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    return str(v)


def _dump_simple(data, indent=0):
    """极简 YAML 序列化（无 PyYAML 时的兜底）：支持字典 / 列表 / 标量。"""
    pad = "  " * indent
    lines = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                lines.append("%s%s:" % (pad, k))
                lines.append(_dump_simple(v, indent + 1))
            else:
                lines.append("%s%s: %s" % (pad, k, _scalar_text(v)))
    elif isinstance(data, list):
        for v in data:
            if isinstance(v, (dict, list)):
                lines.append("%s-" % pad)
                lines.append(_dump_simple(v, indent + 1))
            else:
                lines.append("%s- %s" % (pad, _scalar_text(v)))
    else:
        lines.append("%s%s" % (pad, _scalar_text(data)))
    return "\n".join(lines)


def save_config_to_yaml():
    """回写配置：定义写 config.yaml（入库），运行时写 config_runtime.yaml（不入库）。

    定义：host、limits、默认档案、站点映射。
    运行时：port、每个工具的上下线开关、run_command 的语言清单。
    这样改端口或开关不会污染 config.yaml 的版本历史。
    """
    CONFIG = runtime.CONFIG
    flask = CONFIG.get("flask", {})
    tools = CONFIG.get("tools", {})
    # 定义快照：入版本库，跨机器共享
    definition = {
        "flask": {"host": flask.get("host", "127.0.0.1")},
        "limits": CONFIG.get("limits", {}),
        "default_profile": CONFIG.get("default_profile", "glm"),
        "site_profiles": CONFIG.get("site_profiles", {}),
    }
    # 运行时快照：不入库，随本机状态变
    runtime_tools = {}
    for name, ent in tools.items():
        e = {"enabled": bool(ent.get("enabled", True))}
        if name == "run_command":
            e["languages"] = list(ent.get("languages", []))
        runtime_tools[name] = e
    runtime_data = {
        "flask": {"port": flask.get("port", 5000)},
        "tools": runtime_tools,
    }
    try:
        if yaml:
            with open(runtime.CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(definition, f, allow_unicode=True, sort_keys=False)
            with open(runtime.CONFIG_RUNTIME_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(runtime_data, f, allow_unicode=True, sort_keys=False)
            return True
        runtime.CONFIG_PATH.write_text(_dump_simple(definition) + "\n", encoding="utf-8")
        runtime.CONFIG_RUNTIME_PATH.write_text(_dump_simple(runtime_data) + "\n", encoding="utf-8")
        return True
    except Exception as e:
        print("[config] 写回配置失败：", e)
        return False
