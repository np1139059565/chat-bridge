"""
路由：配置读写

- GET  /config  返回当前配置（flask / limits / tools / 站点规则等）
- POST /config  部分更新配置并回写配置文件

部分更新支持：
- flask.host / flask.port        需重启服务才能生效
- tools.<name>.enabled           即时生效
- tools.run_command.languages    即时生效
- limits.max_json_chars          即时生效
- GET  /profiles 轻量返回站点档案（真源为客户端注册信息，内容脚本注入时经后台中转拉取）
- profiles（站点档案）           写入 /api/clients 的 custom_config 寄存通道，未提交的档案保留
"""
from flask import Blueprint, jsonify, request

import runtime
import tool_config
from config_store import save_config_to_yaml
from service_control import rolling_restart
# 站点档案真源：C-3a 已建的客户端注册信息通道，只读复用其原语（与 command_catalog 同款）。
import client_registry as registry

bp = Blueprint("config_route", __name__)


def _registry_profiles():
    """从客户端注册表聚合站点档案集：{site_key: custom_config}。

    只读复用 client_registry 的整表读取原语；不校验、不清洗、不解释
    custom_config 的字段含义，也不并入 config_store 的档案解析链。
    注册表为空时返回空字典，不静默兜底到 definition.yaml 的出厂档案。
    """
    store = registry._read_store() or {}
    out = {}
    for site_key, entry in store.items():
        if isinstance(entry, dict):
            # custom_config 原样作为该站点档案本体（可为任意 JSON 值）。
            out[site_key] = entry.get("custom_config")
    return out


def _apply_flask_section(data, changed):
    """应用 flask 区块（host / port）的更新；仅记录真正发生变化的项。"""
    if not isinstance(data.get("flask"), dict):
        return
    for k in ("host", "port"):
        if k in data["flask"] and str(data["flask"][k]) != str(runtime.CONFIG["flask"].get(k)):
            runtime.CONFIG["flask"][k] = data["flask"][k]
            changed.append("flask." + k)


def _apply_run_command_languages(tv, changed):
    """应用 run_command 的支持语言列表（小写、去空）。"""
    if not isinstance(tv.get("languages"), list):
        return
    langs = [str(x).strip().lower() for x in tv["languages"] if str(x).strip()]
    runtime.CONFIG["tools"]["run_command"]["languages"] = langs
    changed.append("tools.run_command.languages=" + ",".join(langs))


def _apply_tools_section(data, changed):
    """应用 tools 区块：工具上下线开关，以及 run_command 的支持语言列表。"""
    if not isinstance(data.get("tools"), dict):
        return
    for name, tv in data["tools"].items():
        if name not in runtime.TOOLS or not isinstance(tv, dict):
            continue
        enabled = bool(tv.get("enabled", True))
        runtime.CONFIG["tools"].setdefault(name, {})["enabled"] = enabled
        changed.append("tools." + name + "=" + str(enabled))
        # run_command 额外支持语言列表
        if name == "run_command":
            _apply_run_command_languages(tv, changed)


def _apply_limits_section(data, changed):
    """应用 limits 区块：工具结果 JSON 体积上限，必须是正整数。

    校验失败时返回错误响应（调用方直接返回给客户端）；成功返回 None。
    """
    if not isinstance(data.get("limits"), dict):
        return None
    v = data["limits"].get("max_json_chars")
    if v is None:
        return None
    try:
        v = int(v)
    except (TypeError, ValueError):
        return jsonify(success=False, error="limits.max_json_chars 必须是正整数"), 400
    if v <= 0:
        return jsonify(success=False, error="limits.max_json_chars 必须大于 0"), 400
    if v != runtime.CONFIG["limits"].get("max_json_chars"):
        runtime.CONFIG["limits"]["max_json_chars"] = v
        changed.append("limits.max_json_chars=" + str(v))
    return None


def _apply_tool_config_section(data, changed):
    """应用 tool_config 区块：各工具的配置值。

    只接受声明里存在的工具与键；值按声明类型转换并校验范围。
    值统一存 runtime.CONFIG["tool_config"][工具][键]。
    @returns 校验失败时返回错误响应，成功返回 None
    """
    block = data.get("tool_config")
    if not isinstance(block, dict):
        return None
    for tool, items in block.items():
        # 未声明的工具：忽略，避免写入无意义的键
        specs = {s["key"]: s for s in tool_config.CONFIG_SCHEMA.get(tool, [])}
        if not specs or not isinstance(items, dict):
            continue
        store = runtime.CONFIG.setdefault("tool_config", {}).setdefault(tool, {})
        for key, raw in items.items():
            spec = specs.get(key)
            if not spec:
                continue
            try:
                val = tool_config.coerce(spec, raw)
            except ValueError as e:
                return jsonify(success=False, error=str(e)), 400
            if val != store.get(key):
                store[key] = val
                changed.append("tool_config.%s.%s" % (tool, key))
    return None


def _save_profile_block(block):
    """把 profiles 区块逐档案写入寄存通道；返回是否发生登记。"""
    if not isinstance(block, dict):
        return False
    done = False
    for pid, entry in block.items():
        if not isinstance(pid, str) or not pid:
            continue
        # 覆盖登记时保留原有指令声明，避免把客户端声明一并抹掉。
        old = registry.lookup(pid) or {}
        registry.register(pid, entry, old.get("commands"))
        done = True
    return done


