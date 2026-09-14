"""
AI 工具调用镜像插件 —— 本地 Flask 工具服务
接收插件发来的工具调用请求，参考 codebuddy-craft 的文件读写等工具实现基础功能，
并提供 get_tool_params（根据工具 id 查询参数）。不考虑安全与脱敏，以最快方式跑通流程。

自愈相关设计：
- 工具实现放在 tools_impl.py，可热重载，改代码不必重启服务。
- 工具执行失败时返回完整堆栈（traceback）+ 错误分类（origin），
  让 AI 能区分「参数问题」与「工具代码缺陷」，避免反复改参无效重试。
- 提供 read_tool_source / hot_reload_fix 两个 AI 自愈工具，并暴露 /hot_fix 接口。
"""
import os
import re
import sys
import inspect
import importlib
import traceback
from pathlib import Path

from flask import Flask, request, jsonify, Response

import tools_impl
import custom_tools as ct
import rules as rules_mod
import card_bus
import external_tools
import prompt_sections
from routes_cards import bp as cards_bp
from routes_ext import bp as ext_bp

try:
    import yaml
except ImportError:
    yaml = None

app = Flask(__name__)

# 注册公共卡片路由与外部工具提供方通道
app.register_blueprint(cards_bp)
app.register_blueprint(ext_bp)

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
APP_DIR_STR = str(APP_DIR)

# 当前生效的工具实现（热重载后整体替换）
impl = tools_impl


# ---------- 配置：本地 YAML（配置唯一来源，插件从后端读取，不存浏览器） ----------
CONFIG_PATH = APP_DIR / "config.yaml"
CONFIG = {"flask": {"host": "127.0.0.1", "port": 5000},
          "default_profile": "glm", "site_profiles": {}, "tools": {}}


def _init_config():
    """把 YAML（或默认）合并成完整 CONFIG，并保证所有用户工具都有 enabled 开关。"""
    raw = _load_yaml_config()
    cfg = {
        "flask": raw.get("flask", {}) or {},
        "limits": raw.get("limits", {}) or {},
        "default_profile": raw.get("default_profile", "glm"),
        "site_profiles": raw.get("site_profiles", {}) or {},
        "tools": raw.get("tools", {}) or {},
    }
    cfg["flask"].setdefault("host", "127.0.0.1")
    cfg["flask"].setdefault("port", 5000)
    # 工具结果 JSON 体积上限，未配置时取默认 10 万字符
    cfg["limits"].setdefault("max_json_chars", 100000)
    for name in TOOLS:
        if name in FIX_TOOLS:
            continue  # 自愈工具始终在线，不受开关影响
        entry = cfg["tools"].get(name) or {}
        new_entry = {"enabled": bool(entry.get("enabled", True))}
        if name == "run_command":
            default_langs = getattr(impl, "RUN_COMMAND_SUPPORTED_LANGUAGES", ["cmd", "powershell", "shell", "git", "python"])
            langs = entry.get("languages") or default_langs
            new_entry["languages"] = [str(x).strip().lower() for x in langs if str(x).strip()]
        cfg["tools"][name] = new_entry
    return cfg


def _coerce(v):
    """把 YAML 标量字符串转成合适的 Python 值。"""
    v = v.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.lower() in ("null", "~", ""):
        return None
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def _mini_yaml_load(text):
    """极简 YAML 解析：仅支持本插件 config.yaml 的结构（块映射 + 行内流映射）。
    无 PyYAML 时的兜底；若装了 PyYAML 则优先用它（见 _load_yaml_config）。"""
    data = {"flask": {}, "tools": {}, "site_profiles": {}, "default_profile": "glm"}
    section = None
    for ln in text.splitlines():
        body = ln.split("#", 1)[0].rstrip()  # 去注释
        if not body.strip():
            continue
        indent = len(body) - len(body.lstrip())
        if indent != 0:
            if section == "flask" and ":" in body:
                k, _, v = body.strip().partition(":")
                data["flask"][k.strip()] = _coerce(v)
            elif section == "tools" and ":" in body:
                k, _, v = body.strip().partition(":")
                enabled = True
                m = re.search(r"enabled\s*:\s*(true|false)", v, re.I)
                if m:
                    enabled = m.group(1).lower() == "true"
                data["tools"][k.strip()] = {"enabled": enabled}
            elif section == "site_profiles" and ":" in body:
                k, _, v = body.strip().partition(":")
                data["site_profiles"][k.strip()] = _coerce(v)
            continue
        if ":" in body:
            k, _, v = body.strip().partition(":")
            k, v = k.strip(), v.strip()
            if v == "":
                section = k          # 进入块映射
            else:
                data[k] = _coerce(v)
                section = None
    return data


