"""远程桥接 —— QQ 事件分发

职责：
1. 接收 QQClient 回调的事件，只处理单聊消息 C2C_MESSAGE_CREATE
2. 以「/」开头的消息交给指令处理
3. 其余消息：刷新被动回复窗口，并包装成 external-call 卡片投给卡片总线，
   由抽屉轮询取走、发送进网页 AI

包装成卡片后，网页 AI 看到的只是一条普通外部卡片，感知不到 QQ 的存在。
"""
import time

import card_bus

from . import message_router, bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][gateway]", *args)


# 事件解析与下载辅助已抽到 qq_event_parse；此处按原名引入，保持本文件调用不变。
from .qq_event_parse import (  # noqa: E402
    EVENT_C2C_MESSAGE, to_data_url as _to_data_url, extract as _extract,
    extract_voice as _extract_voice, extract_image as _extract_image,
    download_file as _download_file, dump_raw_event as _dump_raw_event,
)


class QqGateway:
    """QQ 事件分发器：把 QQ 消息变成卡片，把指令交给指令处理器。"""

    def __init__(self, on_command=None):
        """
        @param on_command 指令回调，签名 (qq_client, openid, msg_id, text) -> bool
        """
        self.qq_client = None        # 由 RemoteBridge 在启动后注入
        self.on_command = on_command

    def handle_event(self, event_type, data):
        """QQClient 的事件回调入口。"""
        if event_type != EVENT_C2C_MESSAGE:
            return
        # 调试用：把收到的原始事件原样落盘，供核对语音消息的真实字段结构。
        # 只保留最近若干条，避免无限增长；正式排查完可移除本调用。
        _dump_raw_event(data)
        openid, content, msg_id = _extract(data)
        if not openid:
            log("事件缺少 openid，忽略")
            return

        # 用户发消息即续期：刷新被动回复窗口。
        # 语音也在此续期——识别后要把文字回发，需要窗口开着。
        if msg_id:
            message_router.note_incoming(openid, msg_id)

        # 语音消息：正文 content 通常为空，音频在 attachments 里。
        # 先于「content 判空」处理，否则语音会被当成空消息丢掉。
        voice_url = _extract_voice(data)
        if voice_url:
            self._handle_voice(openid, voice_url, msg_id)
            return

        # 图片消息：正文 content 通常为空，图片在 attachments 里。
        # 同样先于「content 判空」处理，否则图片会被当成空消息丢掉。
        # 同一条消息若既有图又有文字（图文消息），把 content 一并带上，
        # 由图片卡片统一承载，避免文字被这个提前 return 丢掉。
        image_url = _extract_image(data)
        if image_url:
            self._handle_image(openid, image_url, msg_id, content or "")
            return

        if not content:
            log("事件缺少 content 且非语音/图片，忽略")
            return
        log("收到单聊消息", "openid=" + openid[:8], "长度=" + str(len(content)))

        # 指令：以「/」开头，交给指令处理器
        if content.startswith("/"):
            handled = bool(self.on_command
                           and self.on_command(self.qq_client, openid, msg_id, content))
            if not handled:
                # 指令通道与聊天通道彻底分离：以 / 开头却无人认领的命令，
                # 只回机器人一句提示，绝不当作普通消息投给网页 AI。
                self._reply_unknown(openid, content)
            return

        # 普通消息：包装成外部卡片，投给卡片总线
        self._deliver_as_card(openid, content, msg_id)

    def _handle_voice(self, openid, voice_url, msg_id):
        """处理一条语音消息：开关关则丢；开则下载→ASR→暂存→回发等 /vo。

        全程不经过 AI：识别出的文字只回发给机器人，等用户 /vo 确认后
        才由指令处理器转投网页 AI。
        """
        from . import bridge_store
        # 开关：语音识别未打开时，收到语音文件直接丢弃（按用户要求）
        push = bridge_store.get_config().get("push") or {}
        if not push.get("voice"):
            log("语音识别开关未开，丢弃语音消息")
            return

        # 后台线程处理：下载与识别都可能耗时，不能阻塞 WebSocket 回调线程
        import threading
        threading.Thread(target=self._voice_worker,
                         args=(openid, voice_url, msg_id), daemon=True).start()

    def _voice_worker(self, openid, voice_url, msg_id):
        """语音消息的后台处理：下载 → 识别 → 暂存 → 回发等 /vo 确认。

        在独立线程内执行，避免耗时的下载与识别阻塞 WebSocket 回调线程。
        @param openid    用户
        @param voice_url 语音文件地址
        @param msg_id    消息 id
        """
        from . import voice_pending
        text = self._download_and_recognize(openid, voice_url)
        if not text:
            return
        # 暂存待确认（不排队，新的覆盖旧的）
        voice_pending.stash(openid, text, msg_id)
        log("识别成功，已暂存待 /vo 确认：", text)

    def _download_and_recognize(self, openid, voice_url):
        """下载语音并识别为文字；失败时已回发提示并返回空串。

        @param openid    用户
        @param voice_url 语音文件地址
        @returns 识别文本；失败空串
        """
        import os
        import paths
        from . import voice_asr
        os.makedirs(paths.VOICE_DIR, exist_ok=True)
        silk_path = str(paths.VOICE_DIR / ("in_" + str(int(time.time() * 1000)) + ".silk"))
        if not _download_file(voice_url, silk_path):
            self._reply_voice(openid, "语音文件下载失败")
            return ""
        log("开始识别语音", "openid=" + openid[:8])
        text, err = voice_asr.voice_file_to_text(silk_path)
        # 源文件用完即删，不留垃圾
        try:
            os.remove(silk_path)
        except OSError:
            pass
        if err:
            log("语音识别失败：", err)
            self._reply_voice(openid, "语音识别失败：" + err)
            return ""
        if not text:
            log("语音里没识别出文字")
            self._reply_voice(openid, "语音里没识别出文字")
            return ""
        return text
        # 4) 回发识别结果，等用户 /vo 确认
        self._reply_voice(openid, "识别到语音：\n" + text + "\n\n发送 /vo 确认转给 AI，不确认则忽略")

    def _handle_image(self, openid, image_url, msg_id, text=""):
        """处理一条图片消息：下载存本地，并投一张卡片让镜像扩展贴进网页 AI。

        复用截图的逆向流程：图片转 dataURL 放进卡片，扩展取到后
        调 auto_send_image 贴进网页 AI 输入框。
        图片本身也落盘到 QQ_IMAGES_DIR，满足「存储下来」的要求。
        图文消息：同一条消息的文字随图片一起放进卡片，由扩展贴图后
        再把文字粘进同一输入框、一次回车，保证「图文合成一条消息」。
        纯图片（无文字）时补一句「用户截图」，给 AI 一点上下文。
        @param text 同一条消息附带的文字（图文消息）；为空表示纯图片
        """
        import threading
        threading.Thread(target=self._image_worker,
                         args=(openid, image_url, text), daemon=True).start()

    def _image_worker(self, openid, image_url, text):
        """图片消息的后台处理：下载存本地 → 转 dataURL → 投卡片供扩展贴图。

        在独立线程内执行，避免耗时的下载阻塞 WebSocket 回调线程。
        @param openid    用户
        @param image_url 图片地址
        @param text      同消息附带的文字（图文消息）；空表示纯图片
        """
        img_path, ext = self._download_image(openid, image_url)
        if not img_path:
            return
        data_url = _to_data_url(img_path, ext)
        if not data_url:
            return
        self._deliver_image_card(openid, img_path, data_url, text)

    def _download_image(self, openid, image_url):
        """下载图片到本地，返回 (路径, 扩展名)；失败返回 (None, '')。"""
        import os
        import paths
        os.makedirs(str(paths.QQ_IMAGES_DIR), exist_ok=True)
        ts = str(int(time.time() * 1000))
        low = image_url.lower()
        ext = ".png"
        for e in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            if low.endswith(e):
                ext = e
                break
        img_path = str(paths.QQ_IMAGES_DIR / ("in_" + ts + ext))
        if not _download_file(image_url, img_path):
            self._reply_voice(openid, "图片下载失败")
            return None, ""
        return img_path, ext

    def _deliver_image_card(self, openid, img_path, data_url, text):
        """投一张 qq-image 卡片，供前端识别并贴图（不下发网页 AI）。"""
        try:
            card = card_bus.bus.create(
                source="qq",
                card_type="qq-image",
                title="QQ 图片",
                content="（QQ 图片，自动贴入网页 AI 输入框）",
                payload={"kind": "qq-image", "data_url": data_url,
                         "openid": openid, "path": img_path,
                         # 图文消息：带上同消息文字；纯图片则补「用户截图」
                         "text": (text or "").strip() or "用户截图"},
            )
            log("已投递图片卡片", card.id[:8], "等待抽屉取走")
        except Exception as e:
            log("投递图片卡片失败：", e)

    def _reply_voice(self, openid, text):
        """向 QQ 回发一条提示文本（复用被动回复窗口）。"""
        client = self.qq_client
        if not client:
            log("QQ 客户端未就绪，无法回发语音提示")
            return
        msg_id, seq = message_router.next_seq(openid)
        if not msg_id:
            log("窗口已关闭，无法回发语音提示")
            return
        ok, data = client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq)
        if not ok:
            log("回发语音提示失败：", data)

    def _reply_unknown(self, openid, content):
        """未知指令：只回机器人一句提示，绝不投给网页 AI。

        指令通道与聊天通道分离的守门人：以 / 开头却没被任何处理器认领，
        说明用户在试图控制插件、但命令名写错或该指令不存在。此时应当
        告诉他指令无效，而不是把这条控制意图当聊天内容转给 AI。
        """
        client = self.qq_client
        if not client:
            log("QQ 客户端未就绪，无法回复未知指令")
            return
        cmd = str(content).strip().split(None, 1)[0]
        text = "未知指令：%s\n发送 /help 查看可用指令" % cmd
        msg_id, seq = message_router.next_seq(openid)
        if not msg_id:
            log("窗口已关闭，无法回复未知指令")
            return
        ok, data = client.send_c2c(openid, text, msg_id=msg_id, msg_seq=seq)
        if not ok:
            log("回复未知指令失败：", data)

    def _deliver_as_card(self, openid, content, msg_id):
        """把 QQ 消息包装成 external-call 卡片，登记到卡片总线。

        卡片内容里带上来源标记，供推送侧去重（不回推用户自己发的话）。
        """
        self.deliver_text_as_card(openid, content, msg_id)

    def deliver_text_as_card(self, openid, content, msg_id, title="QQ 用户", from_voice=False):
        """把一段文本包装成 external-call 卡片投给网页 AI（公开方法）。

        /vo 确认语音文字后也复用它：把识别出的文字以普通文本卡片格式
        投给 AI，与用户手打一条 QQ 消息的路径完全一致。
        @param openid     用户标识
        @param content    要投递给 AI 的文本
        @param msg_id     被动回复引用的用户消息 id
        @param title      卡片标题（语音确认场景标「语音」）
        @param from_voice 是否由语音确认投递：前端据此要求在随后 AI 回复里
                          必须含 voice 代码块（供 TTS 朗读）
        """
        request_text = _voice_request(content) if from_voice else content
        payload = _external_payload(openid, request_text, msg_id, from_voice)
        try:
            import json
            card = card_bus.bus.create(
                source="qq",
                card_type="external-call",
                title=title,
                content=json.dumps(payload, ensure_ascii=False, indent=2),
                payload={"source": "qq", "openid": openid, "msg_id": msg_id,
                         "from_voice": bool(from_voice)},
            )
            log("已投递卡片", card.id[:8], "等待抽屉取走")
        except Exception as e:
            log("投递卡片失败：", e)


