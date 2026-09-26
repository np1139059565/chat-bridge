"""远程桥接路由：状态查询、配置读写、抽屉上报、重启。

- GET  /api/bridge/status   查询桥接状态（设置页展示）
- GET  /api/bridge/config   读取桥接配置
- POST /api/bridge/config   部分更新配置并重启桥接
- POST /api/bridge/report   抽屉上报消息切片，触发推送
"""
from flask import Blueprint, jsonify, request

import remote_bridge
from remote_bridge import bridge, bridge_store

bp = Blueprint("bridge", __name__)


@bp.route("/api/bridge/status", methods=["GET", "OPTIONS"])
def bridge_status():
    """返回桥接运行状态，供设置页指示灯与窗口信息展示。"""
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify(success=True, **bridge.status())


@bp.route("/api/bridge/config", methods=["GET", "POST", "OPTIONS"])
def bridge_config():
    """读取或部分更新桥接配置。

    POST 后自动重启桥接：凭证 / 开关变化需要重建长连接。
    """
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        cfg = bridge_store.save_config(data)
        # 配置变更后重启：app_id / app_secret / enabled 变了需要重建连接
        try:
            remote_bridge.bridge.restart()
        except Exception as e:
            print("[bridge] 重启失败：", e)
        return jsonify(success=True, config=cfg, status=bridge.status())
    # GET：返回配置（含凭证，供设置页回填）
    cfg = bridge_store.get_config()
    return jsonify(success=True, config=cfg, status=bridge.status())


@bp.route("/api/bridge/report", methods=["POST", "OPTIONS"])
def bridge_report():
    """接收抽屉上报的消息切片，分类去重后推送到 QQ。

    请求体：{ conversationId, messages:[{id, role, blocks}], openid }
    注意：messages 是全量可见切片，桥接层自行与已推送集合比对取差集。
    """
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    try:
        sent = bridge.report(data)
        return jsonify(success=True, pushed=sent)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 200


@bp.route("/api/bridge/restart", methods=["POST", "OPTIONS"])
def bridge_restart():
    """手动重启桥接。"""
    if request.method == "OPTIONS":
        return ("", 204)
    ok = bridge.restart()
    return jsonify(success=bool(ok), status=bridge.status())