def _load_yaml_config():
    if not CONFIG_PATH.exists():
        return {}
    text = CONFIG_PATH.read_text(encoding="utf-8")
    if yaml:
        try:
            return yaml.safe_load(text) or {}
        except Exception as e:
            print("[config] PyYAML 解析失败，回退到内置解析：", e)
    return _mini_yaml_load(text)


def save_config_to_yaml():
    """回写 config.yaml。优先用 PyYAML 整文件重写；无 PyYAML 时按行原地修补，
    保留注释与缩进（只改 port 与 tools.<name>.enabled）。"""
    if not CONFIG_PATH.exists():
        return False
    try:
        if yaml:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.safe_dump(CONFIG, f, allow_unicode=True, sort_keys=False)
            return True
        # 兜底：行内修补，保留注释
        lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
        out, section = [], None
        for ln in lines:
            body = ln.split("#", 1)[0].rstrip()
            if body.strip() and (len(body) - len(body.lstrip())) == 0 and ":" in body:
                head, tail = body.split(":", 1)
                section = head.strip() if tail.strip() == "" else None
            if section == "flask":
                m = re.match(r"^(\s*port\s*:\s*)(\d+)", ln)
                if m:
                    out.append(m.group(1) + str(int(CONFIG["flask"]["port"])))
                    continue
            if section == "tools":
                tm = re.match(r"^\s*([A-Za-z0-9_-]+)\s*:\s*\{\s*enabled\s*:\s*(true|false)", ln)
                if tm and tm.group(1) in CONFIG["tools"]:
                    name = tm.group(1)
                    en = bool(CONFIG["tools"][name].get("enabled", True))
                    out.append(re.match(r"^(\s*[A-Za-z0-9_-]+\s*:\s*\{\s*enabled\s*:\s*)", ln).group(1)
                               + ("true" if en else "false") + " }")
                    continue
                # run_command 的 languages 列表：匹配“  languages: [...]”后紧跟的若干行“- xxx”
                if ln.lstrip().startswith("languages:") and "run_command" in CONFIG["tools"]:
                    langs = CONFIG["tools"]["run_command"].get("languages", [])
                    out.append("    languages: [" + ", ".join(langs) + "]")
                    # 跳过后续原 - xxx 行（由一个标记处理）
                    continue
            out.append(ln)
        CONFIG_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
        return True
    except Exception as e:
        print("[config] 写回 config.yaml 失败：", e)
        return False


def refresh_external_providers():
    """把【已上线】的 executor=external 工具按 provider 注册到提供方注册表。

    同步移除已不存在或不含已上线工具的提供方，避免下线后仍保留旧定义。
    """
    try:
        groups = ct.external_providers()
    except Exception as e:
        print("[ext] 读取外部工具失败：", e)
        return
    external_tools.hub.replace_providers(groups)


def is_tool_enabled(name):
    if name in FIX_TOOLS:
        return True
    entry = CONFIG.get("tools", {}).get(name)
    if not entry:
        return True
    return bool(entry.get("enabled", True))


