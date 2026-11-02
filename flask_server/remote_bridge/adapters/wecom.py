"""远程桥接 —— 企业微信通道适配器

企业微信与另两条通道的差异：

    1. 主动推送无配额压力 —— 但仍合并文本，避免手机被短消息刷屏
    2. 图片 / 文件 / 语音能真正发出去 —— 这是换用企微的核心理由
    3. 媒体与文本走不同接口，且回复凭证 req_id 一次只能用一条

关于发送顺序的代价（须如实记录）：
    原实现的顺序是「媒体先发 → 文本最后」，原因是 req_id 只能回复一条消息，
    文本若先把它用掉，后续图片就只能降级为主动推送。
    本适配器由公共管线驱动，顺序是「文本先发 → 媒体随后」，故同一批里
    媒体的第一条往往拿不到 req_id，走主动推送接口。
    功能上不丢消息（主动推送同样能送达），代价是客户端转圈时间略长。
    若要恢复原顺序，需在管线里为企微开「媒体优先」分支。
"""
from ..channel.adapter import ChannelAdapter
from ..channel import dedupe as dedupe_store
from ..channel import quota as quota_store
from ..channel import target as target_store

# 合并多条消息时的分隔线
SEP = "\n\n———\n\n"

# 各类消息的展示前缀
PREFIX = {"user": "👤 用户", "tool": "🛠 工具", "ai": "🤖 AI"}

# 单条消息最多发送的字符数
MAX_TEXT_CHARS = 3500


def _truncate(text):
    """按上限截断文本，保留首尾。

    @param text 原文本
    @returns 截断后的文本
    """
    if len(text) <= MAX_TEXT_CHARS:
        return text
    head = MAX_TEXT_CHARS * 2 // 3
    tail = MAX_TEXT_CHARS - head - 20
    return text[:head] + "\n\n…（中间省略）…\n\n" + text[-tail:]


