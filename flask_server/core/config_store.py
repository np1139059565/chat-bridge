"""
AI 工具调用镜像插件 —— 主配置读写

配置集中为两份文件（见 core/config_file.py）：
- definition.yaml  全部定义，入库
- runtime.yaml     全部运行时与密钥，不入库

本模块只管其中的 app 分区：
- load_yaml_config：读 definition 与 runtime 的 app 分区并合并
- init_config：把解析结果合并成完整 CONFIG，并补齐每个工具的 enabled 开关
- save_config_to_yaml：定义写 definition、运行时写 runtime
"""
import runtime
import config_file
import yaml_utils


def load_yaml_config():
    """读取 definition.yaml 与 runtime.yaml 的 app 分区并合并。

    definition 的 app —— 定义（入库）：站点映射、主机地址、体积上限
    runtime 的 app    —— 运行时（不入库）：端口、工具上下线、语言清单
    合并顺序：运行时字段覆盖定义中的同名字段。
    """
    base = config_file.get_definition_section("app")
    rt = config_file.get_runtime_section("app")
    # 合并核心委托给公共函数，与 yaml_utils.load_config_dict 共用同一实现
    return yaml_utils.merge_app_sections(base, rt)


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
    """把两份配置（或默认）合并成完整 CONFIG，并保证所有工具都有 enabled 开关。"""
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


def save_config_to_yaml():
    """回写主配置：定义写 definition.yaml 的 app 分区，运行时写 runtime.yaml 的 app 分区。

    定义：host、limits、默认档案、站点映射。
    运行时：port、每个工具的上下线开关、run_command 的语言清单。
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
    ok1 = config_file.update_definition_section("app", definition)
    ok2 = config_file.update_runtime_section("app", runtime_data)
    return bool(ok1 and ok2)
