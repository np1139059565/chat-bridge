"""
路由：指令清单查询（定义收归后的统一出口）

- GET /api/commands       返回三个来源合并后的指令清单
- GET /api/commands/help  返回按来源分组的帮助文本

约定：
- 只做定义查询，不改执行通道；指令回执不进入 AI 对话流；
- 与 /api/commands/pending（执行侧取件）是不同接口，互不替代。
"""
from flask import Blueprint, jsonify

import paths  # noqa: F401  触发路径引导，保证下面的扁平导入可用
import command_catalog as catalog

bp = Blueprint("command_catalog_route", __name__)


@bp.route("/api/commands", methods=["GET", "OPTIONS"])
def commands_list():
    """返回内置、自定义、客户端三来源合并后的统一指令清单。"""
    return jsonify({"success": True, "commands": catalog.list_commands()})


@bp.route("/api/commands/help", methods=["GET", "OPTIONS"])
def commands_help():
    """返回按来源分组的帮助文本，内容与清单取自同一次读取。"""
    # 先取清单再生成文本：两处内容严格一致，不产生二次读取漂移。
    entries = catalog.list_commands()
    return jsonify({"success": True, "help": catalog.help_text(entries)})
