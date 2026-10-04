"""网页版机器人路由：网页聊天页 + 主动拉取接口 + 指令识别。

- GET  /web                    网页聊天页（手机浏览器打开）
- POST /api/web/send           网页发消息：指令走指令通道，普通文本投卡片
- POST /api/web/image          网页发图片（dataURL），贴进网页 AI 输入框
- POST /api/web/voice          网页发语音，落盘并提示 AI
- GET  /api/web/messages       主动拉取新消息（带游标增量）
- GET  /api/web/audio/<name>   取语音音频文件（浏览器直接播放）

设计说明：
- 拉取式：网页打开后才开始轮询，关闭即停，不占后台资源。
- 复用端口：与现有 Flask 服务同端口同进程，局域网即可访问（用户拍板）。
- 指令：以 / 开头走 command_panel 的同一套指令逻辑；其回执经「网页回执出口」
  落进网页收件箱，与 QQ 指令共用实现、去向不同。
"""
from flask import Blueprint, jsonify, request, Response, send_file

import paths
import web_bridge
import screenshot_store
from web_bridge import web_inbox

bp = Blueprint("web", __name__)

# 网页版在指令体系里的固定用户标识（与 command_dispatch.WEB_OPENID 一致）
WEB_OPENID = "web-user"


def _web_reply(text):
    """指令回执出口：把指令的回复文本落进网页收件箱。

    由 command_dispatch 在指令执行时回调，使同一套指令逻辑的回执
    既能发 QQ、也能落到网页。这里按「系统」角色入库，前端单独着色。
    @param text 回执文本
    """
    web_inbox.append("system", str(text or ""), kind="command-reply")


def _ensure_web_reply_sink():
    """注册网页版指令回执出口（幂等）。

    command_dispatch 是可选依赖：未导入成功也不影响网页版普通消息功能。
    """
    try:
        from remote_bridge import command_dispatch
        command_dispatch.set_web_reply_sink(_web_reply)
    except Exception as e:
        print("[web] 注册指令回执出口失败：", e)


# 模块加载即注册：指令逻辑一旦被调用，回执就能找到网页出口
_ensure_web_reply_sink()


def _safe_under(name, base_dir):
    """把文件名解析为 base_dir 下的绝对路径，并拦截目录穿越。

    只允许纯文件名（不含路径分隔符与上跳），解析后还必须落在 base_dir 内，
    否则返回 None。这样即使有人构造 ../../ 也拿不到目录外的文件。
    @param name     请求里的文件名
    @param base_dir 允许的基准目录（Path）
    @returns 合法文件路径字符串；非法返回 None
    """
    import os
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    base = base_dir.resolve()
    target = (base_dir / name).resolve()
    try:
        # 必须确实位于 base_dir 之下
        if os.path.commonpath([str(base), str(target)]) != str(base):
            return None
    except ValueError:
        # 跨盘符等情况 commonpath 会抛错，一律视为非法
        return None
    return str(target) if target.is_file() else None


def _safe_audio_path(name):
    """把音频文件名解析为绝对路径（走通用防护）。"""
    return _safe_under(name, paths.WEB_AUDIO_DIR)


@bp.route("/web-bot", methods=["GET"])
def web_page():
    """网页聊天页：返回页面骨架。

    样式与脚本外置为同目录静态文件，经 /web-bot/<name> 提供，
    无需额外静态资源目录，手机浏览器直接打开即可用。
    """
    return Response(_render_page(), mimetype="text/html; charset=utf-8")


# 静态资源 MIME 表：只放行页面所需的几类文件。
_WEB_MIME = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}