# ---------- 错误分类：参数问题 / 环境路径问题 / 工具内部代码缺陷 ----------
def param_error_cls():
    """取当前生效模块里的 ToolParamError。

    注意：热重载会重建该类对象，若在导入期 `from tools_impl import ToolParamError`
    绑定旧类，isinstance 会失配，导致参数错误被误判成工具代码缺陷。
    """
    return getattr(impl, "ToolParamError", ())


def classify_error(e):
    """把异常归类，决定 AI 该「改参数重试」还是「改工具代码」。"""
    if isinstance(e, param_error_cls()):
        return "parameter"
    if isinstance(e, (KeyError, TypeError, ValueError)):
        return "parameter"
    if isinstance(e, (FileNotFoundError, NotADirectoryError, IsADirectoryError,
                      PermissionError, UnicodeDecodeError)):
        return "environment"
    return "tool_internal"


HINTS = {
    "parameter": "这是调用参数问题（缺失 / 类型不符 / 取值非法），不是工具代码缺陷。"
                 "请核对参数名与取值后重试，不要修改工具代码。",
    "environment": "这是运行环境或路径问题（文件不存在、权限不足、路径非法等）。"
                   "请确认路径与权限后重试。",
    "tool_internal": "这是本地工具代码自身的缺陷（异常发生在工具实现内部），"
                     "反复调整参数不可能解决。请先调用 read_tool_source 查看出错函数的源码定位问题，"
                     "再用 hot_reload_fix 打补丁并热重载，最后用原参数重试该工具。",
    "unknown_tool": "工具名不存在，请从工具目录中选择正确的名称后重试。",
    "disabled": "该工具已被管理员下线（在 config.yaml 中 disabled）。请改用其它可用工具，"
                "或上线该工具后重试；仅靠调整参数无法使其恢复。",
}

ORIGIN_LABEL = {
    "parameter": "parameter（参数问题）",
    "environment": "environment（环境/路径问题）",
    "tool_internal": "tool_internal（工具代码缺陷）",
    "unknown_tool": "unknown_tool（工具名错误）",
    "disabled": "disabled（工具已下线）",
}


def error_location(exc_tb):
    """从 traceback 里挑出最有价值的那一帧：优先工具实现模块内的最后一帧。"""
    try:
        frames = traceback.extract_tb(exc_tb)
        if not frames:
            return None
        picked = None
        for f in reversed(frames):
            if f.filename.startswith(APP_DIR_STR):
                picked = f
                break
        if picked is None:
            picked = frames[-1]
        return {
            "file": picked.filename,
            "line": picked.lineno,
            "function": picked.name,
            "source": (picked.line or "").strip(),
        }
    except Exception:
        return None


# ---------- AI 自愈工具：读源码 / 打补丁热重载 ----------
def t_read_tool_source(p):
    name = p.get("tool") or p.get("tool_id")
    if not name:
        raise impl.ToolParamError("缺少参数 tool")
    fn = DISPATCH.get(name)
    if not fn:
        raise impl.ToolParamError("未知工具: %s（可用：%s）" % (name, ", ".join(sorted(DISPATCH.keys()))))
    try:
        src = inspect.getsource(fn)
    except Exception as e:
        raise impl.ToolParamError("无法读取该工具的源码：%s" % e)
    return {"tool": name, "file": inspect.getsourcefile(fn), "source": src}


def _resolve_impl_path(p):
    fp = p.get("file_path") or p.get("filePath")
    if not fp:
        return APP_DIR / "tools_impl.py"
    path = Path(fp)
    return path if path.is_absolute() else (APP_DIR / path)


