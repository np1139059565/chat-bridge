"""远程桥接 —— 微信通道的网页接口

职责：把微信通道的配置、扫码登录、状态查询暴露成 HTTP 接口，
供设置页操作。与 QQ 的接口并列，互不影响。

- GET  /api/bridge/weixin/status  查询微信通道状态与登录进度
- POST /api/bridge/weixin/config  保存微信开关
- POST /api/bridge/weixin/login   发起扫码登录，返回二维码
- POST /api/bridge/weixin/verify  提交手机显示的验证码
- POST /api/bridge/weixin/logout  退出登录（清除凭证）

设计要点：
  扫码是异步过程，接口一律立即返回当前状态，页面靠轮询 status 推进；
  绝不让某个 HTTP 请求阻塞等待用户扫码完成。
"""
from flask import Blueprint, jsonify, request

import remote_bridge
from remote_bridge import bridge, bridge_store, weixin_router
import app_log

bp = Blueprint("bridge_weixin", __name__)


def _status_payload():
    """组装微信通道的完整状态，供页面渲染与轮询。

    @returns 状态字典
    """
    st = bridge.status().get("weixin") or {}
    # 登录进度：未发起过登录时 login 为 None
    login = None
    if bridge.wx_login:
        login = bridge.wx_login.status()
    # 配额：单用户场景下按最近发消息的人展示
    user = weixin_router.last_user()
    quota = weixin_router.quota_status(user) if user else {"used": 0, "limit": 10, "remaining": 10}
    return {"channel": st, "login": login, "quota": quota}


@bp.route("/api/bridge/weixin/status", methods=["GET", "OPTIONS"])
def weixin_status():
    """查询微信通道状态与登录进度。"""
    return jsonify(success=True, **_status_payload())


@bp.route("/api/bridge/weixin/config", methods=["POST", "OPTIONS"])
def weixin_config():
    """保存微信通道开关。

    请求体：{ enabled: true/false }
    保存后重启桥接：开关变化需要拉起或停止长轮询。
    """
    data = request.get_json(force=True, silent=True) or {}
    patch = {}
    if "enabled" in data:
        patch["enabled"] = bool(data.get("enabled"))
    cfg = bridge_store.save_config({"weixin": patch})
    try:
        remote_bridge.bridge.restart()
    except Exception as e:
        app_log.warn("[bridge]", "重启微信通道失败：", e)
    return jsonify(success=True, weixin=cfg.get("weixin") or {}, **_status_payload())


@bp.route("/api/bridge/weixin/login", methods=["POST", "OPTIONS"])
def weixin_login_start():
    """发起扫码登录，返回二维码内容。

    二维码内容是一段 URL，前端渲染成图片即可；也可直接展示给用户点击。
    """
    try:
        mgr = bridge.ensure_wx_login()
        st = mgr.start()
    except Exception as e:
        app_log.warn("[bridge]", "发起微信登录失败：", e)
        return jsonify(success=False, error=str(e))
    return jsonify(success=True, login=st, **_status_payload())


@bp.route("/api/bridge/weixin/verify", methods=["POST", "OPTIONS"])
def weixin_verify():
    """提交手机微信上显示的验证码。

    请求体：{ code: "123" }
    """
    data = request.get_json(force=True, silent=True) or {}
    code = str(data.get("code") or "").strip()
    if not code:
        return jsonify(success=False, error="验证码不能为空")
    if not bridge.wx_login:
        return jsonify(success=False, error="当前没有进行中的登录")
    ok = bridge.wx_login.submit_verify(code)
    if not ok:
        return jsonify(success=False, error="当前不在需要验证码的阶段")
    return jsonify(success=True, **_status_payload())


@bp.route("/api/bridge/weixin/logout", methods=["POST", "OPTIONS"])
def weixin_logout():
    """退出登录：清除本地凭证并停止长轮询。"""
    try:
        if bridge.wx_client:
            bridge.wx_client.stop()
            bridge.wx_client.clear_cred()
        if bridge.wx_login:
            bridge.wx_login.cancel()
    except Exception as e:
        app_log.warn("[bridge]", "微信退出登录失败：", e)
        return jsonify(success=False, error=str(e))
    return jsonify(success=True, **_status_payload())
