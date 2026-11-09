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
import re

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


# 站点档案 id 的合法字符：与前端 @profile:FIELD 哨兵、PROFILES 键名口径一致。
_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")


def sanitize_profiles(raw):
    """规整站点档案（每站一份完整清单，真源为 definition.yaml 的 app.profiles）。

    规则：
    - 档案 id 仅允许字母 / 数字 / 下划线，其余整条丢弃；非字典条目整条丢弃；
    - label：转字符串，缺省取档案 id；
    - hosts：非空字符串规整为单元素列表；列表逐项转字符串并去空项；
    - split：仅接受布尔，其它类型丢弃；
    - 其余字段：仅接受字符串 / 布尔 / 字符串列表——空串与空列表语义为
      「未配置」（前端按缺失处理：可点击元素报错、状态信号跳过检查），
      数字与嵌套对象一律丢弃，防脏数据进配置文件。

    @param raw 前端提交或配置文件读出的原始档案
    @returns 规整后的 {档案 id: 字段表}
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for pid, entry in raw.items():
        if not isinstance(pid, str) or not _PROFILE_ID_RE.match(pid):
            continue
        if not isinstance(entry, dict):
            continue
        item = {}
        for key, val in entry.items():
            if not isinstance(key, str) or not key:
                continue
            if key == "hosts":
                if isinstance(val, str):
                    item["hosts"] = [val] if val.strip() else []
                elif isinstance(val, list):
                    item["hosts"] = [str(x).strip() for x in val if str(x or "").strip()]
                continue
            if key == "label":
                item["label"] = str(val)
                continue
            if key == "split":
                if isinstance(val, bool):
                    item[key] = val
                continue
            if isinstance(val, (str, bool)):
                item[key] = val
            elif isinstance(val, list) and all(isinstance(x, str) for x in val):
                item[key] = val
        item.setdefault("label", pid)
        item.setdefault("hosts", [])
        out[pid] = item
    return out


def init_config():
    """把两份配置（或默认）合并成完整 CONFIG，并保证所有工具都有 enabled 开关。"""
    raw = load_yaml_config()
    cfg = {
        "flask": raw.get("flask", {}) or {},
        "limits": raw.get("limits", {}) or {},
        "default_profile": raw.get("default_profile", "glm"),
        # site_profiles 一律由档案 hosts 派生，忽略文件里的同名字段：
        # 该字段是冗余历史遗留，两处分别维护必然漂移（详见 derive_site_profiles）。
        "site_profiles": derive_site_profiles(sanitize_profiles(raw.get("profiles", {}))),
        "profiles": sanitize_profiles(raw.get("profiles", {})),
        "tools": raw.get("tools", {}) or {},
        # 通道绑定：{通道名: 站点 id}，让 QQ 与企微各跟一个站点
        "channel_bindings": raw.get("channel_bindings", {}) or {},
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


def derive_site_profiles(profiles):
    """由站点档案的 hosts 字段派生「域名 → 档案 id」映射。

    site_profiles 是历史遗留的冗余字段：真正被消费的是每个档案自己的 hosts
    （前端 guessProfile 遍历 PROFILES[].hosts 匹配当前域名），此映射并不参与解析。
    既然是冗余，就必须只有一个真源，否则必然漂移——实际发生过两次：
    后端 POST /config 只带 profiles 时，内存里的 site_profiles 仍是旧值，
    写盘时把文件里刚补的新站点映射又覆盖掉，配置文件与档案集长期不一致。

    因此写盘前一律从 profiles 重新派生：新增站点只要在档案里写了 hosts，
    映射自动出现，不再需要两处手工维护。

    @param {dict} profiles 站点档案集
    @returns {dict} 域名到档案 id 的映射
    """
    out = {}
    if not isinstance(profiles, dict):
        return out
    for pid, entry in profiles.items():
        if not isinstance(entry, dict):
            continue
        for h in _normalized_hosts(entry.get("hosts")):
            # 同一域名被两个档案同时声明时保留先出现的，属配置冲突，由人工裁决
            if h not in out:
                out[h] = pid
    return out


def _normalized_hosts(raw):
    """把档案的 hosts 字段规整为去空白、统一小写的域名列表。

    容忍字符串写法（单域名）与非法类型：非字符串项被丢弃，空串被剔除。
    抽成独立函数是为了把类型归一化的分支从 derive_site_profiles 里挪出去，
    让后者只表达「遍历档案、填映射」这一件事。

    @param raw hosts 原始值，可为列表、字符串或其它
    @returns {list} 规整后的域名列表
    """
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        host = str(item or "").strip().lower()
        if host:
            out.append(host)
    return out


def _definition_snapshot(cfg):
    """定义分区快照：入版本库、跨机器共享的键。

    site_profiles 不直接取内存值，而是由 profiles 的 hosts 派生，
    保证「域名映射」与「档案本体」永不脱节（详见 derive_site_profiles）。
    """
    flask = cfg.get("flask", {})
    profiles = cfg.get("profiles", {})
    return {
        "flask": {"host": flask.get("host", "127.0.0.1")},
        "limits": cfg.get("limits", {}),
        "default_profile": cfg.get("default_profile", "glm"),
        "site_profiles": derive_site_profiles(profiles),
        "profiles": profiles,
    }


def _runtime_snapshot(cfg):
    """运行时分区快照：不入库、随本机状态变的键。"""
    runtime_tools = {}
    for name, ent in cfg.get("tools", {}).items():
        e = {"enabled": bool(ent.get("enabled", True))}
        if name == "run_command":
            e["languages"] = list(ent.get("languages", []))
        runtime_tools[name] = e
    return {
        "flask": {"port": cfg.get("flask", {}).get("port", 5000)},
        "tools": runtime_tools,
        # 工具配置：各工具的可调参数值，随本机状态变，写运行时文件。
        "tool_config": cfg.get("tool_config", {}),
        # 通道绑定：哪条通道固定跟哪个站点（QQ 跟 DeepSeek、企微跟 GLM）。
        # 属本机偏好、不入库；必须在此保留，否则任何一次保存配置都会把它抹掉。
        "channel_bindings": cfg.get("channel_bindings", {}),
    }


def save_config_to_yaml():
    """回写主配置：定义写 definition.yaml 的 app 分区，运行时写 runtime.yaml 的 app 分区。

    定义：host、limits、默认档案、站点映射、站点档案本体。
    运行时：port、每个工具的上下线开关、run_command 的语言清单。
    """
    ok1 = config_file.update_definition_section("app", _definition_snapshot(runtime.CONFIG))
    ok2 = config_file.update_runtime_section("app", _runtime_snapshot(runtime.CONFIG))
    return bool(ok1 and ok2)
