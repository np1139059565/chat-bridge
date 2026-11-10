"""标准 System Prompt 接口（任务 A-2）：GET /v1/system_prompt。

与 /v1/chat/completions 同族的标准接口：返回 core/system_prompt.py 聚合
生成的标准提示词全文与分段标记。本文件只做路由层，不拼装内容、不持真源。
鉴权：无（docs/split-mirror-and-tools-service.md 6.3，服务仅监听 127.0.0.1）。
"""
from flask import Blueprint, jsonify

import system_prompt as sp

bp = Blueprint("system_prompt", __name__)


@bp.route("/v1/system_prompt", methods=["GET", "OPTIONS"])
def system_prompt_text():
    """返回标准 System Prompt：{ system_prompt, sections }。"""
    return jsonify(sp.build_system_prompt())