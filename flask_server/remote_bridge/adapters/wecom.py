"""远程桥接 —— 企业微信通道适配器

企业微信与另两条通道的差异：

    1. 主动推送无配额压力 —— 但仍合并文本，避免手机被短消息刷屏
    2. 图片 / 文件 / 语音能真正发出去 —— 这是换用企微的核心理由
    3. 媒体与文本走不同接口，媒体在文本之后单独发送

出向消息一律走主动推送：企业微信不依赖被动回复窗口，
主动推送没有「一条凭证只能回一条」的限制，故障时也只有一条通路要查。

关于发送顺序：本适配器由公共管线驱动，顺序是「文本先发 → 媒体随后」。
媒体随后单独发送，因此一批里的多张图片都能依次发出、不会互相挤占。
"""
from ..channel.adapter import ChannelAdapter
from ..channel import dedupe as dedupe_store
from ..channel import quota as quota_store
from ..channel import target as target_store
from ..channel import text as text_store
from .. import bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。

    与另两条通道的适配器保持一致。缺了它，媒体发送失败时调用 log 会抛
    NameError，整个推送流程被异常中断，表现为「管线报成功、用户收不到」。
    """
    bridge_log.write("[bridge][wecom]", *args)

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

    def prepare_items(self, conv_id, items):
        """合并上次推送失败的消息，让它们获得重试机会。

        与 QQ 通道保持一致：失败的消息可能已滚出可见区、不再出现在切片里，
        只能靠待推缓存补回来，否则那条消息永远丢失。
        @param conv_id 会话标识
        @param items   本轮切片消息
        @returns 合并后的消息列表
        """
        from .. import bridge_store
        return bridge_store.merge_pending(conv_id, items)

    def push_one(self, recipient, conv_id, m, push, ctx):
        """推送一条消息：正文与媒体。

        为何不走管线默认实现：默认组装器优先采用网页 Markdown 原文，而原文里
        工具调用是平铺 JSON、思考是裸文本；text_store.body_of 内含判断，块里有
        这两类内容时改走完整组装，把工具收成「只报工具名」的代码块、思考包成
        折叠块。另：逐条分支不发媒体，故此处须显式调用 push_media。
        @param recipient 会话 id
        @param conv_id   会话标识（本方法不使用，去重由管线外层完成）
        @param m         单条消息
        @param push      推送开关
        @param ctx       锁外预处理结果（含预合成的语音映射）
        @returns 'sent' / 'fail'
        """
        text = text_store.body_of(m, push, "wecom", use_md=True)
        if text:
            ok, _err = self.send_text(recipient, text, markdown=True)
            # 正文失败即整条失败：外层会撤回占用、下轮重试
            if not ok:
                return "fail"
        # 媒体失败不影响正文已送达，故不返回 fail（避免正文被重发）
        self.push_media(recipient, [m], push, ctx)
        return "sent"

    def send_text(self, target, text, markdown=False):
        """发送文本：走主动推送。

        @param target   会话 id
        @param text     正文
        @param markdown 是否按 Markdown 发送
        @returns (是否成功, 平台返回)
        """
        if not self.client:
            return False, "NO_CLIENT"
        # 会话类型决定按单聊还是群聊编码
        chat_type = self._chat_type.get(target, 1)
        # 主动推送：不受凭证约束，也不会因凭证过期而失败
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
        from ..channel import wecom_chats
        cid, ct = wecom_chats.last()
        if cid:
            self._chat_type[cid] = ct
        return cid

    def merge_batch(self, items, push):
        """不合并：返回 None，让管线逐条推送。

        为什么从「合并」改为「不合并」：合并会把整批消息拼成一个大字符串，
        拼接过程压平了每条消息自身的结构——工具调用的代码块不再独立、
        平台无从折叠，代码围栏退化为纯文本，且 AI 回复与工具结果被迫融成一条。
        更直接的代价是时延：必须等整批消息收集齐才能拼出完整字符串再发送，
        首字延迟等于整批的收集时间。

        改为逐条后，每条消息由 outbound.build_body 单独组装——该组装器会
        为工具结果包上 json 围栏、把思考内容包进独立折叠块，格式与 QQ 通道一致。

        企业微信主动推送接口没有「每条用户消息仅限 N 条回复」的配额限制，
        逐条发送不会像微信那样迅速耗尽额度。

        @param items 本轮待推消息（本实现不使用）
        @param push  推送开关（本实现不使用）
        @returns 恒为 None，表示不合并
        """
        return None

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
        from ..channel import media as media_store
        chat_type = self._chat_type.get(recipient, 1)
        voice_map = (ctx or {}).get("voice_map") or {}

        def _send_one(path, kind):
            """把一件媒体交给本通道的发送实现。

            @param path 本地文件路径
            @param kind image / file / voice
            @returns 成功返回 True
            """
            return bool(self._send_media(recipient, chat_type, path, kind))

        # 收集与计数的骨架在公共层，本通道只提供「怎么发」
        return media_store.push_collected(items, push, voice_map, _send_one)

    def _send_media(self, recipient, chat_type, path, kind):
        """发一件媒体：走主动推送。

        @param recipient 会话 id
        @param chat_type 1 单聊 / 2 群聊
        @param path      本地文件路径
        @param kind      image / file / voice
        @returns 成功返回 1，失败返回 0
        """
        # 主动推送：不受凭证约束，多张图能依次发出
        fn = getattr(self.client, "send_" + kind, None)
        if not fn:
            log("媒体类型不支持主动推送 kind=%s" % kind)
            return 0
        ok, err = fn(recipient, path, chat_type)
        if not ok:
            log("媒体推送失败 kind=%s err=%s" % (kind, err))
        return 1 if ok else 0

    def before_push(self, recipient, conv_id, items, push):
        """锁外预处理：只查语音缓存，不做合成。

        与 QQ 通道保持一致：合成一条要一秒以上，放在推文字前会让用户干等，
        故此处只做零成本查找，未命中的留到正文推完后由 after_push 补合成。
        @returns 上下文，含 {消息id: 音频路径}
        """
        from .. import message_flow
        return {"voice_map": message_flow.presynth_voice(items, push)}

    def after_push(self, recipient, conv_id, items, push, ctx):
        """锁外收尾：并发合成剩余语音并补推。

        与 QQ 通道保持一致：语音只是补充，不该占住正文推送锁，
        也不该让用户为了听语音而晚收到文字。
        @param ctx 上下文，含 before_push 得到的 voice_map
        """
        from .. import message_flow

        def _push_voice(client, chatid, path):
            """用企微的主动推送发一条语音。

            与 QQ 的差别只在最后这一步：QQ 走被动回复窗口，
            企微直接主动推送，合成、缓存、顺序等公共逻辑完全共用。
            """
            ok, _err = client.send_voice(chatid, path)
            return ok

        message_flow.postsynth_and_push_voice(
            self.client, recipient, items, push, (ctx or {}).get("voice_map") or {},
            push_voice_fn=_push_voice)

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
        return text_store.is_own_source(m, "wecom")

    def record_incoming(self, chatid, chat_type=1, user=""):
        """收到用户消息：登记会话并记下 chat_type。

        chat_type 决定出向消息按单聊还是群聊编码。
        @param chatid    会话 id
        @param chat_type 1 单聊 / 2 群聊
        @param user      发送者
        """
        target_store.wecom.note(chatid)
        self._chat_type[chatid] = int(chat_type or 1)
        from ..channel import wecom_chats
        wecom_chats.note(chatid, chat_type, user)