def _remove_profile_keys(removed):
    """按 profiles_remove 显式注销客户端；返回是否实际删除。"""
    if not isinstance(removed, list):
        return False
    done = False
    for pid in removed:
        if isinstance(pid, str) and registry.unregister(pid):
            done = True
    return done


def _apply_profiles_section(data, changed):
    """应用 profiles 区块：真源为客户端注册信息（/api/clients 的 custom_config）。

    每个档案 id 即一个 site_key，custom_config 原样存放该档案本体；服务端
    不校验、不清洗、不解释字段，不回写 definition.yaml，也不并入 config_store。
    """
    saved = _save_profile_block(data.get("profiles"))
    removed = _remove_profile_keys(data.get("profiles_remove"))
    if saved or removed:
        changed.append("profiles")


def _config_snapshot():
    """构造 GET /config 的完整配置快照。"""
    host = runtime.CONFIG["flask"]["host"]
    port = runtime.CONFIG["flask"]["port"]
    return {
        "flask": {"host": host, "port": port, "url": "http://%s:%s" % (host, port)},
        "limits": runtime.CONFIG.get("limits", {}),
        "default_profile": runtime.CONFIG.get("default_profile", "glm"),
        "site_profiles": runtime.CONFIG.get("site_profiles", {}),
        "profiles": _registry_profiles(),
        "tools": runtime.CONFIG.get("tools", {}),
        # 工具配置：声明 + 当前值，设置页按类型通用渲染
        "tool_config": tool_config.all_specs(),
        # 系统级配置：目录与队列上限，独立于工具
        "system_config": tool_config.system_specs(),
        "available_tools": sorted(list(runtime.TOOLS.keys())),
    }


def _handle_config_post():
    """POST /config：依次应用各区块，保存配置并返回响应。"""
    data = request.get_json(force=True, silent=True) or {}
    changed = []
    _apply_flask_section(data, changed)
    _apply_tools_section(data, changed)
    err = _apply_tool_config_section(data, changed)
    if err is not None:
        return err
    err = _apply_limits_section(data, changed)
    if err is not None:
        return err
    _apply_profiles_section(data, changed)
    saved = save_config_to_yaml()
    # 配置已变更：立即让记忆总开关缓存失效，使开关切换马上生效。
    # 不做这一步的话，开关最长要等缓存过期才起作用，用户会以为没生效。
    try:
        import memory_switch
        memory_switch.invalidate()
    except Exception:
        pass
    # 端口 / host 改动需要重启进程才能重新绑定，单靠写配置无法让正在运行的服务生效
    require_restart = any(c.startswith("flask.") for c in changed)
    return jsonify(success=saved, saved=saved, changed=changed, requireRestart=require_restart)


@bp.route("/config", methods=["GET", "POST", "OPTIONS"])
def config():
    """读取（GET）或部分更新（POST）配置。

    POST 支持四个区块：flask（host/port）、tools（开关与语言）、limits（体积上限）、
    profiles（写入客户端注册信息，profiles_remove 显式删除）。仅 flask 改动需要重启服务才能生效。
    """
    if request.method == "POST":
        return _handle_config_post()
    # GET：返回完整配置快照
    return jsonify(_config_snapshot())


@bp.route("/profiles", methods=["GET"])
def profiles_endpoint():
    """轻量读取站点档案：真源为客户端注册信息（/api/clients 的 custom_config）。

    内容脚本注入时经后台中转拉取（HTTPS 页直连本地服务受混合内容策略拦截）；
    按 site_key（档案 id）聚合各客户端寄存的档案本体，只返回档案集，不携带
    工具配置等无关字段。服务端不解释字段；注册表为空时返回空档案集，
    不静默兜底到 definition.yaml 的出厂档案（历史事故「千问档案缺失被按 GLM 解析」）。
    """
    return jsonify({"profiles": _registry_profiles()})


@bp.route("/config/restart-port", methods=["POST", "OPTIONS"])
def restart_port():
    """以新端口重启服务，不落盘。

    这是「改端口」流程的中间步：前端先带新端口调此端点，让服务在
    新端口上重新起来；前端探测到新端口通了，再调 POST /config 把端口
    写进配置文件。这样文件是最后一步，避免写错端口把服务写死。

    请求体：{ "port": 5001 }
    响应：立即返回，随后进程重启（连接会短暂中断属正常）。
    """
    data = request.get_json(force=True, silent=True) or {}
    try:
        port = int(data.get("port"))
    except (TypeError, ValueError):
        return jsonify(success=False, error="port 必须是整数"), 400
    if port < 1 or port > 65535:
        return jsonify(success=False, error="port 超出合法范围"), 400
    # 不写配置文件：新端口仅通过启动参数传给新进程。
    # 滚动重启：先以新端口起新服务，确认可连后旧服务再退出，
    # 全程旧服务存活，不存在服务真空。本响应立即返回，
    # 后续「确认新服务→退出旧进程」在后台进行。
    rolling_restart(port)
    return jsonify(success=True, port=port)
