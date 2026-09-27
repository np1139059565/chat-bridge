"""远程桥接路由：状态查询、配置读写、抽屉上报、结果回传、重启。

- GET  /api/bridge/status   查询桥接状态（设置页展示）
- GET  /api/bridge/config   读取桥接配置
- POST /api/bridge/config   部分更新配置并重启桥接
- POST /api/bridge/report   抽屉上报消息切片，触发推送
- POST /api/bridge/result   抽屉回传指令执行结果，转发到 QQ
"""
from flask import Blueprint, jsonify, request

import remote_bridge
from remote_bridge import bridge, bridge_store, command_panel, message_router

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


def _try_send_image(client, openid, image):
    """尝试把 dataURL 截屏发到 QQ。

    成功返回 None；失败返回应回退发送的提示文本（含本地路径），
    让用户至少知道图存在哪，而不是只看到一句「发送失败」。
    """
    saved = _save_data_url(image)
    if not saved:
        return "截屏已收到，但保存失败"
    # 直接读本地文件上传（Base64），无需公网地址
    msg_id, seq = message_router.next_seq(openid)
    if not msg_id:
        return "截屏已保存，但回复窗口已关闭\n路径：%s" % saved["path"]
    ok, err = client.send_c2c_image(openid, saved["path"], msg_id=msg_id, msg_seq=seq)
    if ok:
        return None
    return "截屏已保存，但发送图片失败：%s\n路径：%s" % (err, saved["path"])


def _send_text(client, openid, text):
    """向 QQ 发送一条文本；窗口已关闭时静默跳过。"""
    msg_id, seq = message_router.next_seq(openid)
    if msg_id:
        client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq)


def _take_result_context(data):
    """取出待回传请求并确认桥接在线。

    返回 (client, openid, err_resp)：出错时 client 为 None、err_resp 为响应；
    成功时 err_resp 为 None。请求不存在或已过期属正常情况，返回提示而非报错
    （可能用户已离开或重复回传）。
    """
    rid = data.get("request_id") or ""
    item = command_panel.take_pending(rid) if rid else None
    if not item:
        return None, "", jsonify(success=False, error="pending_not_found")
    client = bridge.client
    if not client:
        return None, "", jsonify(success=False, error="bridge_offline")
    return client, item.get("openid") or "", None


def _deliver_result(client, openid, data):
    """把回传结果送达 QQ：优先按图片发送，失败则转为文本回退。

    返回成功响应；无内容可发时也返回成功（回传本身已确认接收）。
    """
    text = data.get("text") or ""
    image = data.get("image") or ""
    # 截屏且无文本：优先按图片发送；失败则把错误信息转为文本回退发送
    if image and not text:
        fallback = _try_send_image(client, openid, image)
        if fallback is None:
            return jsonify(success=True, sent="image")
        text = fallback
    if openid and text:
        _send_text(client, openid, text)
    return jsonify(success=True)


@bp.route("/api/bridge/result", methods=["POST", "OPTIONS"])
def bridge_result():
    """接收抽屉回传的指令执行结果，转发到 QQ。

    用于 /sessions、/screenshot 这类「浏览器执行后要回传结果」的指令。
    请求体：{ request_id, text }（text 为已格式化好的文本，或图片附件另行处理）
    """
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    client, openid, err = _take_result_context(data)
    if err is not None:
        return err
    return _deliver_result(client, openid, data)


def _save_data_url(data_url):
    """把 dataURL 图片保存到本地文件，返回绝对路径；失败返回空串。

    截屏存到 flask_server/screenshots/ 下，文件名带时间戳便于分辨。
    """
    import base64
    import os
    import time
    try:
        # dataURL 形如 data:image/png;base64,xxxx
        if "," not in data_url:
            return ""
        head, b64 = data_url.split(",", 1)
        ext = ".png"
        if "image/jpeg" in head:
            ext = ".jpg"
        raw = base64.b64decode(b64)
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")
        if not os.path.isdir(out_dir):
            os.makedirs(out_dir)
        name = "shot_" + time.strftime("%Y%m%d_%H%M%S") + ext
        path = os.path.join(out_dir, name)
        with open(path, "wb") as f:
            f.write(raw)
        # 同时返回文件名与路径：文件名供拼公网 URL，路径供回退提示
        return {"name": name, "path": path}
    except Exception as e:
        print("[bridge] 保存截屏失败：", e)
        return None


def _cmd_upsert(data):
    """新增或修改一条指令（index 为 null 时新增，否则修改该下标）。"""
    entry = data.get("entry") or {}
    idx = data.get("index")
    # 保存前校验：命令名格式 / 重复、组合子指令是否存在。
    # 放在后端做，前端绕过也拦得住。
    err = command_panel.validate_command(entry, idx)
    if err:
        return jsonify(success=False, error=err)
    return jsonify(success=True, commands=bridge_store.upsert_command(idx, entry))


def _cmd_remove(data):
    """删除指定下标的指令。"""
    return jsonify(success=True, commands=bridge_store.remove_command(int(data.get("index"))))


@bp.route("/api/bridge/commands", methods=["GET", "POST", "DELETE", "OPTIONS"])
def bridge_commands():
    """指令的增删改：独立接口，避免与 saveBridge 的全量覆盖互相干扰。

    - GET            ：列出全部指令
    - POST {index?, entry}：index 为 null 时新增，否则修改该下标
    - DELETE {index} ：删除该下标
    """
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "GET":
        return jsonify(success=True, commands=bridge_store.list_commands())
    data = request.get_json(force=True, silent=True) or {}
    try:
        if request.method == "POST":
            return _cmd_upsert(data)
        return _cmd_remove(data)
    except Exception as e:
        # IndexError（下标越界）与其它异常统一回传错误文本，由前端提示
        return jsonify(success=False, error=str(e))


@bp.route("/api/bridge/restart", methods=["POST", "OPTIONS"])
def bridge_restart():
    """手动重启桥接。"""
    if request.method == "OPTIONS":
        return ("", 204)
    ok = bridge.restart()
    return jsonify(success=bool(ok), status=bridge.status())