@bp.route("/web-bot/<name>", methods=["GET", "OPTIONS"])
def web_asset(name):
    """提供网页版的静态资源（样式与脚本）。

    只允许 web_bridge 目录下的 css / js / html，且拦截目录穿越；
    这样页面文件能拆小、保持在仓库行数上限内。
    """
    if request.method == "OPTIONS":
        return ("", 204)
    import os
    # 只允许纯文件名，拦截路径分隔符与上跳
    if not name or "/" in name or "\\" in name or ".." in name:
        return jsonify(success=False, error="bad_name"), 400
    ext = os.path.splitext(name)[1].lower()
    if ext not in _WEB_MIME:
        return jsonify(success=False, error="bad_type"), 400
    base = (paths.APP_DIR / "web_bridge").resolve()
    target = (base / name).resolve()
    # 必须确实落在 web_bridge 目录之下
    try:
        if os.path.commonpath([str(base), str(target)]) != str(base):
            return jsonify(success=False, error="bad_path"), 400
    except ValueError:
        return jsonify(success=False, error="bad_path"), 400
    if not target.is_file():
        return jsonify(success=False, error="not_found"), 404
    try:
        content = target.read_text(encoding="utf-8")
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
    return Response(content, mimetype=_WEB_MIME[ext])


@bp.route("/api/web/commands", methods=["GET", "OPTIONS"])
def web_commands():
    """返回指令快捷键列表，供网页「指令展开面板」渲染。

    只回快捷键本身（不含描述）：面板要一屏放下多个，长描述会挤占空间。
    数据源是指令注册表，新增内置指令时面板自动出现，无需前端改代码。
    @returns {success, commands: ["/xx", ...]}
    """
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        from remote_bridge import command_registry
        groups = command_registry.shortcut_groups()
    except Exception as e:
        print("[web] 读取指令快捷键失败：", e)
        groups = {"builtin": [], "custom": []}
    # 同时回扁平列表（兼容）与分组（新前端按内置/自定义两区渲染）
    flat = list(groups.get("builtin", [])) + list(groups.get("custom", []))
    return jsonify(success=True, commands=flat, groups=groups)


def _handle_command(text):
    """把一条以 / 开头的文本交给指令处理器执行。

    复用 QQ 指令的同一套逻辑；openid 用网页固定标识，指令回执经
    command_dispatch 的网页出口落到收件箱（不碰 QQ）。
    @param text 指令原文（含斜杠）
    @returns True 表示已作为指令处理
    """
    try:
        from remote_bridge import command_panel
    except Exception as e:
        web_inbox.append("system", "指令系统不可用：%s" % e)
        return False
    # qq_client 传 None：网页版回执走独立出口，不会用到它
    command_panel.handle_command(None, WEB_OPENID, "", text)
    return True


@bp.route("/api/web/send", methods=["POST", "OPTIONS"])
def web_send():
    """网页发消息：指令走指令通道，普通文本投卡片送进网页 AI。"""
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify(success=False, error="empty_text")
    # 指令：以 / 开头，交给指令处理器，不投网页 AI
    if text.startswith("/"):
        web_inbox.append("user", text, kind="command")
        _handle_command(text)
        return jsonify(success=True, command=True)
    # 普通消息：投进卡片总线，送进网页 AI
    card_id = web_bridge.web.ingest_text(text)
    web_inbox.append("user", text, kind="web-user")
    return jsonify(success=True, cardId=card_id)