def _voice_request(content):
    """为语音确认卡片组装请求文本：在正文前附一段针对性提示。

    只靠 System Prompt 的通用约定，AI 容易漏 voice 块；把提醒贴进这次的具体
    请求里，命中率更高。
    @param content 语音转出的文字
    @returns 拼好提示的请求文本
    """
    return (
        "【本卡片来自 QQ 语音机器人】这是一段语音转成的文字。"
        "请针对它作答，并在回复中务必另用一个代码块，块内为 JSON："
        '{"type":"bridge-voice","text":"适合朗读的纯口语文本"}，'
        "供系统合成语音发回用户。\n\n语音内容：\n" + content
    )


def _external_payload(openid, request_text, msg_id, from_voice):
    """组装外部调用卡片的信封载荷。

    @param openid       用户标识
    @param request_text 请求正文
    @param msg_id       被动回复引用的用户消息 id
    @param from_voice   是否由语音确认投递
    @returns 信封字典
    """
    return {
        "type": "external-call",
        "nonce": "qq-" + str(int(time.time() * 1000)),
        "request": request_text,
        "source": "qq",
        "openid": openid,
        "msg_id": msg_id,
        "from_voice": bool(from_voice),   # 语音确认标记，前端据此要求 voice 块
        "page_url": "",          # 不指定目标页面，谁打开着抽屉谁取走
    }
