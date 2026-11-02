"""远程桥接 —— QQ 通道适配器

QQ 是三条通道里最复杂的一条，差异集中在：

    1. 被动回复窗口 —— 用户发消息后 60 分钟内才能回复，
       且 (msg_id, msg_seq) 必须唯一递增，否则被 QQ 静默丢弃
    2. 一条消息会产出多个独立推送单元 —— 正文、图片、卡片结果
       各自用不同的去重 key（mid / mid#img / mid#cardid）
    3. 语音是补充能力 —— 文字推完才补推，且合成要放锁外

第 2 点是本适配器覆盖 push_one 的原因：公共管线的去重维度是
「一条消息一个 id」，而 QQ 需要「一条消息多个子 key」。把子维度
留在适配器内，公共层不必为单条通道的特殊性扭曲。
"""
from ..channel.adapter import ChannelAdapter
from ..channel import dedupe as dedupe_store
from ..channel import quota as quota_store
from ..channel import target as target_store


class QQAdapter(ChannelAdapter):
    """QQ 通道适配器。"""

    def __init__(self, client=None):
        """构造适配器。

        @param client QQClient 实例；可后置注入
        """
        super().__init__("qq", dedupe_store.qq, quota_store.qq)
        self.client = client

    def send_text(self, target, text, markdown=False):
        """发送文本，走被动回复窗口。

        窗口已关闭时返回失败——这不是异常，而是「此刻不能推」，
        调用方据此把消息留待下次重试。
        @param target   收件人 openid
        @param text     正文
        @param markdown 是否按 Markdown 发送
        @returns (是否成功, 平台返回)
        """
        if not self.client:
            return False, "NO_CLIENT"
        from .. import message_router
        # 复用既有 push_text：内部统一分配 seq，避免编号冲突被丢弃
        ok = message_router.push_text(self.client, target, text, markdown=markdown)
        return ok, {}

    def resolve_target(self, payload):
        """确定收件人：上报体带 openid，否则回退最近发来 QQ 消息的人。

        @param payload 上报体
        @returns openid；无从确定返回空串
        """
        from ..message_router import WEB_OPENID
        openid = payload.get("openid") or ""
        # 网页端的固定标识不是 QQ 用户，不能拿来推送
        if openid and openid != WEB_OPENID:
            return openid
        return target_store.qq.get()

    def is_own_source(self, m):
        """判断消息是否由 QQ 通道自己投递（不回推，避免复读）。

        @param m 消息对象
        @returns 来自 QQ 返回 True
        """
        from ..message_parse import _has_qq_source
        return _has_qq_source(m)

    def prepare_items(self, conv_id, items):
        """合并上次推送失败的消息，让它们获得重试机会。

        失败的消息可能已滚出可见区、不再出现在切片里，只能靠缓存补回来。
        @param conv_id 会话标识
        @param items   本轮切片消息
        @returns 合并后的消息列表
        """
        from .. import bridge_store
        return bridge_store.merge_pending(conv_id, items)

    def before_push(self, recipient, conv_id, items, push):
        """锁外预处理：只查语音缓存，不做合成。

        合成一条要一秒以上，放在推文字前会让用户干等；
        故此处只做零成本查找，未命中的留到推完后补合成。
        @returns 上下文，含 {消息id: 音频路径}
        """
        from .. import message_flow
        return {"voice_paths": message_flow.presynth_voice(items, push)}

    def after_push(self, recipient, conv_id, items, push, ctx):
        """锁外收尾：并发合成剩余语音并补推。

        语音只是补充，不该占住正文推送锁。
        @param ctx 上下文，含 before_push 得到的 voice_paths
        """
        from .. import message_flow
        message_flow.postsynth_and_push_voice(
            self.client, recipient, items, push, (ctx or {}).get("voice_paths") or {})

    def push_one(self, recipient, conv_id, m, push, ctx):
        """推送一条消息的全部单元：正文、图片、卡片结果。

        三者的去重 key 各不相同，必须分开记账：
          - 正文：mid
          - 图片：mid#img（工具结果晚于正文产生，不能因正文推过就被挡住）
          - 卡片：mid#cardid
        任一处失败都不记账，留待下轮重试。
        @returns 'skip' / 'sent' / 'fail'
        """
        from .. import message_router as mr
        from .. import bridge_store
        mid = m.get("id") or ""
        voice_paths = (ctx or {}).get("voice_paths") or {}
        pushed = bridge_store.get_pushed_set(conv_id)
        seen = []
        failed = False
        # 正文与图片各自去重、各自判成败
        if mid and mid not in pushed:
            status = mr._push_one(self.client, recipient, m, push, voice_paths)
            if status in ("sent", "skip"):
                seen.append(mid)
            elif status == "fail":
                failed = True
        # 图片块：按「消息id#img」独立去重，不受正文是否推过的影响
        img_seen = []
        try:
            _, img_failed = mr._push_images_block(
                self.client, recipient, m, push, pushed, img_seen)
            if img_failed:
                failed = True
        except Exception:
            failed = True
        seen.extend(img_seen)
        # 卡片结果：按「消息id#卡片id」去重，与正文互不影响。
        # 只处理截图类，文本结果经回传链路本就到 QQ，此处再推会重复。
        card_seen = []
        try:
            for card in (m.get("cardResults") or []):
                cid = card.get("id") or ""
                if not cid:
                    continue
                ckey = (mid + "#" + cid) if mid else cid
                if ckey in pushed:
                    continue
                if mr._push_card_result(self.client, recipient, card, push):
                    card_seen.append(ckey)
        except Exception:
            failed = True
        seen.extend(card_seen)
        if seen:
            bridge_store.mark_pushed(conv_id, seen)
        if failed:
            return "fail"
        return "sent" if seen else "skip"

    def record_incoming(self, openid, msg_id=None, client=None):
        """收到 QQ 用户消息：刷新窗口并登记为最近用户。

        窗口与序号必须一起持久化：QQ 按 (msg_id, msg_seq) 去重，
        重启后序号从 1 重数会撞号，消息被静默丢弃。
        @param openid 发来消息的 QQ 用户
        @param msg_id 本条消息的 id（用于回复窗口）
        @param client QQClient 实例
        """
        target_store.qq.note(openid)
        if msg_id:
            from .. import message_router
            message_router.note_incoming(openid, msg_id, client)
