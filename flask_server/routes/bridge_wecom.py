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
from remote_bridge import bridge, bridge_store
from remote_bridge.channel import wecom_chats
import app_log

bp = Blueprint("bridge_wecom", __name__)


def _status_payload():
    """组装企业微信通道状态。

    回传 secret 明文：设置页需要能查看并修改它。凭证本就存在本机配置文件里
    （runtime.yaml，不入库），明文回显不额外增加暴露面，反而避免了
    「填过之后再也看不到、想改只能重填」的不便。

    @returns 状态字典
    """
    st = bridge.status().get("wecom") or {}
    cfg = bridge_store.get_config().get("wecom") or {}
    chatid, chat_type = wecom_chats.last()
    secret = cfg.get("secret") or ""
    return {
        "channel": st,
        "botId": cfg.get("bot_id") or "",
        "secret": secret,
        # hasSecret 保留：仍有调用方只关心「填没填」，不必解析明文
        "hasSecret": bool(secret.strip()),
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
