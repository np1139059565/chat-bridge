"""远程桥接 —— 微信通道适配器

微信与其它通道的差异集中在这里，公共流程交给 channel.push_pipeline：

    1. 必须合并推送 —— 配额紧张，逐条推几轮就耗尽
    2. 正文只留结果不留过程 —— 工具调用参数是 JSON，手机上占满一屏
    3. 收件人必须是微信格式标识 —— 拿 QQ 的 id 去调微信接口会直接报错
    4. 配额按用户消息重置 —— 见 channel.quota.WeixinQuota.reset
"""
from ..channel.adapter import ChannelAdapter
from ..channel import dedupe as dedupe_store
from ..channel import quota as quota_store
from ..channel import target as target_store
from ..channel import text as text_store

# 合并多条消息时的分隔线
SEP = "\n\n———\n\n"

# 各类消息的展示前缀，与其它通道保持一致的视觉语言
PREFIX = {"user": "👤 用户", "tool": "🛠 工具", "ai": "🤖 AI"}

# 单条消息最多发送的字符数。微信对文本长度有上限，过长在手机上体验也差。
MAX_TEXT_CHARS = 1800


def _is_weixin_id(uid):
    """判断标识是否属于微信用户（iLink 下发形如 xxx@im.wechat）。

    @param uid 用户标识
    @returns 属于微信返回 True
    """
    return bool(uid) and str(uid).endswith("@im.wechat")


def _truncate(text):
    """按微信的上限截断文本，保留首尾。

    截断算法在公共层，此处只传微信自己的上限（1800，比企微短）：
    微信对文本长度限制更严，这个差异属通道固有属性，不能抹平。
    @param text 原文本
    @returns 截断后的文本
    """
    return text_store.truncate(text, MAX_TEXT_CHARS)


class WeixinAdapter(ChannelAdapter):
    """微信通道适配器。

    client 在运行时注入（由 bridge 单例持有），避免启动期强依赖。
    """

    def __init__(self, client=None):
        """构造适配器。

        @param client WeixinClient 实例；可后置注入
        """
        super().__init__("weixin", dedupe_store.weixin, quota_store.weixin)
        self.client = client

    def send_text(self, target, text, markdown=False):
        """发送文本。微信不支持 Markdown 渲染，markdown 参数仅作接口对齐。

        @param target   微信用户标识
        @param text     正文
        @param markdown 忽略
        @returns (是否成功, 平台返回)
        """
        if not self.client:
            return False, "NO_CLIENT"
        return self.client.send_text(target, text)

    def resolve_target(self, payload):
        """确定收件人：只接受微信格式标识，否则回退到最近微信用户。

        抽屉上报里的 openid 装的是 QQ 标识（或网页固定值），
        拿去调微信接口会返回 -3 invalid arguments，一条也发不出去。
        @param payload 上报体
        @returns 微信用户标识；无从确定返回空串
        """
        explicit = payload.get("weixin_user") or ""
        if _is_weixin_id(explicit):
            return explicit
        raw = payload.get("openid") or ""
        if _is_weixin_id(raw):
            return raw
        # 非微信标识一律丢弃，回退到本通道自己的记账
        return target_store.weixin.get()

    def is_own_source(self, m):
        """判断消息是否由微信通道自己投递（不回推，避免复读）。

        判定逻辑在公共层，此处只声明本通道的标识。
        @param m 消息对象
        @returns 来自微信返回 True
        """
        return text_store.is_own_source(m, "weixin")

    def merge_batch(self, items, push):
        """把一批消息合并成一条长文本。

        微信必须合并：每条用户消息只给一个约 10 条的回复池，
        逐条推会迅速耗尽。
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

    def _body_of(self, m, push):
        """取一条消息的待推正文（含类型前缀）；不可推返回空串。

        check_own 传 False：管线在上游已按来源过滤过，此处不重复判断。
        @param m    消息对象
        @param push 推送开关
        @returns 正文
        """
        return text_store.body_of(m, push, "weixin", check_own=False)

    def _extract_text(self, m, push):
        """提取微信要看的正文（实现见公共层）。

        剔除工具调用痕迹的理由：参数里的 JSON 在手机上一屏花括号，
        还挤占微信紧张的配额。
        @param m    消息对象
        @param push 推送开关
        @returns 正文文本；无可用内容返回空串
        """
        return text_store.extract_text(m, push)

    def record_incoming(self, user_id):
        """用户发来消息：登记为最近用户，并重置其回复池。

        @param user_id 微信用户标识
        """
        target_store.weixin.note(user_id)
        self.quota.reset(user_id)
