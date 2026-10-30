"""远程桥接路由：状态查询、配置读写、抽屉上报、结果回传、重启。

- GET  /api/bridge/status   查询桥接状态（设置页展示）
- GET  /api/bridge/config   读取桥接配置
- POST /api/bridge/config   部分更新配置并重启桥接
- POST /api/bridge/report   抽屉上报消息切片，触发推送
- POST /api/bridge/result   抽屉回传指令执行结果，转发到 QQ
"""
import threading
import time

from flask import Blueprint, jsonify, request

import remote_bridge
import screenshot_store
from remote_bridge import bridge, bridge_store, command_panel, message_router
import app_log

bp = Blueprint("bridge", __name__)

# 各会话「推送处理中」标记：QQ 推送是重活（合成 + 逐条发送），放后台线程跑，
# 请求立即返回，避免堆积切片把请求线程拖死。同一会话若上一轮还在跑，
# 本轮直接跳过——抽屉在生成完成、工具执行完成等时机会重复上报全量切片，
# 跳过只影响本次，下次上报会带上最新全量，不会丢消息，天然形成背压。
_report_busy = {}
_report_lock = threading.Lock()

# 上报处理超时（秒）：后台推送线程若卡死（如本地语音合成无响应），
# 「处理中」标记会永远不释放，此后每一轮上报都被静默跳过，
# 表现为「消息生成了却一条也收不到，重启才恢复」。
# 超过此时长即视为卡死，允许新一轮接管，并记录告警。
_REPORT_BUSY_TIMEOUT = 120


def _run_report_async(data, token):
    """把 QQ 推送放到后台线程执行，完成后清除该会话的「处理中」标记。

    @param data  上报体
    @param token 本轮标记的时间戳，用于确认清除的是自己这一轮
    """
    conv = data.get("conversationId") or "__default__"

    def worker():
        try:
            bridge.report(data)
        except Exception as e:
            app_log.warn("[bridge]", "后台推送失败：", e)
        finally:
            with _report_lock:
                # 仅当标记仍属于本轮时才清除：
                # 本轮若已超时并被新一轮接管，不能误删新标记。
                if _report_busy.get(conv) == token:
                    _report_busy.pop(conv, None)

    threading.Thread(target=worker, daemon=True).start()


@bp.route("/api/bridge/status", methods=["GET", "OPTIONS"])
def bridge_status():
    """返回桥接运行状态，供设置页指示灯与窗口信息展示。"""
    return jsonify(success=True, **bridge.status())


@bp.route("/api/bridge/config", methods=["GET", "POST", "OPTIONS"])
def bridge_config():
    """读取或部分更新桥接配置。

    POST 后自动重启桥接：凭证 / 开关变化需要重建长连接。
    """
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        cfg = bridge_store.save_config(data)
        # 配置变更后重启：app_id / app_secret / enabled 变了需要重建连接
        try:
            remote_bridge.bridge.restart()
        except Exception as e:
            app_log.warn("[bridge]", "重启失败：", e)
        return jsonify(success=True, config=cfg, status=bridge.status())
    # GET：返回配置（含凭证，供设置页回填）
    cfg = bridge_store.get_config()
    return jsonify(success=True, config=cfg, status=bridge.status())


@bp.route("/api/bridge/voices", methods=["GET", "OPTIONS"])
def bridge_voices():
    """列出某引擎可选音色，供设置页下拉选择。

    查询参数 engine 缺省时取当前配置实际生效的引擎（auto 取 fallback 首个）。
    三类引擎音色来源不同：系统语音读注册表、Piper 读本地模型文件、
    edge-tts 取内置清单，故由 voice_voices 统一封装。
    """
    from remote_bridge import voice_voices
    engine = (request.args.get("engine") or "").strip() or None
    try:
        data = voice_voices.list_voices(engine)
    except Exception as e:
        app_log.warn("[bridge]", "列举音色失败：", e)
        return jsonify(success=False, error=str(e), engine=engine or "", voices=[], current="")
    return jsonify(success=True, **data)