@bp.route("/api/web/image", methods=["POST", "OPTIONS"])
def web_image():
    """网页发图片：把一组 dataURL 与文字投成一张卡片，由抽屉一次贴进网页 AI 输入框。

    支持多图 + 图文合一：图片数组与文字放同一张卡片，抽屉会把它们
    一次性贴入输入框再回车，避免拆成多条消息。
    请求体：{ dataUrls: [...], text: "" }；兼容旧的单个 dataUrl。
    """
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    # 图片列表：优先取 dataUrls 数组，兼容单个 dataUrl
    urls = data.get("dataUrls")
    if not isinstance(urls, list):
        one = str(data.get("dataUrl") or "")
        urls = [one] if one else []
    urls = [str(u) for u in urls if u]
    text = str(data.get("text") or "").strip()
    if not urls:
        return jsonify(success=False, error="empty_image")
    # 图片落盘：网页消息列表、抽屉镜像、抽屉消息列表三处都要能拿到这张图，
    # 故服务端把 dataURL 存成本地文件，三处统一按文件名经 /api/web/image-file 取用。
    names = []
    for u in urls:
        try:
            saved = screenshot_store.save_web_image(u)
            if saved and saved.get("name"):
                names.append(saved["name"])
        except Exception as e:
            print("[web] 保存网页图片失败：", e)
    # 先落盘再投卡片：卡片带上图片文件名，抽屉据此把图片挂到对应消息上
    card_id = web_bridge.web.ingest_images(urls, text, names)
    # 收件箱展示：有文字带文字，并标注图片张数；图片字段带文件名供前端渲染真图
    label = text or "[图片]"
    if len(urls) > 1:
        label = (text + " " if text else "") + "[%d 张图片]" % len(urls)
    web_inbox.append("user", label, kind="web-image", image=(names if len(names) > 1 else (names[0] if names else "")))
    return jsonify(success=True, cardId=card_id, count=len(urls), images=names)


@bp.route("/api/web/voice", methods=["POST", "OPTIONS"])
def web_voice():
    """网页发语音：接收 base64 音频，落盘后包装成文本卡片提示 AI。

    简化实现：不做 ASR（语音识别），把「收到一段语音」这一事实连同
    音频落盘路径告知 AI；落盘文件供留档与后续排查。
    请求体：{ audio: base64, format: 'webm' }
    """
    if request.method == "OPTIONS":
        return ("", 204)
    import base64
    import time
    data = request.get_json(force=True, silent=True) or {}
    b64 = str(data.get("audio") or "")
    if not b64:
        return jsonify(success=False, error="empty_audio")
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return jsonify(success=False, error="bad_base64")
    try:
        paths.WEB_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        fname = "in_" + str(int(time.time() * 1000)) + ".webm"
        (paths.WEB_AUDIO_DIR / fname).write_bytes(raw)
    except Exception as e:
        return jsonify(success=False, error="save_failed: %s" % e)
    text = "[网页语音] 用户发来一段语音（已存至 %s）。" % fname
    card_id = web_bridge.web.ingest_text(text)
    web_inbox.append("user", "[语音]", kind="web-voice")
    return jsonify(success=True, cardId=card_id, file=fname)


@bp.route("/api/web/messages", methods=["GET", "OPTIONS"])
def web_messages():
    """主动拉取新消息。

    查询参数：
    - cursor：上次拿到的最大 seq；缺省 0（配合 history=1 用于首次铺历史）
    - limit ：单次上限，缺省 200
    - history：为 1 时返回最近一批历史（首次打开页面用），否则按游标增量
    @returns {success, seq, messages}
    """
    if request.method == "OPTIONS":
        return ("", 204)
    cursor = request.args.get("cursor", "0")
    try:
        limit = int(request.args.get("limit", "200"))
    except ValueError:
        limit = 200
    if request.args.get("history") == "1":
        data = web_inbox.recent(limit if limit < 200 else 50)
    else:
        data = web_inbox.list_since(cursor, limit)
    return jsonify(success=True, **data)


@bp.route("/api/web/image-file/<name>", methods=["GET", "OPTIONS"])
def web_image_file(name):
    """取网页图片文件（指令结果截图等），供前端渲染 <img>。

    与音频接口同一套目录穿越防护：只允许纯文件名，且必须落在网页图片目录内。
    """
    if request.method == "OPTIONS":
        return ("", 204)
    path = _safe_under(name, paths.WEB_IMAGES_DIR)
    if not path:
        return jsonify(success=False, error="not_found"), 404
    ext = path.rsplit(".", 1)[-1].lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    # max_age：图片文件名唯一（时间戳+序号）、内容不变，故设强缓存，
    # 让浏览器对同一图片复用已下载的副本，点开看大图时不再重新请求。
    return send_file(path, mimetype=mime, conditional=True, max_age=604800)


