"""远程桥接 —— 企业微信事件分发

职责：
1. 接收 WecomClient 回调的消息，抽出正文（文本 / 图片 / 文件 / 语音）
2. 以「/」开头的消息交给指令处理
3. 其余消息包装成 external-call 卡片投给卡片总线
4. 记住每个会话的 chatid，供主动推送使用

与微信 ClawBot 网关同构，但多一件事：
  企业微信可以主动推送，所以必须持久化 chatid——
  重启后没有 chatid 就再也推不出去了。
"""
import json
import time
from collections import namedtuple

import card_bus

from . import wecom_router, bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][wecom]", *args)


def _text_of(body):
    """从回调体里抽正文。

    企业微信的文本在 body.text.content；图片、文件等只有媒体描述，
    没有正文，返回空串由上层按媒体处理。
    @param body 回调体
    @returns 正文；无则空串
    """
    t = body.get("text") or {}
    if isinstance(t, dict):
        c = t.get("content") or ""
        if c:
            return str(c)
    return ""


def _media_of(body):
    """取出媒体信息（图片 / 文件 / 语音）。

    @param body 回调体
    @returns (类型, 描述字典) 或 ("", {})
    """
    for kind in ("image", "file", "voice", "video"):
        v = body.get(kind)
        if isinstance(v, dict) and v:
            return kind, v
    return "", {}


def _mixed_of(body):
    """取出图文混排消息的子项列表。

    企业微信把「文字 + 图片」放进 mixed.msg_item 数组，顶层 msgtype 为 mixed。
    这类消息既没有顶层 text 也没有顶层 image，按普通文本或媒体判断都会落空，
    表现为「收到了但无可用正文，直接忽略」。

    @param body 回调体
    @returns 子项字典列表；非图文消息返回空列表
    """
    mixed = body.get("mixed")
    if not isinstance(mixed, dict):
        return []
    # 平台字段名为 msg_item；兼容 items 以防不同版本命名差异
    items = mixed.get("msg_item") or mixed.get("items") or []
    return [i for i in items if isinstance(i, dict)]


def sender_of(body):
    """取发送者标识。

    企业微信的回调把发送者放在 body.from.userid 里，不在顶层。
    曾按顶层 userid 取，导致每条消息都因「缺发送者」被丢弃。

    @param body 回调体
    @returns 用户 id；缺失返回空串
    """
    f = body.get("from") or {}
    return f.get("userid") or body.get("userid") or body.get("from_user") or ""


# 会话上下文：chatid 与 chat_type 在分派链路上总是同时使用，
# 打包成一个不可变对象传递，避免函数参数列表过长（质量门禁限制 6 个）。
_ChatCtx = namedtuple("ChatCtx", ["chatid", "chat_type"])