def t_hot_reload_fix(p):
    """对本地工具代码打补丁并热重载；若补丁导致模块无法加载，自动回滚。"""
    fp = _resolve_impl_path(p)
    if not fp.exists():
        raise impl.ToolParamError("文件不存在: %s" % fp)

    old = p.get("old_str")
    new = p.get("new_str")
    content = p.get("content")
    if content is None and not old:
        raise impl.ToolParamError("old_str/new_str 与 content 至少要提供一组")

    original = fp.read_text(encoding="utf-8")
    if content is not None:
        patched = content
    else:
        cnt = original.count(old)
        if cnt == 0:
            raise impl.ToolParamError("未找到 old_str（原文需与文件内容完全一致，含缩进与换行）")
        if cnt > 1:
            raise impl.ToolParamError("old_str 在文件中出现 %d 次，不唯一，请扩大上下文" % cnt)
        patched = original.replace(old, new or "", 1)

    if patched == original:
        raise impl.ToolParamError("补丁前后内容一致，未产生任何改动")

    fp.write_text(patched, encoding="utf-8")
    try:
        _reload_impl()
        return {
            "patched": True,
            "reloaded": True,
            "file": str(fp),
            "tools": sorted(DISPATCH.keys()),
            "note": "已热重载，可立即用原参数重试该工具。",
        }
    except Exception as e:
        # 补丁把模块搞坏了：回滚文件并恢复可运行状态
        fp.write_text(original, encoding="utf-8")
        try:
            _reload_impl()
        except Exception:
            pass
        return {
            "patched": False,
            "reloaded": False,
            "rolledBack": True,
            "file": str(fp),
            "errorType": type(e).__name__,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "note": "补丁导致工具模块无法加载，已自动回滚到修复前的版本。",
        }


FIX_TOOLS = {
    "read_tool_source": t_read_tool_source,
    "hot_reload_fix": t_hot_reload_fix,
}

FIX_TOOL_META = {
    "read_tool_source": {
        "description": "读取本地工具实现的当前源码，用于定位工具代码缺陷（AI 自愈专用）",
        "parameters": [
            {"name": "tool", "type": "string", "required": True, "description": "工具名，如 read_file"},
        ],
    },
    "hot_reload_fix": {
        "description": "修复本地工具代码并热重载：对工具实现文件打补丁后重新加载，无需重启服务；失败自动回滚。",
        "parameters": [
            {"name": "file_path", "type": "string", "required": False, "description": "待修复文件，默认 tools_impl.py"},
            {"name": "old_str", "type": "string", "required": True, "description": "待替换原文（须唯一且完全匹配，含缩进）"},
            {"name": "new_str", "type": "string", "required": True, "description": "替换后的代码"},
            {"name": "content", "type": "string", "required": False, "description": "整文件重写时提供，与 old_str/new_str 二选一"},
        ],
    },
}


def _reload_impl():
    """重新加载工具实现模块，并重建 TOOLS / DISPATCH（修复类工具始终保留）。"""
    global impl, TOOLS, DISPATCH
    impl = importlib.reload(impl)
    TOOLS = dict(impl.TOOLS)
    TOOLS.update(FIX_TOOL_META)
    DISPATCH = dict(impl.DISPATCH)
    DISPATCH.update(FIX_TOOLS)


# 初始化当前生效的工具表
TOOLS = {}
DISPATCH = {}
_reload_impl()

# 配置在所有工具就绪后再初始化（需要 TOOLS / FIX_TOOLS）
CONFIG = _init_config()

# 首次启动（规则目录为空）时写入默认 self-healing 规则，供 AI 遇错时按需读取
try:
    rules_mod.seed_defaults()
except Exception as e:
    print("[rules] 初始化默认规则失败：", e)

# 加载外部工具提供方（executor=external 的工具按 provider 注册）
refresh_external_providers()


# ---------- 错误响应辅助：统一「已下线」「工具执行异常」两种返回 ----------
def _disabled_resp(name):
    return jsonify(
        success=False, tool=name,
        error="工具已下线（disabled）: %s" % name,
        errorType="ToolDisabled", origin="disabled",
        originLabel=ORIGIN_LABEL["disabled"],
        available=[k for k in TOOLS if is_tool_enabled(k)],
        hint=HINTS["disabled"],
    ), 200