@bp.route("/api/web/audio/<name>", methods=["GET", "OPTIONS"])
def web_audio(name):
    """取语音音频文件：浏览器据此自动播放。"""
    if request.method == "OPTIONS":
        return ("", 204)
    path = _safe_audio_path(name)
    if not path:
        return jsonify(success=False, error="not_found"), 404
    # conditional=True 支持 Range 请求，手机浏览器拖动进度条也能正常响应
    return send_file(path, mimetype="audio/mpeg", conditional=True)


# 正在后台合成的 seq 集合：避免同一条被多次点播时重复合成。
_synth_inflight = set()
_synth_lock = __import__("threading").Lock()


def _synth_worker(seq, text):
    """后台合成线程：合成完成后把文件名回填到收件箱，并释放占用标记。"""
    try:
        from web_bridge import web_mirror
        name = web_mirror.synthesize_voice(text)
        if name:
            web_inbox.set_voice(seq, name)
    except Exception as e:
        print("[web] 按需合成失败：", e)
    finally:
        with _synth_lock:
            _synth_inflight.discard(seq)


@bp.route("/api/web/voice-ensure", methods=["POST", "GET", "OPTIONS"])
def web_voice_ensure():
    """按需合成：网页点播某条语音时调用。

    立即返回，不在请求内做合成（合成是网络调用，放这里会阻塞接口）。
    返回 status：ready（已有音频）/ processing（已启动后台合成）/ not_found（无朗读文本）。
    前端据 status=processing 轮询 voice-status，就绪后再播放。
    查询参数：seq（消息序号）
    """
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        seq = int(request.args.get("seq", "0"))
    except (TypeError, ValueError):
        seq = 0
    msg = web_inbox.get_by_seq(seq)
    if not msg:
        return jsonify(success=False, error="not_found")
    # 已合成：直接给文件名
    if msg.get("voice"):
        return jsonify(success=True, status="ready", name=msg.get("voice"))
    text = str(msg.get("voice_text") or "")
    if not text:
        return jsonify(success=False, error="no_voice_text")
    # 已在合成中：不重复启动
    import threading
    with _synth_lock:
        if seq in _synth_inflight:
            return jsonify(success=True, status="processing")
        _synth_inflight.add(seq)
    threading.Thread(target=_synth_worker, args=(seq, text), daemon=True).start()
    return jsonify(success=True, status="processing")


@bp.route("/api/web/voice-status", methods=["GET", "OPTIONS"])
def web_voice_status():
    """查询某条消息的语音是否已合成完毕，供前端轮询。

    查询参数：seq
    返回 status：ready（含 name）/ processing / not_found
    """
    if request.method == "OPTIONS":
        return ("", 204)
    try:
        seq = int(request.args.get("seq", "0"))
    except (TypeError, ValueError):
        seq = 0
    msg = web_inbox.get_by_seq(seq)
    if not msg:
        return jsonify(success=False, error="not_found")
    if msg.get("voice"):
        return jsonify(success=True, status="ready", name=msg.get("voice"))
    with _synth_lock:
        pending = seq in _synth_inflight
    if pending or str(msg.get("voice_text") or ""):
        return jsonify(success=True, status="processing")
    return jsonify(success=False, error="no_voice_text")


def _render_page():
    """读取网页聊天页 HTML 文件并返回。

    页面独立成 web_bridge/web_page.html：单文件内嵌样式与脚本，
    无外部依赖、无构建步骤，改完刷新即生效；读失败时回退到提示页，
    避免整个接口 500。
    """
    page = paths.APP_DIR / "web_bridge" / "web_page.html"
    try:
        return page.read_text(encoding="utf-8")
    except Exception as e:
        print("[web] 读取页面文件失败：", e)
        return "<h3>网页版页面文件缺失</h3><p>请检查 flask_server/web_bridge/web_page.html</p>"