class WecomGateway:
    """企业微信事件分发器。"""

    def __init__(self, on_command=None):
        """
        @param on_command 指令回调，签名 (client, chatid, msg_id, text) -> bool
        """
        self.client = None
        self.on_command = on_command

    def handle_message(self, client, frame_msg):
        """WecomClient 的消息回调入口。

        @param client    WecomClient 实例
        @param frame_msg 完整下行帧
        """
        self.client = client
        body = frame_msg.get("body") or {}
        user = sender_of(body)
        # 单聊消息**没有 chatid 字段**，只有 from.userid；群聊才有 chatid。
        # 曾因「缺 chatid 就忽略」把每一条单聊消息都丢弃了。
        chatid = body.get("chatid") or user
        chat_type = body.get("chat_type") or 1
        if not chatid:
            log("消息缺少 chatid 与 userid，忽略")
            return
        log("收到消息 chatid=" + chatid[:12] + " type=" + str(chat_type))
        # 记住会话：主动推送依赖 chatid 定位收件人
        wecom_router.note_chat(chatid, chat_type, user)
        # 同步登记到公共层：统一推送管线从 channel.target 读「最近会话」。
        # 两处并写，切换前后行为一致；旧链路停用后可只留公共层。
        from .channel import target as target_store
        target_store.wecom.note(chatid)

        # 登记最近活跃渠道为企业微信：用户刚在企业微信侧发了消息（含指令）。
        # 后续上报只推给这个渠道，避免同一条回复同时发到 QQ 与网页。
        import active_channel
        active_channel.note("wecom")

        # 图文混排必须优先处理：平台会在 mixed 消息顶层也带上文字，
        # 若先取 text 判断，会因「有文字」而走文本分支，把同一条里的图片整个丢掉。
        # 用户侧看到的就是「发了图和字，只收到字」。
        if (body.get("msgtype") or "") == "mixed":
            mixed = _mixed_of(body)
            if mixed:
                # 顶层 text 也要带上：平台可能把正文放在顶层而非子项里，
                # 只取子项会漏掉这部分文字。
                self._handle_mixed(client, body, chatid, chat_type, mixed,
                                   _text_of(body))
                return
        text = _text_of(body)
        if not text:
            # 诊断：无正文时打出消息类型与 mixed 的原始结构。
            # 只看 msgtype 看不出子项长什么样，必须打原始值才能定位。
            log("无正文诊断 msgtype=%s mixed=%s"
                % (body.get("msgtype") or "", str(body.get("mixed"))[:600]))
            # 图文混排：文字与图片同处一条消息，需合并成一次投递，
            # 拆成两条会破坏「一条消息里带图文」的通道铁律。
            mixed = _mixed_of(body)
            if mixed:
                self._handle_mixed(client, body, chatid, chat_type, mixed)
                return
            kind, info = _media_of(body)
            if kind:
                self._handle_media(client, body, chatid, chat_type, kind, info)
                return
            # 带 msgtype：未知类型时据此判断平台又新增了什么形态
            log("消息无可用正文，忽略 msgtype=%s" % (body.get("msgtype") or ""))
            return
        log("收到消息", "user=" + (user[:8] if user else "?"), "长度=" + str(len(text)))
        ctx = _ChatCtx(chatid, chat_type)
        self._dispatch_text(client, body, ctx, text)

    def _dispatch_text(self, client, body, ctx, text):
        """分派文本：斜杠走指令，其余投卡片。

        与网页版机器人一致：所有出向消息统一走主动推送，
        不区分「是否在回复窗口内」。企业微信不需要窗口，
        主动推送也没有「一个凭证只能回一条」的限制。

        @param ctx 会话上下文（chatid / chat_type）
        """
        if text.startswith("/"):
            handled = bool(self.on_command
                           and self.on_command(client, ctx.chatid,
                                               body.get("msg_id") or "", text))
            if not handled:
                client.send_markdown(ctx.chatid,
                                     "未知指令：%s\n发送 /h 查看可用指令"
                                     % str(text).strip().split(None, 1)[0],
                                     ctx.chat_type)
            return
        self._deliver_as_card(body, ctx.chatid, ctx.chat_type, text)

    def _handle_mixed(self, client, body, chatid, chat_type, items, top_text=""):
        """处理图文混排消息：文字与图片合并成一次投递。

        顺序：先抽出全部文字拼成正文，再把图片逐张投成图片卡片，
        最后把文字作为一张 external-call 卡片投出去。

        @param client    WecomClient
        @param body      回调体
        @param chatid    会话 id
        @param chat_type 会话类型
        @param items     mixed 子项列表
        @param top_text  顶层正文（平台可能把文字放在顶层而非子项里）
        """
        # 诊断：打出每个子项的类型与键名，判断正文是否真在消息里
        log("mixed 子项：count=%d detail=%s top_text_len=%d"
            % (len(items), [(i.get("msgtype"), sorted(i.keys())) for i in items],
               len(top_text or "")))
        # 顶层文字先入列：它是这条消息的正文，子项里的文字按出现顺序追加
        texts = [top_text] if top_text else []
        images = []
        for it in items:
            mt = it.get("msgtype") or ""
            if mt == "text":
                c = ((it.get("text") or {}).get("content") or "").strip()
                if c:
                    texts.append(c)
            elif mt == "image":
                images.append(it.get("image") or {})
        for info in images:
            if info:
                self._handle_media(client, body, chatid, chat_type, "image", info)
        joined = chr(10).join(texts).strip()
        if joined:
            self._deliver_as_card(body, chatid, chat_type, joined)
            log("图文消息已投递 文字长度=%d 图片数=%d" % (len(joined), len(images)))
        elif not images:
            log("图文消息无可用内容，忽略")

    def _handle_media(self, client, body, chatid, chat_type, kind, info):
        """处理图片 / 文件 / 语音消息。

        下载并解密到本地，再投一张卡片告诉网页 AI「收到一个文件，路径在此」。
        @param client    WecomClient
        @param body      回调体
        @param chatid    会话 id
        @param chat_type 会话类型
        @param kind      媒体类型
        @param info      媒体描述
        """
        # 诊断日志：记录平台下发的媒体字段名与关键取值。
        # 平台字段名可能与文档不一致（曾因 from.userid 取错层级丢光所有消息），
        # 这里把实际收到的键名打出来，避免继续按假设的字段名猜。
        log("媒体字段：kind=%s keys=%s" % (kind, sorted(info.keys())))
        url = info.get("url") or info.get("download_url") or ""
        aeskey = (info.get("aeskey") or info.get("aes_key")
                  or info.get("aeskey_str") or "")
        if not url:
            log("媒体缺少下载地址，忽略")
            return
        import paths
        path = client.download_media(url, aeskey, str(paths.WECOM_MEDIA_DIR))
        if not path:
            log("媒体下载失败")
            return
        log("媒体已落盘：", path)
        # 图片走「贴进网页 AI 输入框」的路径，与 QQ 一致：
        # 只把本地路径当文本投给网页 AI，模型看不到图，等于没收到。
        # 故转成 dataURL 放进图片卡片，由前端贴进输入框。
        if kind == "image":
            self._deliver_image_card(chatid, path)
            return
        # 文件与语音以卡片投递，卡片正文写明本地路径：
        # 与其它通道等价，AI 拿到路径后可自行决定读不读
        if kind in ("file", "voice"):
            self._deliver_media_card(chatid, path, kind, info)
            return
        # 其余类型（视频）暂以文本描述投递
        text = "【收到%s】本地路径：%s" % (
            {"video": "视频"}.get(kind, kind), path)
        self._deliver_as_card(body, chatid, chat_type, text)

    def _deliver_media_card(self, chatid, path, kind, info):
        """把文件或语音投成卡片，卡片正文写明本地路径。

        与图片的区别：文件是二进制，模型看不见也不需要看见，
        它需要的是路径——拿到后自行调 read_file 或让用户下载。

        @param chatid 会话 id
        @param path   本地落盘路径
        @param kind   file / voice
        @param info   平台下发的媒体描述
        """
        import os
        # 文件名优先取平台下发值，缺失时用落盘文件的基本名
        name = info.get("name") or os.path.basename(path)
        # 体积取落盘后的真实大小，平台下发的值可能缺失
        size = os.path.getsize(path) if os.path.exists(path) else 0
        label = "文件" if kind == "file" else "语音"
        # 卡片正文写成一句完整的话，AI 与用户都能直接看懂
        body = "用户从企业微信发来%s：%s（%d 字节），已保存到 %s" % (
            label, name, size, path)
        try:
            card = card_bus.bus.create(
                source="wecom",
                card_type="qq-file",
                title="企业微信" + label,
                content=body,
                payload={"kind": "qq-file", "openid": chatid,
                         "path": path, "name": name, "size": size},
            )
            log("已投递" + label + "卡片", card.id[:8], "等待抽屉取走")
        except Exception as e:
            log("投递" + label + "卡片失败：", e)

    def _deliver_image_card(self, chatid, path):
        """投一张企微图片卡片，供前端贴进网页 AI 输入框。

        与 QQ 的做法一致：把图片转成 dataURL 放进卡片，前端识别后
        直接贴图，模型才真正「看得到」图片内容。只投本地路径的话，
        模型拿到的是一段文字，图片等于没收到。

        @param chatid 会话 id
        @param path   本地图片路径
        """
        import os
        try:
            from .qq_event_parse import to_data_url
        except Exception as e:
            log("图片转 dataURL 不可用：", e)
            return
        ext = os.path.splitext(path)[1].lower()
        data_url = to_data_url(path, ext)
        if not data_url:
            log("图片转 dataURL 失败，退化为路径文本")
            self._deliver_as_card({}, chatid, 1, "【收到图片】本地路径：%s" % path)
            return
        try:
            card = card_bus.bus.create(
                source="wecom",
                card_type="qq-image",
                title="企业微信图片",
                content="（企业微信图片，自动贴入网页 AI 输入框）",
                payload={"kind": "qq-image", "data_url": data_url,
                         "openid": chatid, "path": path,
                         "text": "用户截图"},
            )
            log("已投递图片卡片", card.id[:8], "等待抽屉取走")
        except Exception as e:
            log("投递图片卡片失败：", e)

    def _deliver_as_card(self, body, chatid, chat_type, content):
        """把消息包装成 external-call 卡片投给网页 AI。

        出向回复统一走主动推送，卡片只承载内容本身。
        """
        payload = {
            "type": "external-call",
            "nonce": "wecom-" + str(int(time.time() * 1000)),
            "request": content,
            "source": "wecom",
            "openid": chatid,
            "msg_id": body.get("msg_id") or "",
            "from_voice": False,
            "page_url": "",
        }
        try:
            card = card_bus.bus.create(
                source="wecom",
                card_type="external-call",
                title="企业微信用户",
                content=json.dumps(payload, ensure_ascii=False, indent=2),
                payload={"source": "wecom", "openid": chatid,
                         "msg_id": body.get("msg_id") or ""},
            )
            log("已投递卡片", card.id[:8], "等待抽屉取走")
        except Exception as e:
            log("投递卡片失败：", e)
