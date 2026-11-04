"""微信配额状态查询（channel.quota.WeixinQuota.status）测试

为什么需要：
    微信的回复池语义是「每条用户消息发放一个约 10 条的池子」，
    与「按时间窗口累计」是两回事。设置页要展示「已用 / 剩余 / 是否有效」，
    这三种状态必须能从策略对象直接取得，否则调用方只能自己重算一遍，
    又退回到各写一份配额逻辑的老路。

覆盖内容：
    - 从未发过消息：无活跃池子，剩余为满额
    - 发过消息后重置：池子有效，已用为 0
    - 消耗若干条后：剩余相应减少
    - 池子过期：回到「无活跃池子」

运行：python -m pytest tests/test_channel_weixin_quota.py -q
"""
import time

from remote_bridge.channel.quota import WeixinQuota


class TestWeixinQuotaStatus:
    """回复池状态的对外查询。"""

    def test_no_pool_means_inactive(self):
        """用户从未发过消息时，没有活跃池子，剩余为满额。"""
        # 全新策略实例：记账表为空
        q = WeixinQuota()
        # 查一个从未登记过的用户
        st = q.status("never-sent")
        # 没有池子
        assert st["active"] is False
        # 剩余为上限 10 条
        assert st["remaining"] == 10
        # 已用为 0
        assert st["used"] == 0

    def test_reset_creates_active_pool(self):
        """用户发来消息后池子生效，已用归零。"""
        q = WeixinQuota()
        # 模拟用户发来消息：重置回复池
        q.reset("u1@im.wechat")
        st = q.status("u1@im.wechat")
        # 池子有效
        assert st["active"] is True
        # 刚重置，一条未用
        assert st["used"] == 0
        # 剩余为满额
        assert st["remaining"] == 10

    def test_consumed_reduces_remaining(self):
        """消耗若干条后，剩余相应减少。"""
        q = WeixinQuota()
        q.reset("u2@im.wechat")
        # 连发三条
        q.record("u2@im.wechat", 1)
        q.record("u2@im.wechat", 1)
        q.record("u2@im.wechat", 1)
        st = q.status("u2@im.wechat")
        # 已用三条
        assert st["used"] == 3
        # 剩余七条
        assert st["remaining"] == 7
        # 池子仍然有效
        assert st["active"] is True

    def test_expired_pool_becomes_inactive(self):
        """池子超过窗口时长后失效，状态回到「无活跃池子」。"""
        q = WeixinQuota()
        q.reset("u3@im.wechat")
        # 把池子的起始时间往前拨，模拟已过 24 小时
        with q._lock:
            q._usage["u3@im.wechat"] = [(time.time() - q.window_seconds - 1, 0)]
        st = q.status("u3@im.wechat")
        # 过期后不再算作有效池子
        assert st["active"] is False
        # 剩余回到满额
        assert st["remaining"] == 10
