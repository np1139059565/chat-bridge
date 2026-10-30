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


def sender_of(body):
    """取发送者标识。

    企业微信的回调把发送者放在 body.from.userid 里，不在顶层。
    曾按顶层 userid 取，导致每条消息都因「缺发送者」被丢弃。

    @param body 回调体
    @returns 用户 id；缺失返回空串
    """
    f = body.get("from") or {}
    return f.get("userid") or body.get("userid") or body.get("from_user") or ""


# 会话上下文：chatid / chat_type / req_id 三者在分派链路上总是同时使用，
# 打包成一个不可变对象传递，避免函数参数列表过长（质量门禁限制 6 个）。
_ChatCtx = namedtuple("ChatCtx", ["chatid", "chat_type", "req_id"])


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
        # 记住会话，并带上本条消息的 req_id：
        # 推送时必须用它走 respond 才能让客户端停止转圈（主动推送做不到）。
        req_id = (frame_msg.get("headers") or {}).get("req_id") or ""
        wecom_router.note_chat(chatid, chat_type, user, req_id=req_id)

        text = _text_of(body)
        if not text:
            kind, info = _media_of(body)
            if kind:
                self._handle_media(client, body, chatid, chat_type, kind, info)
                return
            log("消息无可用正文，忽略")
            return
        log("收到消息", "user=" + (user[:8] if user else "?"), "长度=" + str(len(text)))
        ctx = _ChatCtx(chatid, chat_type, req_id)
        self._dispatch_text(client, body, ctx, text)

    def _dispatch_text(self, client, body, ctx, text):
        """分派文本：斜杠走指令，其余投卡片。

        @param ctx 会话上下文（chatid / chat_type / req_id 三者总是一起用，
                   打包传递，避免参数列表过长）

        req_id 必须一路带到推送环节：企业微信客户端只有在收到
        带同一个 req_id 的 aibot_respond_msg 之后才停止转圈，
        用主动推送做不到这一点。
        """
        if text.startswith("/"):
            handled = bool(self.on_command
                           and self.on_command(client, ctx.chatid,
                                               body.get("msg_id") or "", text))
            if not handled:
                client.respond_to(ctx.req_id, ctx.chatid,
                                  "未知指令：%s\n发送 /h 查看可用指令"
                                  % str(text).strip().split(None, 1)[0])
            return
        self._deliver_as_card(body, ctx.chatid, ctx.chat_type, text, ctx.req_id)

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
        url = info.get("url") or info.get("download_url") or ""
        aeskey = info.get("aeskey") or ""
        if not url:
            log("媒体缺少下载地址，忽略")
            return
        import paths
        path = client.download_media(url, aeskey, str(paths.WECOM_MEDIA_DIR))
        if not path:
            log("媒体下载失败")
            return
        log("媒体已落盘：", path)
        text = "【收到%s】本地路径：%s" % (
            {"image": "图片", "file": "文件", "voice": "语音", "video": "视频"}.get(kind, kind),
            path)
        self._deliver_as_card(body, chatid, chat_type, text)

    def _deliver_as_card(self, body, chatid, chat_type, content, req_id=""):
        """把消息包装成 external-call 卡片投给网页 AI。

        req_id 一并放进 payload：推送环节要靠它走 respond 回复，
        否则客户端永远停在「发送中」。
        """
        payload = {
            "type": "external-call",
            "nonce": "wecom-" + str(int(time.time() * 1000)),
            "request": content,
            "source": "wecom",
            "openid": chatid,
            "msg_id": body.get("msg_id") or "",
            "req_id": req_id,
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
