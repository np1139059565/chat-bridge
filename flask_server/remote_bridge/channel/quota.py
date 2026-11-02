"""远程桥接 —— 配额策略

三条通道的发送限额完全不同，这是它们最本质的差异之一：

    QQ      —— 被动回复窗口：用户发消息后 60 分钟内可回复，无条数上限；
               窗口关闭即不能主动推送。
    微信    —— 24 小时内最多 10 条独立消息，且不支持主动推送。
               超额后必须把整批消息合并成一条长文本，否则几轮对话就耗尽配额。
    企业微信 —— 走机器人接口，无明确条数限制，可主动推送。

差异不能被抹平，只能收敛。本模块用一个策略对象描述「这条通道怎么算配额」，
推送管线据此决定「能不能发、要不要合并、超了怎么提示」，各通道不再各写一份判断。
"""
import threading
import time


class QuotaPolicy:
    """配额策略基类：默认不限条数、必须能主动推送。

    子类按通道特性覆盖：微信改成窗口内限条数，QQ 改成依赖被动回复窗口。
    """

    # 窗口时长（秒）；0 表示不限窗口
    window_seconds = 0
    # 窗口内允许的条数；0 表示不限
    limit = 0
    # 是否支持主动推送（无需用户先发消息）
    can_push_freely = True

    def __init__(self):
        """初始化记账表与锁。"""
        # 记账表：{ 用户标识: [(时间戳, 条数), ...] }
        self._usage = {}
        # 保护 _usage 的锁：多条线程可能同时发送并记账
        self._lock = threading.RLock()

    def record(self, user_id, count=1):
        """记一次发送，并顺手清理过期记录。

        @param user_id 用户标识
        @param count   本次消耗的条数
        """
        # 不限配额的通道不必记账，省掉无谓的内存与锁开销
        if not self.limit or not self.window_seconds:
            return
        now = time.time()
        with self._lock:
            rows = self._usage.setdefault(user_id, [])
            # 追加本次记录
            rows.append((now, count))
            # 清理窗口外的旧记录：只保留仍在窗口内的，避免列表无限增长
            cutoff = now - self.window_seconds
            self._usage[user_id] = [r for r in rows if r[0] >= cutoff]

    def used(self, user_id):
        """取某用户在窗口内已用的条数。

        @param user_id 用户标识
        @returns 已用条数
        """
        # 不限配额：恒为 0，调用方据此不会触发「超额」分支
        if not self.limit or not self.window_seconds:
            return 0
        now = time.time()
        cutoff = now - self.window_seconds
        with self._lock:
            rows = self._usage.get(user_id) or []
            # 只统计窗口内的记录，同时顺手把过期项清掉
            alive = [r for r in rows if r[0] >= cutoff]
            if alive:
                self._usage[user_id] = alive
            else:
                self._usage.pop(user_id, None)
            return sum(r[1] for r in alive)

    def remaining(self, user_id):
        """取窗口内剩余可发条数；不限配额时返回 None。

        @param user_id 用户标识
        @returns 剩余条数或 None
        """
        if not self.limit:
            return None
        return max(0, self.limit - self.used(user_id))

    def exhausted(self, user_id):
        """判断配额是否已用尽。

        @param user_id 用户标识
        @returns 用尽返回 True
        """
        left = self.remaining(user_id)
        return left is not None and left <= 0

    def warn_text(self, user_id):
        """配额将满 / 已满时的提示文案；无需要时返回空串。

        默认实现：剩余 1 条时提示「下条可能收不到」。
        @param user_id 用户标识
        @returns 提示文案
        """
        left = self.remaining(user_id)
        if left is None or left > 1:
            return ""
        if left <= 0:
            return "（配额已用尽，本条可能无法送达）"
        return "（配额仅剩 1 条，后续消息可能合并发送）"


class UnlimitedQuota(QuotaPolicy):
    """不限条数、可主动推送：企业微信使用。"""


class WeixinQuota(QuotaPolicy):
    """微信配额：24 小时内最多 10 条，且不支持主动推送。

    超配额时必须把整批消息合并成一条长文本——这正是微信 router
    与 QQ 逐条推送的根本差异。
    """

    window_seconds = 24 * 60 * 60
    limit = 10
    can_push_freely = False


class QQWindowQuota(QuotaPolicy):
    """QQ 配额：依赖被动回复窗口，窗口内不限条数。

    窗口本身由 window_store 维护（必须与序号一起持久化），
    故这里不再重复记条数，只声明「不能主动推送」。
    """

    can_push_freely = False


# 三条通道各自的策略实例：记账表互不干扰。
qq = QQWindowQuota()
weixin = WeixinQuota()
wecom = UnlimitedQuota()