@bp.route("/api/bridge/report", methods=["POST", "OPTIONS"])
def bridge_report():
    """接收抽屉上报的消息切片，分类去重后推送到 QQ。

    请求体：{ conversationId, messages:[{id, role, blocks}], openid }
    注意：messages 是全量可见切片，桥接层自行与已推送集合比对取差集。
    """
    data = request.get_json(force=True, silent=True) or {}
    # 网页版镜像：无论 QQ 是否在线，都把这次切片存一份进网页收件箱，
    # 让手机网页能拉到 AI 回复。失败不影响 QQ 推送。
    try:
        from web_bridge import web_mirror
        web_mirror.mirror_report(data.get("messages") or [])
    except Exception as e:
        app_log.warn("[web]", "镜像上报失败：", e)
    # QQ 推送放后台线程执行，请求立即返回：合成 + 逐条发送是重活，
    # 若在请求线程里同步跑，堆积切片会把接口拖死。
    # 同一会话上一轮仍在处理则跳过——抽屉会重报全量切片，跳过不丢消息，
    # 同时天然形成背压，避免线程无限堆积。
    conv = data.get("conversationId") or "__default__"
    now = time.time()
    token = now
    with _report_lock:
        started = _report_busy.get(conv)
        if started is not None:
            # 上一轮仍在跑且未超时：跳过本次（抽屉会重复上报全量，不丢消息）
            if now - started < _REPORT_BUSY_TIMEOUT:
                # 跳过必须留痕：此处静默返回会让「上报进了但什么都没发生」
                # 完全查不到，是排查时最容易误判成「前端没上报」的盲区。
                app_log.warn("[bridge]", "上报跳过（上一轮已跑 %.0f 秒）会话 %s"
                             % (now - started, conv))
                return jsonify(success=True, pushed=0, skipped=True)
            # 超时：判定上一轮卡死，强制接管并告警，否则该会话永久静默
            app_log.warn("[bridge]", "上报处理超时 %.0f 秒，强制接管会话 %s"
                         % (now - started, conv))
        _report_busy[conv] = token
    _run_report_async(data, token)
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
# 微信用户标识的后缀。iLink 下发的用户 id 形如 xxx@im.wechat，
# 据此把微信回传与 QQ 回传区分开——两者的投递通道完全不同。
_WEIXIN_SUFFIX = "@im.wechat"


def _is_weixin_openid(openid):
    """判断某个 openid 是否属于微信用户。

    为什么要判：回传接口原先是按 QQ 写的，微信用户的 id 不等于 web-user，
    于是被当成 QQ 用户走了 QQ 的被动回复窗口检查。而微信 openid 在 QQ 的
    窗口表里根本不存在，next_seq 返回空、发送被静默跳过——
    表现为「截图执行了、抽屉回传了、手机上却什么也没收到」。

    @param openid 用户标识
    @returns 属于微信返回 True
    """
    return bool(openid) and str(openid).endswith(_WEIXIN_SUFFIX)


def _is_wecom_openid(openid):
    """判断某个 openid 是否属于企业微信用户。

    企业微信单聊的用户 id 没有固定后缀（形如 NenHanSuoMengYinChunLeng），
    无法像微信那样靠后缀识别。这里用「是否出现在企业微信会话表里」判断：
    该表在收到每条消息时登记，是权威来源。

    @param openid 用户标识
    @returns 属于企业微信返回 True
    """
    if not openid or str(openid) in (_WEB_OPENID,):
        return False
    try:
        from remote_bridge import wecom_router
        return str(openid) in (wecom_router._load_chats() or {})
    except Exception:
        return False


