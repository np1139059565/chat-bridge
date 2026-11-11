"""
路由：配置读写

- GET  /config  返回当前配置（flask / limits / tools / 站点规则等）
- POST /config  部分更新配置并回写配置文件

部分更新支持：
- flask.host / flask.port        需重启服务才能生效
- tools.<name>.enabled           即时生效
- tools.run_command.languages    即时生效
- limits.max_json_chars          即时生效
- GET  /profiles 轻量返回站点档案（内容脚本注入时经后台中转拉取）
- profiles（站点档案）           按档案 id 合并，未提交的档案保留，即时生效
"""
from flask import Blueprint, jsonify, request

import json
import threading
from pathlib import Path

import runtime
import tool_config
from config_store import sanitize_profiles, save_config_to_yaml, derive_site_profiles
from service_control import rolling_restart

bp = Blueprint("config_route", __name__)

# 后端草稿（缓存）文件：界面改动立即落此文件；【覆盖】才写母版（入库、可分发）。
# 本机文件，不入库；master 仍是 definition.yaml + runtime.yaml。
DRAFT_PATH = Path(__file__).resolve().parent.parent / "config" / "config_draft.json"
_draft_lock = threading.Lock()

def _load_draft():
    try:
        if DRAFT_PATH.exists():
            return json.loads(DRAFT_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None

def _save_draft(draft):
    with _draft_lock:
        DRAFT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DRAFT_PATH.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return True

def _clear_draft():
    with _draft_lock:
        try:
            DRAFT_PATH.unlink(missing_ok=True)
        except Exception:
            pass



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


def _apply_profiles_section(data, changed):
    """应用 profiles 区块：站点档案按 id 合并，不再整集替换。

    方案 v3（D2）：【覆盖】只提交当前站点那份档案。整集替换会让 A 电脑改
    glm 时冲掉 B 电脑刚提交的 deepseek，故未出现在请求里带之外的档案原样保留。
    删除须经 data["profiles_remove"] 显式列出 id，避免与「未提交」混淆。
    合并后同步派生 site_profiles，防止内存映射与档案集漂移。
    """
    current = runtime.CONFIG.get("profiles", {})
    merged = dict(current)
    block = data.get("profiles")
    if isinstance(block, dict):
        for pid, entry in sanitize_profiles(block).items():
            merged[pid] = entry
    removed = data.get("profiles_remove")
    if isinstance(removed, list):
        for pid in removed:
            if isinstance(pid, str) and pid in merged:
                del merged[pid]
    if merged != current:
        runtime.CONFIG["profiles"] = merged
        runtime.CONFIG["site_profiles"] = derive_site_profiles(merged)
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
        "profiles": runtime.CONFIG.get("profiles", {}),
        "tools": runtime.CONFIG.get("tools", {}),
        # 工具配置：声明 + 当前值，设置页按类型通用渲染
        "tool_config": tool_config.all_specs(),
        # 系统级配置：目录与队列上限，独立于工具
        "system_config": tool_config.system_specs(),
        "available_tools": sorted(list(runtime.TOOLS.keys())),
    }


def _apply_patch(data):
    """把一份 patch 应用到运行时并回写母版；/config 与 /config/commit 共用。"""
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


def _handle_config_post():
    """POST /config：兼容旧调用。"""
    return _apply_patch(request.get_json(force=True, silent=True) or {})


@bp.route("/config/draft", methods=["GET", "POST", "OPTIONS"])
def config_draft():
    """GET 一次回传 master + draft 两份；POST 把整份草稿落后端缓存文件。"""
    if request.method == "POST":
        _save_draft(request.get_json(force=True, silent=True) or {})
        return jsonify(success=True)
    return jsonify(success=True, master=_config_snapshot(), draft=_load_draft())

@bp.route("/config/commit", methods=["POST", "OPTIONS"])
def config_commit():
    """【覆盖】：把草稿写回母版，成功后清掉缓存文件。"""
    resp = _apply_patch(request.get_json(force=True, silent=True) or {})
    _clear_draft()
    return resp

@bp.route("/config", methods=["GET", "POST", "OPTIONS"])
def config():
    """读取（GET）或部分更新（POST）配置。

    POST 支持四个区块：flask（host/port）、tools（开关与语言）、limits（体积上限）、
    profiles（站点档案按 id 合并，profiles_remove 显式删除）。仅 flask 改动需要重启服务才能生效。
    """
    if request.method == "POST":
        return _handle_config_post()
    # GET：返回完整配置快照
    return jsonify(_config_snapshot())


@bp.route("/profiles", methods=["GET"])
def profiles_endpoint():
    """轻量读取站点档案。

    内容脚本注入时经后台中转拉取（HTTPS 页直连本地服务受混合内容策略拦截）；
    只返回档案本体，不携带工具配置等无关字段，供前端覆盖出厂默认值。
    """
    return jsonify({"profiles": runtime.CONFIG.get("profiles", {})})


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
