"""远程桥接 —— 企业微信通道的网页接口

职责：把企业微信通道的配置与状态暴露成 HTTP 接口，供设置页操作。
与微信的接口并列，互不影响。

- GET  /api/bridge/wecom/status  查询通道状态
- POST /api/bridge/wecom/config  保存开关与凭证

企业微信凭证是手工填的 BotID / Secret（不是扫码），
Secret 只显示一次，保存后页面只回显是否已填，不回传明文。
"""
from flask import Blueprint, jsonify, request

import remote_bridge
from remote_bridge import bridge, bridge_store, wecom_router
import app_log

bp = Blueprint("bridge_wecom", __name__)


def _status_payload():
    """组装企业微信通道状态。

    不回传 secret 明文：它只显示一次，页面无需回显，
    回传反而增加泄露面。只告知「是否已填」。

    @returns 状态字典
    """
    st = bridge.status().get("wecom") or {}
    cfg = bridge_store.get_config().get("wecom") or {}
    chatid, chat_type = wecom_router.last_chat()
    return {
        "channel": st,
        "botId": cfg.get("bot_id") or "",
        "hasSecret": bool((cfg.get("secret") or "").strip()),
        "chatid": chatid,
        "chatType": chat_type,
    }


@bp.route("/api/bridge/wecom/status", methods=["GET", "OPTIONS"])
def wecom_status():
    """查询企业微信通道状态。"""
    return jsonify(success=True, **_status_payload())


@bp.route("/api/bridge/wecom/config", methods=["POST", "OPTIONS"])
def wecom_config():
    """保存企业微信通道开关与凭证。

    请求体：{ enabled?, bot_id?, secret? }
    secret 留空表示「不修改已有值」——避免用户只想改开关时把密钥清空。
    保存后重启桥接以重建长连接。
    """
    data = request.get_json(force=True, silent=True) or {}
    patch = {}
    if "enabled" in data:
        patch["enabled"] = bool(data.get("enabled"))
    if "bot_id" in data:
        patch["bot_id"] = str(data.get("bot_id") or "").strip()
    # secret 留空不覆盖：页面上它是密码框，留空即「保持原值」
    secret = str(data.get("secret") or "").strip()
    if secret:
        patch["secret"] = secret
    cfg = bridge_store.save_config({"wecom": patch})
    try:
        remote_bridge.bridge.restart()
    except Exception as e:
        app_log.warn("[bridge]", "重启企业微信通道失败：", e)
    return jsonify(success=True, wecom=cfg.get("wecom") or {}, **_status_payload())