class WecomAdapter(ChannelAdapter):
    """企业微信通道适配器。"""

    def __init__(self, client=None):
        """构造适配器。

        @param client WecomClient 实例；可后置注入
        """
        super().__init__("wecom", dedupe_store.wecom, quota_store.wecom)
        self.client = client
        # 最近会话的 chat_type：单聊 1 / 群聊 2，随 target 一起记
        self._chat_type = {}

    def send_text(self, target, text, markdown=False):
        """发送文本：优先走回复凭证（客户端停止转圈），否则主动推送。

        @param target   会话 id
        @param text     正文
        @param markdown 是否按 Markdown 发送
        @returns (是否成功, 平台返回)
        """
        if not self.client:
            return False, "NO_CLIENT"
        chat_type = self._chat_type.get(target, 1)
        # 有凭证走回复：客户端那边会立即停止转圈
        from .. import wecom_router
        req_id = wecom_router.take_req_id(target)
        if req_id:
            return self.client.respond_to(req_id, target, text, chat_type)
        return self.client.send_markdown(target, text, chat_type)

    def resolve_target(self, payload):
        """确定收件人：优先上报体里的企微会话，回退最近活跃会话。

        顺手记下 chat_type：发消息时要用它区分单聊与群聊。
        @param payload 上报体
        @returns 会话 id；无从确定返回空串
        """
        cid = payload.get("wecom_chatid") or ""
        if cid:
            ct = int(payload.get("wecom_chat_type") or 1)
            self._chat_type[cid] = ct
            return cid
        from .. import wecom_router
        cid, ct = wecom_router.last_chat()
        if cid:
            self._chat_type[cid] = ct
        return cid

    def merge_batch(self, items, push):
        """把一批消息合并成一条文本。

        企微无配额压力，但逐条推会在手机上刷出很多条，故仍合并。
        @param items 本轮待推消息
        @param push  推送开关
        @returns 合并后的文本；全部不可推时返回空串
        """
        bodies = []
        for m in items:
            body = self._body_of(m, push)
            if body:
                bodies.append(body)
        if not bodies:
            return ""
        return _truncate(SEP.join(bodies))

    def push_media(self, recipient, items, push, ctx):
        """发送这批消息里的图片、文件、语音，返回成功条数。

        媒体不能并进合并文本：那样就变成一段路径文字，用户看不到内容。
        @param recipient 会话 id
        @param items     本轮待推消息
        @param push      推送开关
        @param ctx       锁外预处理结果（含预合成的语音映射）
        @returns 成功发送的媒体条数
        """
        if not self.client:
            return 0
        from ..wecom_media_collect import collect_images, collect_files, collect_voice
        chat_type = self._chat_type.get(recipient, 1)
        voice_map = (ctx or {}).get("voice_map") or {}
        images, files, voices = [], [], []
        for m in items:
            images.extend(collect_images(m))
            files.extend(collect_files(m))
            # 语音只在 AI 消息上推：用户与工具消息没有朗读文本
            if push.get("voice"):
                vpath, vtext = collect_voice(m, voice_map)
                if vpath and vtext:
                    from ..message_parse import _classify
                    if _classify(m) == "ai":
                        voices.append(vpath)
        sent = 0
        # 三类媒体共用同一个发送骨架：取凭证 → 有则回复、无则主动推送
        for path in images:
            sent += self._send_media(recipient, chat_type, path, "image")
        for path in files:
            sent += self._send_media(recipient, chat_type, path, "file")
        for path in voices:
            sent += self._send_media(recipient, chat_type, path, "voice")
        return sent

    def _send_media(self, recipient, chat_type, path, kind):
        """发一件媒体：优先用回复凭证，没有则主动推送。

        @param recipient 会话 id
        @param chat_type 1 单聊 / 2 群聊
        @param path      本地文件路径
        @param kind      image / file / voice
        @returns 成功返回 1，失败返回 0
        """
        from .. import wecom_router
        req_id = wecom_router.take_req_id(recipient)
        # 按媒体类型选对应接口：回复接口与主动推送接口各有一套
        if req_id:
            fn = getattr(self.client, "respond_" + kind, None)
            if fn:
                ok, _ = fn(req_id, recipient, path, chat_type)
                return 1 if ok else 0
        fn = getattr(self.client, "send_" + kind, None)
        if not fn:
            return 0
        ok, _ = fn(recipient, path, chat_type)
        return 1 if ok else 0

    def before_push(self, recipient, conv_id, items, push):
        """锁外预处理：预合成语音。

        合成是网络调用、一条要一秒以上，放锁内会让该会话长时间占锁。
        @returns 上下文，透传给 push_media
        """
        from .. import message_flow
        return {"voice_map": message_flow.synth_pending(items, push, {})}

    def _body_of(self, m, push):
        """取一条消息的待推正文（含类型前缀）；不可推返回空串。

        @param m    消息对象
        @param push 推送开关
        @returns 正文
        """
        if not self._should_push(m, push):
            return ""
        text = self._extract_text(m, push)
        if not text:
            return ""
        from ..message_parse import _classify
        kind = _classify(m)
        return "%s\n%s" % (PREFIX.get(kind, kind), text)

    def _should_push(self, m, push):
        """判断一条消息是否应当推送：类型开关打开，且不是企微自己发的。

        @param m    消息对象
        @param push 推送开关
        @returns 该推返回 True
        """
        from ..message_parse import _classify
        if not push.get(_classify(m), True):
            return False
        return not self.is_own_source(m)

    def is_own_source(self, m):
        """判断消息是否由企微通道自己投递。

        @param m 消息对象
        @returns 来自企微返回 True
        """
        from ..message_parse import _parse_envelope
        obj = _parse_envelope(m)
        return bool(obj and obj.get("source") == "wecom")

    def _extract_text(self, m, push):
        """提取正文：剔除工具调用与工具结果块。

        与微信同理：工具调用的 JSON 参数在手机上是噪音。
        @param m    消息对象
        @param push 推送开关
        @returns 正文文本
        """
        from ..message_parse import _BLOCK_HANDLERS, _load_json_block
        parts = []
        for b in (m.get("blocks") or []):
            if not b:
                continue
            btype = b.get("type")
            if btype == "code":
                obj = _load_json_block(b)
                if obj and obj.get("type") in (
                        "bridge-chat-call", "bridge-chat-res", "bridge-voice"):
                    continue
                code = str(b.get("code") or "").strip()
                if code:
                    parts.append("```\n" + code + "\n```")
                continue
            fn = _BLOCK_HANDLERS.get(btype)
            if not fn:
                continue
            text = fn(b, bool(push.get("thinking")))
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    def record_incoming(self, chatid, chat_type=1, user="", req_id=""):
        """收到用户消息：登记会话、记下 chat_type、保留回复凭证。

        @param chatid    会话 id
        @param chat_type 1 单聊 / 2 群聊
        @param user      发送者
        @param req_id    本条消息的请求 id
        """
        target_store.wecom.note(chatid)
        self._chat_type[chatid] = int(chat_type or 1)
        from .. import wecom_router
        wecom_router.note_chat(chatid, chat_type, user, req_id)
