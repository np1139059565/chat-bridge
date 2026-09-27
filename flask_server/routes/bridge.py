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


@bp.route("/api/bridge/result", methods=["POST", "OPTIONS"])
def bridge_result():
    """接收抽屉回传的指令执行结果，转发到 QQ。

    用于 /sessions、/screenshot 这类「浏览器执行后要回传结果」的指令。
    请求体：{ request_id, text }（text 为已格式化好的文本，或图片附件另行处理）
    """
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    rid = data.get("request_id") or ""
    item = command_panel.take_pending(rid) if rid else None
    if not item:
        # 请求不存在或已过期：正常返回，不报错（可能用户已离开或重复回传）
        return jsonify(success=False, error="pending_not_found")
    client = bridge.client
    if not client:
        return jsonify(success=False, error="bridge_offline")
    openid = item.get("openid") or ""
    text = data.get("text") or ""
    image = data.get("image") or ""
    # 截屏：先落盘拿到文件名。若配置了公网地址，就把图片发到 QQ；
    # 否则回退为回复文件路径（QQ 取不到本机 127.0.0.1 的图）。
    if image and not text:
        saved = _save_data_url(image)
        if not saved:
            text = "截屏已收到，但保存失败"
        else:
            # 直接读本地文件上传（Base64），无需公网地址
            msg_id, seq = message_router.next_seq(openid)
            ok, err = (False, "no_window")
            if msg_id:
                ok, err = client.send_c2c_image(openid, saved["path"], msg_id=msg_id, msg_seq=seq)
            if ok:
                return jsonify(success=True, sent="image")
            text = "截屏已保存，但发送图片失败：%s\n路径：%s" % (err, saved["path"])
    if openid and text:
        msg_id, seq = message_router.next_seq(openid)
        if msg_id:
            client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq)
    return jsonify(success=True)


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
            entry = data.get("entry") or {}
            idx = data.get("index")
            # 保存前校验：命令名格式 / 重复、组合子指令是否存在。
            # 放在后端做，前端绕过也拦得住。
            err = command_panel.validate_command(entry, idx)
            if err:
                return jsonify(success=False, error=err)
            cmds = bridge_store.upsert_command(idx, entry)
            return jsonify(success=True, commands=cmds)
        # DELETE
        cmds = bridge_store.remove_command(int(data.get("index")))
        return jsonify(success=True, commands=cmds)
    except IndexError as e:
        return jsonify(success=False, error=str(e))
    except Exception as e:
        return jsonify(success=False, error=str(e))


@bp.route("/api/bridge/restart", methods=["POST", "OPTIONS"])
def bridge_restart():
    """手动重启桥接。"""
    if request.method == "OPTIONS":
        return ("", 204)
    ok = bridge.restart()
    return jsonify(success=bool(ok), status=bridge.status())
