"""远程桥接 —— 指令回传结果的投递实现

从 routes/bridge.py 抽出，使路由文件保持在行数上限内。

职责：把抽屉回传的指令结果（文本 / 截图）投递到对应通道。
路由层只负责判定「该投给哪条通道」，投递细节全在本模块。

四条去向：
  web      —— 落网页收件箱，由前端拉取展示
  qq       —— 走被动回复窗口，窗口关闭时回退成文字说明
  weixin   —— 暂不支持发图，截图转为文字说明 + 本地路径
  wecom    —— 无回复窗口，一律主动推送

为什么投递都在后台线程：发送是网络调用（图片上传 / 文本发送），
放请求线程里会把 /api/bridge/result 拖住。
"""
from flask import jsonify

import app_log
import screenshot_store
from remote_bridge import message_router


def _save_data_url(data_url):
    """把 dataURL 图片保存到本地，返回 {name, path}；失败返回 None。

    存盘实现已抽到公共模块 screenshot_store，与 debug_chrome 的截图工具
    共用同一套命名与目录，避免同一目录下两种格式混杂。

    @param data_url 图片的 dataURL
    @returns 保存结果字典；失败返回 None
    """
    return screenshot_store.save_data_url(data_url)


def _try_send_image(client, openid, image):
    """尝试把 dataURL 截屏发到 QQ。

    成功返回 None；失败返回应回退发送的提示文本（含本地路径），
    让用户至少知道图存在哪，而不是只看到一句「发送失败」。

    @param client QQ 客户端
    @param openid 接收方
    @param image  图片 dataURL
    @returns 失败时的回退文本；成功返回 None
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
    """向 QQ 发送一条文本；窗口已关闭时静默跳过。

    @param client QQ 客户端
    @param openid 接收方
    @param text   正文
    """
    msg_id, seq = message_router.next_seq(openid)
    if msg_id:
        client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq)


def deliver_web(text, image):
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


def deliver_qq(client, openid, data):
    """把 QQ 版回传结果实际投递出去（在后台线程执行，故不构造 HTTP 响应）。

    - 截屏且无文本时优先按图片发送，失败则把错误信息转为文本回退；
    - 无内容可发时直接返回（回传本身已确认接收）。

    @param client QQ 客户端
    @param openid 接收方
    @param data   回传体 {text, image}
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


def deliver_weixin(client, openid, data):
    """把微信版回传结果投递出去（在后台线程执行）。

    微信暂不支持发送图片，故截图类结果转成文字说明，并给出本地保存路径，
    让用户至少知道图存在哪、能自己去取。这是诚实降级：
    与其静默丢弃，不如说清「图已存，路径在此」。

    @param client 微信客户端
    @param openid 接收方
    @param data   回传体 {text, image}
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


def deliver_wecom(client, openid, data):
    """把企业微信版回传结果投递出去（在后台线程执行）。

    企业微信没有被动回复窗口，一律主动推送。截图先落盘，再经 send_image
    上传成素材发出；发送失败时把本地路径转成文字说明回退，
    让用户至少知道图存在哪。

    @param client 企业微信客户端
    @param openid 接收方
    @param data   回传体 {text, image}
    """
    text = data.get("text") or ""
    image = data.get("image") or ""
    if image:
        saved = _save_data_url(image)
        path = (saved or {}).get("path") or ""
        if path:
            # 图片本身能发就发图，文字作为附注不单独再发一条
            ok, err = client.send_image(openid, path)
            if ok:
                return
            app_log.warn("[bridge]", "企业微信回传图片发送失败：", err)
            note = "截图已保存：%s" % path
        else:
            note = "截图已收到，但保存失败"
        text = (text + "\n" + note) if text else note
    if not text:
        return
    ok, err = client.send_markdown(openid, text)
    if not ok:
        app_log.warn("[bridge]", "企业微信回传结果发送失败：", err)