def _tool_error(name, e):
    """工具执行异常：回传完整堆栈 + 分类，让 AI 区分「参数错」与「代码缺陷」。
    自定义脚本抛出的异常也走同一分类（ValueError→parameter 等）。"""
    tb_str = traceback.format_exc()
    origin = classify_error(e)
    return jsonify(
        success=False, tool=name,
        error="%s: %s" % (type(e).__name__, e),
        errorType=type(e).__name__,
        origin=origin,
        originLabel=ORIGIN_LABEL.get(origin, origin),
        location=error_location(sys.exc_info()[2]),
        traceback=tb_str,
        hint=HINTS.get(origin, ""),
    ), 200


# ---------- 路由 ----------
@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    # 禁用缓存：工具上下线、技能说明等状态变化需即时反映到前端
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/tools", methods=["GET"])
def tools():
    # 只返回「已上线」的工具；下线工具不出现在 System Prompt，也无法调用。
    # 自愈工具（read_tool_source / hot_reload_fix）永远在线；自定义工具（来自 skill）合并进来。
    # executor=external 的工具由其提供方在线时并入。
    builtin = []
    for k, v in TOOLS.items():
        if not is_tool_enabled(k):
            continue
        item = {"name": k, **v}
        if k == "run_command":
            item["languages"] = CONFIG.get("tools", {}).get("run_command", {}).get("languages", [])
        builtin.append(item)
    refresh_external_providers()
    custom = ct.all_meta()
    external = external_tools.hub.provider_tools()
    # 外部工具若已由 custom 列出（自定义工具视图），避免重复
    seen = {t.get("name") for t in custom}
    external = [t for t in external if t.get("name") not in seen]
    return jsonify({"tools": builtin + custom + external})


@app.route("/tool", methods=["POST", "OPTIONS"])
def tool():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("tool") or data.get("name")
    params = data.get("parameters") or data.get("arguments") or {}

    # 1) 内置工具（含自愈工具）
    fn = DISPATCH.get(name)
    if fn:
        if not is_tool_enabled(name):
            return _disabled_resp(name)
        try:
            result = fn(params)
            return jsonify(success=True, tool=name, result=result)
        except Exception as e:
            return _tool_error(name, e)

    # 2) 自定义工具（来自标准 skill 的 tool.json）
    ctool = ct.get_tool(name)
    if ctool:
        if not ct.is_enabled(name):
            return _disabled_resp(name)
        # 2a) executor=external：转发给提供方，阻塞等待其回传结果
        if (ctool.get("executor") or "script") == "external":
            provider = (ctool.get("provider") or "").strip()
            if not provider or not external_tools.hub.is_online(provider):
                return jsonify(
                    success=False, tool=name,
                    error="提供方离线，无法执行外部工具: %s" % name,
                    errorType="ProviderOffline", origin="environment",
                    originLabel=ORIGIN_LABEL.get("environment", "environment"),
                    hint="该工具由其提供方（扩展）执行，需提供方上线轮询后重试。",
                ), 200
            silent = bool(ctool.get("silent"))
            ok, data = external_tools.hub.dispatch(provider, name, params, silent=silent)
            if not ok:
                return jsonify(
                    success=False, tool=name,
                    error="外部工具转发失败: %s" % data,
                    errorType="ForwardError", origin="environment",
                    originLabel=ORIGIN_LABEL.get("environment", "environment"),
                    hint="提供方未在超时内回传结果，请确认扩展在线后重试。",
                ), 200
            # silent 工具：入队即结束，其结果不回传网页 AI
            return jsonify(success=True, tool=name, result=data, silent=silent)
        # 2b) executor=script：本地子进程执行
        try:
            result = ct.run(ctool, params)
            return jsonify(success=True, tool=name, result=result)
        except Exception as e:
            return _tool_error(name, e)

    return jsonify(
        success=False, tool=name,
        error="未知工具: %s" % name,
        errorType="UnknownTool",
        origin="unknown_tool",
        originLabel=ORIGIN_LABEL["unknown_tool"],
        available=list(sorted(set(list(DISPATCH.keys()) + [t["name"] for t in ct.all_meta_full()]))),
        hint=HINTS["unknown_tool"],
    ), 404


