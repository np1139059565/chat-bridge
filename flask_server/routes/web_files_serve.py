"""网页版机器人 —— 静态文件下发路由

职责：把网页端需要的三类文件按文件名安全下发，从 routes/web.py 抽出，
使后者保持在仓库行数上限内。

三类文件：
  - 网页图片（指令结果截图等）→ /api/web/image-file
  - 工具截图（debug_chrome 抓屏结果）→ /api/web/screenshot-file
  - 语音音频（TTS 合成产物）→ /api/web/audio

共同的安全要求：只接受纯文件名，解析后必须落在基准目录内，
避免用 ../ 之类的构造读到目录外的文件。

依赖：flask、os、paths
"""
import os

from flask import Blueprint, jsonify, send_file

import paths

# 独立蓝图：与 web_file 一致的做法，使 routes/web.py 保持在行数上限内。
# 蓝图名不得与既有重复（web / web_clientlog / web_source / web_file）。
bp = Blueprint("web_files_serve", __name__)


def _safe_under(name, base_dir):
    """把文件名解析为 base_dir 下的绝对路径，并拦截目录穿越。

    只允许纯文件名（不含路径分隔符与上跳），解析后还必须落在 base_dir 内，
    否则返回 None。这样即使有人构造 ../../ 也拿不到目录外的文件。
    @param name     请求里的文件名
    @param base_dir 允许的基准目录（Path）
    @returns 合法文件路径字符串；非法返回 None
    """
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


def _send_image_under(name, base_dir):
    """按基准目录安全地发送一张图片：目录穿越校验 + MIME 判定 + 强缓存。

    图片文件名唯一（时间戳 + 序号）、内容不变，故设一周强缓存，
    浏览器对同一张图复用已下载副本，点开看大图不再重新请求。
    网页图片与工具截图两张表共用本函数，只是基准目录不同。
    @param name     请求里的文件名
    @param base_dir 允许的基准目录（Path）
    @returns Flask 响应：命中图片返回文件，否则 404
    """
    path = _safe_under(name, base_dir)
    if not path:
        return jsonify(success=False, error="not_found"), 404
    # 只按扩展名区分 jpeg 与 png，其余一律按 png 发送
    ext = path.rsplit(".", 1)[-1].lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"
    return send_file(path, mimetype=mime, conditional=True, max_age=604800)


@bp.route("/api/web/image-file/<name>", methods=["GET", "OPTIONS"])
def web_image_file(name):
    """取网页图片文件（指令结果截图等），供前端渲染 <img>。"""
    return _send_image_under(name, paths.WEB_IMAGES_DIR)


@bp.route("/api/web/screenshot-file/<name>", methods=["GET", "OPTIONS"])
def web_screenshot_file(name):
    """取工具截图文件（debug_chrome 的 get_page_snapshot 结果），供前端渲染 <img>。

    前端据此把工具截图按文件名挂到对应消息上，无需把 base64 塞进正文。
    """
    return _send_image_under(name, paths.SCREENSHOTS_DIR)


@bp.route("/api/web/audio/<name>", methods=["GET", "OPTIONS"])
def web_audio(name):
    """取语音音频文件：浏览器据此自动播放。"""
    path = _safe_audio_path(name)
    if not path:
        return jsonify(success=False, error="not_found"), 404
    # max_age：音频文件名唯一（时间戳+序号）、内容不变，故设强缓存，
    # 让浏览器留住已下载副本，断网后仍可复播同一条语音。
    # conditional=True 支持 Range 请求，手机浏览器拖动进度条也能正常响应。
    return send_file(path, mimetype="audio/mpeg", conditional=True, max_age=604800)
