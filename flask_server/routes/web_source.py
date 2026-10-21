"""网页版 —— 源文件按路径取回接口

职责：GET /api/web/source-file?path=...，把工程内的原始文件按二进制返回。

用途：read_file 做整文件读取时不读内容、不编码，只返回源文件路径；
前端据路径取回原始字节，直接构造成 File 粘贴进输入框。
这样整文件读取不产生任何副本，也不经历 base64 往返。

安全约束：仅限工程根内文件；拒绝点文件（.git / .env 等不外泄）。
"""
import os

from flask import Blueprint, jsonify, request, send_file

import paths
import app_log

bp = Blueprint("web_source", __name__)

# 扩展名 → MIME：只影响浏览器如何标记该文件，不影响内容
_MIME = {
    ".txt": "text/plain", ".md": "text/markdown", ".json": "application/json",
    ".py": "text/plain", ".js": "text/plain", ".css": "text/plain",
    ".html": "text/plain", ".yaml": "text/plain", ".yml": "text/plain",
    ".xml": "text/plain", ".csv": "text/plain", ".log": "text/plain",
}


def _resolve(raw_path):
    """把请求路径解析为工程根内的真实文件路径，越界或不存在返回 None。

    与按文件名的接口不同，本接口接受完整路径，故安全性靠
    「必须落在工程根内」与「拒绝点文件」两道约束保证。
    @param raw_path 请求里的原始路径（绝对或相对）
    @returns 合法文件路径字符串；非法返回 None
    """
    if not raw_path:
        return None
    root = os.path.abspath(str(paths.PROJECT_ROOT))
    # 相对路径以工程根为基准解析（与 read_file 工具口径一致）
    target = os.path.abspath(raw_path if os.path.isabs(raw_path) else os.path.join(root, raw_path))
    # 与 read_file 工具能力对齐：该工具能读任意路径的文件，
    # 本接口若只放行工程根内，就会出现「读到了却贴不进去」的割裂
    # （跨盘文件一律 404，前端最终报「读取文件失败」）。
    # 故不再限制工程根，只要求目标确实是存在的文件——目录不可取。
    if not os.path.isfile(target):
        return None
    try:
        import path_policy
        path_policy.check_path(target, write=False)
    except Exception:
        return None
    return target


@bp.route("/api/web/source-file", methods=["GET", "OPTIONS"])
def web_source_file():
    """按路径返回原始文件字节，供前端直接构造 File 粘贴。

    查询参数：path（工程内路径，绝对或相对）。
    不复制、不编码：直接以二进制流返回源文件内容。
    """
    target = _resolve(request.args.get("path", ""))
    if not target:
        return jsonify(success=False, error="not_found"), 404
    ext = os.path.splitext(target)[1].lower()
    mime = _MIME.get(ext, "application/octet-stream")
    try:
        return send_file(target, mimetype=mime, conditional=True)
    except OSError as e:
        app_log.warn("[web]", "读取源文件失败：", e)
        return jsonify(success=False, error="read_failed"), 500