@app.route("/prompt_sections", methods=["GET", "OPTIONS"])
def prompt_section_list():
    """技能说明段落：返回已上线技能的统一说明，供镜像插件注入 System Prompt。"""
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify({"success": True, "sections": prompt_sections.sections()})


@app.route("/hot_fix", methods=["POST", "OPTIONS"])
def hot_fix():
    """AI 自愈专用 HTTP 接口：修复本地工具代码并热重载（等价于 hot_reload_fix 工具）。"""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(success=True, result=t_hot_reload_fix(data))
    except Exception as e:
        tb_str = traceback.format_exc()
        origin = classify_error(e)
        return jsonify(
            success=False,
            error="%s: %s" % (type(e).__name__, e),
            errorType=type(e).__name__,
            origin=origin,
            originLabel=ORIGIN_LABEL.get(origin, origin),
            location=error_location(sys.exc_info()[2]),
            traceback=tb_str,
            hint=HINTS.get(origin, ""),
        ), 200


@app.route("/", methods=["GET"])
def index():
    items = "".join(
        f"<li><b>{k}</b> — {v['description']}</li>" for k, v in TOOLS.items()
    )
    return Response(
        f"<h2>AI 工具调用镜像 · 本地服务</h2>"
        f"<p>POST <code>/tool</code> 调用工具，GET <code>/tools</code> 获取工具目录，"
        f"POST <code>/hot_fix</code> 修复工具代码并热重载。POST/GET <code>/config</code> 读写配置。</p>"
        f"<ul>{items}</ul>",
        mimetype="text/html",
    )


@app.route("/config", methods=["GET", "POST", "OPTIONS"])
def config():
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "POST":
        # 部分更新：flask.port（端口，需重启生效）/ tools.<name>.enabled（上下线，即时生效）
        data = request.get_json(force=True, silent=True) or {}
        changed = []
        if isinstance(data.get("flask"), dict):
            for k in ("host", "port"):
                if k in data["flask"] and str(data["flask"][k]) != str(CONFIG["flask"].get(k)):
                    CONFIG["flask"][k] = data["flask"][k]
                    changed.append("flask." + k)
        if isinstance(data.get("tools"), dict):
            for name, tv in data["tools"].items():
                if name in TOOLS and name not in FIX_TOOLS and isinstance(tv, dict):
                    enabled = bool(tv.get("enabled", True))
                    CONFIG["tools"].setdefault(name, {})["enabled"] = enabled
                    changed.append("tools." + name + "=" + str(enabled))
                    if name == "run_command" and isinstance(tv.get("languages"), list):
                        langs = [str(x).strip().lower() for x in tv["languages"] if str(x).strip()]
                        CONFIG["tools"]["run_command"]["languages"] = langs
                        changed.append("tools.run_command.languages=" + ",".join(langs))
        # 工具结果 JSON 体积上限：正整数，即时生效（tools_impl 每次调用现读 config.yaml）
        if isinstance(data.get("limits"), dict):
            v = data["limits"].get("max_json_chars")
            if v is not None:
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    return jsonify(success=False, error="limits.max_json_chars 必须是正整数"), 400
                if v <= 0:
                    return jsonify(success=False, error="limits.max_json_chars 必须大于 0"), 400
                if v != CONFIG["limits"].get("max_json_chars"):
                    CONFIG["limits"]["max_json_chars"] = v
                    changed.append("limits.max_json_chars=" + str(v))
        saved = save_config_to_yaml()
        # 端口 / host 改动需要重启进程才能重新绑定，单靠写配置无法让正在运行的服务生效
        require_restart = any(c.startswith("flask.") for c in changed)
        return jsonify(success=saved, saved=saved, changed=changed, requireRestart=require_restart)
    host = CONFIG["flask"]["host"]
    port = CONFIG["flask"]["port"]
    return jsonify({
        "flask": {"host": host, "port": port, "url": "http://%s:%s" % (host, port)},
        "limits": CONFIG.get("limits", {}),
        "default_profile": CONFIG.get("default_profile", "glm"),
        "site_profiles": CONFIG.get("site_profiles", {}),
        "tools": CONFIG.get("tools", {}),
        "available_tools": sorted([k for k in TOOLS if k not in FIX_TOOLS]),
    })


