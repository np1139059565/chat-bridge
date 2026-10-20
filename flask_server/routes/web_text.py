"""网页版 —— 文本文件取回接口

职责：GET /api/web/text-file，按路径与行范围取回文本片段，供前端把大段正文
粘贴进对话（read_file 返回 file_ref 时，正文不随工具结果回传，由此接口取回）。

从 routes/web.py 拆出，使后者保持在仓库行数上限内。

安全约束：仅限工程根内文件；拒绝点文件（.git / .env 等不外泄）；
单次正文上限 2MB。不生成临时副本，直接读源文件，故无需清理策略。
"""
from flask import Blueprint, jsonify, request

import os

import paths
import app_log

bp = Blueprint("web_text", __name__)


# 取回接口的正文体积上限（字节）：防止被用来下载超大文件
_MAX_REF_BYTES = 2 * 1024 * 1024


def _resolve_project_file(raw_path):
    """把请求里的路径解析为工程根内的真实文件路径，越界或不存在返回 None。

    与 _safe_under 的差别：本接口接受完整路径（read_file 的 file_ref 带的是
    绝对路径），故不能只收纯文件名；安全性改由「必须落在工程根内」保证，
    同时拒绝点文件与非普通文件，避免暴露配置密钥或设备文件。
    @param raw_path 请求里的原始路径（绝对或相对）
    @returns 合法文件路径字符串；非法返回 None
    """
    import os
    if not raw_path:
        return None
    root = os.path.abspath(str(paths.PROJECT_ROOT))
    target = os.path.abspath(raw_path if os.path.isabs(raw_path) else os.path.join(root, raw_path))
    try:
        # 必须确实位于工程根之内
        if os.path.commonpath([root, target]) != root:
            return None
    except ValueError:
        # 跨盘符等情况一律视为非法
        return None
    # 拒绝点文件与目录：工程根内的 .git / .env 等不应经此接口外泄
    rel = os.path.relpath(target, root)
    for part in rel.split(os.sep):
        if part.startswith("."):
            return None
    return target if os.path.isfile(target) else None


@bp.route("/api/web/text-file", methods=["GET", "OPTIONS"])
def web_text_file():
    """按路径取回文本文件片段，供前端把大段正文粘贴进对话。

    查询参数：path（工程内路径）、start（起始行，从 1 开始）、end（结束行，含）。
    返回 JSON：{success, path, content, lines:[start,end], total_lines}。
    正文不写任何临时副本，直接读源文件，故无需额外清理策略。
    """
    raw = request.args.get("path", "")
    target = _resolve_project_file(raw)
    if not target:
        return jsonify(success=False, error="not_found"), 404
    # 行范围：缺省读全文；非法值按默认处理，避免抛异常
    try:
        start = max(1, int(request.args.get("start", "1")))
    except (TypeError, ValueError):
        start = 1
    try:
        end = int(request.args.get("end", "0"))
    except (TypeError, ValueError):
        end = 0
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as e:
        app_log.warn("[web]", "取回文本失败：", e)
        return jsonify(success=False, error="read_failed"), 500
    total = len(lines)
    # 行号归一：start 超界时钳到末行，end 缺省或超界时取到末行
    start = min(start, max(1, total))
    end = total if end <= 0 else min(end, total)
    if end < start:
        end = start
    content = "".join(lines[start - 1:end])
    # 体积护栏：超限返回错误，提示缩小行范围
    size = len(content.encode("utf-8"))
    if size > _MAX_REF_BYTES:
        return jsonify(success=False, error="too_large", size=size,
                       limit=_MAX_REF_BYTES), 413
    return jsonify(success=True, path=target, content=content,
                   lines=[start, end], total_lines=total)
