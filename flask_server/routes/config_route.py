"""
路由：配置读写

- GET  /config  返回当前配置（flask / limits / tools / 站点规则等）
- POST /config  部分更新配置并回写 config.yaml

部分更新支持：
- flask.host / flask.port        需重启服务才能生效
- tools.<name>.enabled           即时生效
- tools.run_command.languages    即时生效
- limits.max_json_chars          即时生效
"""
from flask import Blueprint, jsonify, request

import runtime
from config_store import save_config_to_yaml
from service_control import rolling_restart

bp = Blueprint("config_route", __name__)


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


def _config_snapshot():
    """构造 GET /config 的完整配置快照。"""
    host = runtime.CONFIG["flask"]["host"]
    port = runtime.CONFIG["flask"]["port"]
    return {
        "flask": {"host": host, "port": port, "url": "http://%s:%s" % (host, port)},
        "limits": runtime.CONFIG.get("limits", {}),
        "default_profile": runtime.CONFIG.get("default_profile", "glm"),
        "site_profiles": runtime.CONFIG.get("site_profiles", {}),
        "tools": runtime.CONFIG.get("tools", {}),
        "available_tools": sorted(list(runtime.TOOLS.keys())),
    }


@bp.route("/config", methods=["GET", "POST", "OPTIONS"])
def config():
    """读取（GET）或部分更新（POST）配置。

    POST 支持三个区块：flask（host/port）、tools（开关与语言）、limits（体积上限）。
    仅 flask 改动需要重启服务才能生效，因此单独标记 requireRestart。
    """
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        changed = []
        _apply_flask_section(data, changed)
        _apply_tools_section(data, changed)
        err = _apply_limits_section(data, changed)
        if err is not None:
            return err
        saved = save_config_to_yaml()
        # 端口 / host 改动需要重启进程才能重新绑定，单靠写配置无法让正在运行的服务生效
        require_restart = any(c.startswith("flask.") for c in changed)
        return jsonify(success=saved, saved=saved, changed=changed, requireRestart=require_restart)
    # GET：返回完整配置快照
    return jsonify(_config_snapshot())


@bp.route("/config/restart-port", methods=["POST", "OPTIONS"])
def restart_port():
    """以新端口重启服务，不落盘。

    这是「改端口」流程的中间步：前端先带新端口调此端点，让服务在
    新端口上重新起来；前端探测到新端口通了，再调 POST /config 把端口
    写进 config.yaml。这样文件是最后一步，避免写错端口把服务写死。

    请求体：{ "port": 5001 }
    响应：立即返回，随后进程重启（连接会短暂中断属正常）。
    """
    if request.method == "OPTIONS":
        return ("", 204)
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
