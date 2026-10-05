"""远程桥接路由：状态查询、配置读写、抽屉上报、结果回传、重启。

- GET  /api/bridge/status   查询桥接状态（设置页展示）
- GET  /api/bridge/config   读取桥接配置
- POST /api/bridge/config   部分更新配置并重启桥接
- POST /api/bridge/report   抽屉上报消息切片，触发推送
- POST /api/bridge/result   抽屉回传指令执行结果，转发到 QQ
"""
import threading

from flask import Blueprint, jsonify, request

import remote_bridge
import screenshot_store
from remote_bridge import bridge, bridge_store, command_panel, message_router

bp = Blueprint("bridge", __name__)

# 各会话「推送处理中」标记：QQ 推送是重活（合成 + 逐条发送），放后台线程跑，
# 请求立即返回，避免堆积切片把请求线程拖死。同一会话若上一轮还在跑，
# 本轮直接跳过——抽屉每 2.5 秒重报全量切片，跳过不会丢消息，天然形成背压。
_report_busy = {}
_report_lock = threading.Lock()


def _run_report_async(data):
    """把 QQ 推送放到后台线程执行，完成后清除该会话的「处理中」标记。"""
    conv = data.get("conversationId") or "__default__"

    def worker():
        try:
            bridge.report(data)
        except Exception as e:
            print("[bridge] 后台推送失败：", e)
        finally:
            with _report_lock:
                _report_busy.pop(conv, None)

    threading.Thread(target=worker, daemon=True).start()


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
    # 网页版镜像：无论 QQ 是否在线，都把这次切片存一份进网页收件箱，
    # 让手机网页能拉到 AI 回复。失败不影响 QQ 推送。
    try:
        from web_bridge import web_mirror
        web_mirror.mirror_report(data.get("messages") or [])
    except Exception as e:
        print("[web] 镜像上报失败：", e)
    # QQ 推送放后台线程执行，请求立即返回：合成 + 逐条发送是重活，
    # 若在请求线程里同步跑，堆积切片会把接口拖死。
    # 同一会话上一轮仍在处理则跳过——抽屉会重报全量切片，跳过不丢消息，
    # 同时天然形成背压，避免线程无限堆积。
    conv = data.get("conversationId") or "__default__"
    with _report_lock:
        if conv in _report_busy:
            return jsonify(success=True, pushed=0, skipped=True)
        _report_busy[conv] = True
    _run_report_async(data)
    return jsonify(success=True, accepted=True)


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


# 网页版在指令体系里的固定标识（与 command_dispatch.WEB_OPENID 保持一致）
_WEB_OPENID = "web-user"


def _take_result_context(data):
    """取出待回传请求，并确定回传去向。

    返回 (client, openid, err_resp)：出错时 err_resp 为响应，成功时为 None。
    - 网页版（openid == web-user）：不依赖 QQ 连接，client 返回 None，走收件箱；
    - QQ 版：client 为 bridge.client，必须在线，否则报 bridge_offline。
    请求不存在或已过期属正常情况，返回提示而非报错（可能用户已离开或重复回传）。
    """
    rid = data.get("request_id") or ""
    item = command_panel.take_pending(rid) if rid else None
    if not item:
        return None, "", jsonify(success=False, error="pending_not_found")
    openid = item.get("openid") or ""
    # 网页版：没有 QQ 客户端，也不该要求它在线，直接放行
    if openid == _WEB_OPENID:
        return None, openid, None
    client = bridge.client
    if not client:
        return None, "", jsonify(success=False, error="bridge_offline")
    return client, openid, None


def _deliver_result_web(text, image):
    """把网页版指令的执行结果落进网页收件箱。

    与 QQ 版同一份结果，去向不同：这里不进 QQ，而是存进收件箱，
    由网页按游标拉取后展示。图片存进网页图片目录并带 image 字段。
    @param text  结果文本（可为空）
    @param image 结果图片的 dataURL（可为空）
    @returns Flask 响应
    """
    from web_bridge import web_inbox
    if image:
        saved = screenshot_store.save_web_image(image)
        if saved:
            # 图片消息：带 image 字段，前端据此渲染 <img>
            web_inbox.append("system", text or "[截图]", kind="command-image", image=saved["name"])
            return jsonify(success=True, sent="image")
        # 存盘失败：把错误信息转为文本回退，至少让用户知道结果没丢
        text = (text + "\n" if text else "") + "截图保存失败"
    if text:
        web_inbox.append("system", text, kind="command-reply")
    return jsonify(success=True)


def _deliver_result_qq_sync(client, openid, data):
    """把 QQ 版回传结果实际投递出去（在后台线程执行，故不构造 HTTP 响应）。

    - 截屏且无文本时优先按图片发送，失败则把错误信息转为文本回退；
    - 发送是网络调用（图片上传 / 文本发送），放后台线程跑，
      绝不阻塞 /api/bridge/result 的请求线程。
    无内容可发时直接返回（回传本身已确认接收）。
    """
    text = data.get("text") or ""
    image = data.get("image") or ""
    # 截屏且无文本时优先按图片发送；失败则把错误信息转为文本回退
    if image and not text:
        fallback = _try_send_image(client, openid, image)
        if fallback is None:
            return
        text = fallback
    if openid and text:
        _send_text(client, openid, text)


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
    # 网页版：结果落本地收件箱，快且不涉网络，同步完成即可。
    if openid == _WEB_OPENID:
        return _deliver_result_web(data.get("text") or "", data.get("image") or "")
    # QQ 版：投递要发图片 / 文本（网络调用），放后台线程执行，
    # 请求立即返回，避免慢网络把 /api/bridge/result 卡住。
    threading.Thread(
        target=_deliver_result_qq_sync, args=(client, openid, data), daemon=True
    ).start()
    return jsonify(success=True)


def _save_data_url(data_url):
    """把 dataURL 图片保存到本地，返回 {name, path}；失败返回 None。

    存盘实现已抽到公共模块 screenshot_store，与 debug_chrome 的截图工具
    共用同一套命名与目录，避免同一目录下两种格式混杂。
    """
    return screenshot_store.save_data_url(data_url)


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


@bp.route("/api/bridge/help", methods=["GET", "OPTIONS"])
def bridge_help():
    """返回指令说明文本（与 /h 同源），供设置页展示，避免两处手写漂移。"""
    if request.method == "OPTIONS":
        return ("", 204)
    return jsonify(success=True, help=command_panel.help_text())


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