def _take_result_context(data):
    """取出待回传请求，并确定回传去向。

    返回 (client, openid, err_resp)：出错时 err_resp 为响应，成功时为 None。
    - 网页版（openid == web-user）：不依赖 QQ 连接，client 返回 None，走收件箱；
    - 微信版：client 返回微信客户端，由调用方走微信投递路径；
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
    # 微信版：用自己的客户端投递，绝不能走 QQ 的窗口检查（见 _is_weixin_openid）
    if _is_weixin_openid(openid):
        if not bridge.wx_client:
            return None, "", jsonify(success=False, error="weixin_offline")
        return bridge.wx_client, openid, None
    # 企业微信版：单聊的 openid 是纯用户 id（无 @im.wechat 后缀），
    # 只能按「是否属于企业微信通道」判断，不能靠后缀。
    # 若漏掉这一支，会掉进下面的 QQ 分支、走窗口检查而静默失败。
    if _is_wecom_openid(openid):
        if not bridge.wecom_client:
            return None, "", jsonify(success=False, error="wecom_offline")
        return bridge.wecom_client, openid, None
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


def _deliver_result_weixin(client, openid, data):
    """把微信版回传结果投递出去（在后台线程执行）。

    与 QQ 版的差别：微信暂不支持发送图片，故截图类结果转成文字说明，
    并给出本地保存路径，让用户至少知道图存在哪、能自己去取。
    这是诚实降级：与其静默丢弃，不如说清「图已存，路径在此」。

    @param client  微信客户端
    @param openid  接收方
    @param data    回传体 {text, image}
    """
    text = data.get("text") or ""
    image = data.get("image") or ""
    if image:
        saved = _save_data_url(image)
        path = (saved or {}).get("path") or ""
        if path:
            note = "截图已保存：%s" % path
        else:
            note = "截图已收到，但保存失败"
        # 有文字就一并带上，否则只发截图说明
        text = (text + "\n" + note) if text else note
    if not text:
        return
    ok, err = client.send_text(openid, text)
    if not ok:
        app_log.warn("[bridge]", "微信回传结果发送失败：", err)


@bp.route("/api/bridge/result", methods=["POST", "OPTIONS"])
def bridge_result():
    """接收抽屉回传的指令执行结果，按来源转发到 QQ / 微信 / 网页收件箱。

    用于 /sessions、/screenshot 这类「浏览器执行后要回传结果」的指令。
    请求体：{ request_id, text, image }
    """
    data = request.get_json(force=True, silent=True) or {}
    client, openid, err = _take_result_context(data)
    if err is not None:
        return err
    # 网页版：结果落本地收件箱，快且不涉网络，同步完成即可。
    if openid == _WEB_OPENID:
        return _deliver_result_web(data.get("text") or "", data.get("image") or "")
    # 微信版：投递同样可能走网络，放后台线程；截图转文字说明。
    if _is_weixin_openid(openid):
        threading.Thread(
            target=_deliver_result_weixin, args=(client, openid, data), daemon=True
        ).start()
        return jsonify(success=True)
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
    """返回指令说明，供设置页展示。

    同时返回两份数据：
      help   —— 纯文本（与 /h 同源），保留给既有的文本展示场景；
      groups —— 结构化分组（组名 + 每条指令的快捷键/描述），
                供前端渲染成可点击的按钮，用户点一下就执行，便于测试。
    """
    from remote_bridge import command_registry
    return jsonify(success=True,
                   help=command_panel.help_text(),
                   groups=command_registry.builtin_groups())


@bp.route("/api/bridge/run-command", methods=["POST", "OPTIONS"])
def bridge_run_command():
    """由抽屉直接执行一条指令（供设置页的指令按钮调用）。

    与 QQ 里敲指令走完全相同的处理链路（handle_command），
    区别只在于 openid 用网页标识：回执落网页收件箱，不发 QQ。
    这样按钮点下去的行为与真实指令一致，便于用户逐条测试。
    请求体：{ text: "/sd" }
    """
    from remote_bridge import command_panel
    data = request.get_json(force=True, silent=True) or {}
    text = str(data.get("text") or "").strip()
    # 空指令或不是以 / 开头：不当作指令处理
    if not text or not text.startswith("/"):
        return jsonify(success=False, error="not_a_command")
    try:
        # qq_client 传 None：网页标识的回执走网页出口，不会用到它
        handled = command_panel.handle_command(None, "web-user", "", text)
    except Exception as e:
        app_log.warn("[bridge]", "执行指令失败：", e)
        return jsonify(success=False, error=str(e))
    return jsonify(success=True, handled=bool(handled))


@bp.route("/api/bridge/command_params", methods=["GET", "OPTIONS"])
def bridge_command_params():
    """返回内置指令的参数声明列表，供设置页渲染通用「内置指令参数」区块。

    声明来自 command_registry.BUILTIN_PARAMS，与具体指令解耦：
    前端不写死任何指令名，新增带参数的内置指令时后端登记一行即可。
    @returns { success, defs: [ {cmd, key, label, placeholder, hint} ] }
    """
    from remote_bridge import command_registry
    return jsonify(success=True, defs=command_registry.builtin_param_defs())


@bp.route("/api/bridge/commands", methods=["GET", "POST", "DELETE", "OPTIONS"])
def bridge_commands():
    """指令的增删改：独立接口，避免与 saveBridge 的全量覆盖互相干扰。

    - GET            ：列出全部指令
    - POST {index?, entry}：index 为 null 时新增，否则修改该下标
    - DELETE {index} ：删除该下标
    """
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
    ok = bridge.restart()
    return jsonify(success=bool(ok), status=bridge.status())