# ---------- 自定义工具（来自标准 skill 的 tool.json） ----------
@app.route("/custom_tools", methods=["GET", "OPTIONS"])
def custom_tools_list():
    if request.method == "OPTIONS":
        return ("", 204)
    roots = [str(p) for p in ct.DEFAULT_SKILL_ROOTS]
    return jsonify({"tools": ct.all_meta_full(), "scanRoots": roots})


@app.route("/custom_tools/scan", methods=["POST", "OPTIONS"])
def custom_tools_scan():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    d = (data.get("dir") or "").strip()
    try:
        return jsonify({"ok": True, "skills": ct.scan_dir(d)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/custom_tools/install", methods=["POST", "OPTIONS"])
def custom_tools_install():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    d = (data.get("dir") or "").strip()
    names = data.get("names")
    try:
        installed = ct.install(d, set(names) if names else None)
        refresh_external_providers()
        return jsonify({"ok": True, "installed": installed})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/custom_tools/<name>", methods=["PUT", "DELETE", "OPTIONS"])
def custom_tools_manage(name):
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "DELETE":
        ok = ct.remove(name)
        refresh_external_providers()
        return jsonify({"ok": bool(ok), "removed": name})
    data = request.get_json(force=True, silent=True) or {}
    t = ct.update(name, data)
    if not t:
        return jsonify({"ok": False, "error": "未找到工具：" + name}), 404
    # 上线 / 下线变化会改变提供方工具集合
    refresh_external_providers()
    return jsonify({"ok": True, "tool": t, "tool_name": name})


# ---------- 规则（Rules）文件管理：设置页增 / 删 / 改 ----------
@app.route("/rules", methods=["GET", "POST", "OPTIONS"])
def rules_list():
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        name = data.get("name")
        content = data.get("content", "")
        try:
            saved = rules_mod.write_rule(name, content, priority=data.get("priority"))
            return jsonify({"ok": True, "name": saved})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({
        "rules": rules_mod.list_rules(),
        "rulesDir": str(rules_mod.RULES_DIR),
        "priorities": rules_mod.PRIORITIES,
        "priorityLabels": rules_mod.PRIORITY_LABELS,
    })


@app.route("/rules/<name>", methods=["GET", "PUT", "DELETE", "OPTIONS"])
def rules_manage(name):
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "DELETE":
        ok = rules_mod.delete_rule(name)
        return jsonify({"ok": bool(ok), "removed": name})
    if request.method == "PUT":
        data = request.get_json(force=True, silent=True) or {}
        try:
            # 仅改优先级：未提供 content 时只更新 priority
            if "content" in data:
                saved = rules_mod.write_rule(name, data.get("content", ""), priority=data.get("priority"))
            else:
                if data.get("priority") is not None:
                    rules_mod.set_priority(name, data.get("priority"))
                saved = name
            return jsonify({"ok": True, "name": saved})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    # GET：读取单条规则内容
    if not rules_mod.valid_name(name):
        return jsonify({"ok": False, "error": "规则名非法"}), 400
    try:
        content = rules_mod.read_rule(name)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "规则不存在：" + name}), 404
    return jsonify({"ok": True, "name": name, "content": content, "priority": rules_mod.get_priority(name)})


if __name__ == "__main__":
    # 关闭 reloader：热重载由 hot_reload_fix 精确控制，避免与调试重载器打架
    # 端口来自 config.yaml（flask.port），修改后需重启服务
    flask_cfg = CONFIG.get("flask", {})
    # threaded=True：卡片与外部工具均为同步阻塞，需并发承载
    app.run(host=flask_cfg.get("host", "127.0.0.1"), port=flask_cfg.get("port", 5000),
            debug=False, threaded=True)
