"""卡片总线与界面优先级的测试。

背景：
    card_bus 负责外部卡片的登记与投递（含总数上限裁剪，防内存泄漏）；
    ui_priority 负责让后台维护在界面请求进行时主动让路。此前均无测试。

隔离策略：
    card_bus 测试新建独立 CardBus 实例，不碰全局单例 bus；
    ui_priority 测试直接操作模块计数，并在 tearDown 复位为 0。

验证目标：
    1. CardBus.create / get / claim_pending / confirm_delivered 主流程；
    2. 未确认卡片可反复取走，确认后不再投递，重复确认幂等；
    3. 超过上限时优先裁剪已确认卡片，未确认的保留；
    4. ui_request_enter/exit 计数增减，exit 不使计数为负；
    5. maintenance_yield：无界面请求时不等待，有请求时会等待。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_card_bus_and_priority -v
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import card_bus
import ui_priority


def _new_bus():
    """新建独立总线实例，避免污染全局单例。"""
    return card_bus.CardBus()


class TestCardBus(unittest.TestCase):
    """卡片总线。"""

    def test_create_and_get(self):
        """登记后可按 id 取回。"""
        b = _new_bus()
        card = b.create("external", "t", "标题", "正文", {"k": 1})
        got = b.get(card.id)
        self.assertIsNotNone(got)
        self.assertEqual(got["content"], "正文")
        self.assertEqual(got["status"], card_bus.STATUS_PENDING)

    def test_get_missing_returns_none(self):
        """取不存在的卡片返回 None。"""
        self.assertIsNone(_new_bus().get("nope"))

    def test_claim_pending_excludes_delivered(self):
        """确认展示后的卡片不再出现在待投递列表。"""
        b = _new_bus()
        c1 = b.create("external", "t", "a", "正文1", {})
        c2 = b.create("external", "t", "b", "正文2", {})
        b.confirm_delivered(c1.id)
        pending_ids = {c["id"] for c in b.claim_pending()}
        self.assertNotIn(c1.id, pending_ids)
        self.assertIn(c2.id, pending_ids)

    def test_unconfirmed_can_be_claimed_repeatedly(self):
        """未确认的卡片可被反复取走。"""
        b = _new_bus()
        c = b.create("external", "t", "a", "正文", {})
        first = {x["id"] for x in b.claim_pending()}
        second = {x["id"] for x in b.claim_pending()}
        self.assertIn(c.id, first)
        self.assertIn(c.id, second)

    def test_confirm_idempotent(self):
        """重复确认应幂等，均返回 True。"""
        b = _new_bus()
        c = b.create("external", "t", "a", "正文", {})
        self.assertTrue(b.confirm_delivered(c.id))
        self.assertTrue(b.confirm_delivered(c.id))

    def test_confirm_missing_returns_false(self):
        """确认不存在的卡片返回 False。"""
        self.assertFalse(_new_bus().confirm_delivered("nope"))

    def test_trim_keeps_unconfirmed(self):
        """超上限时，未确认卡片必须保留。"""
        b = _new_bus()
        # 先造一张未确认卡片
        keep = b.create("external", "t", "keep", "正文", {})
        # 再造超上限的已确认卡片
        for i in range(card_bus.MAX_CARDS + 20):
            c = b.create("external", "t", "x", "正文", {})
            b.confirm_delivered(c.id)
        pending_ids = {c["id"] for c in b.claim_pending()}
        self.assertIn(keep.id, pending_ids)

    def test_trim_reduces_size(self):
        """超上限后总卡片数应回到上限之内。"""
        b = _new_bus()
        for i in range(card_bus.MAX_CARDS + 30):
            c = b.create("external", "t", "x", "正文", {})
            b.confirm_delivered(c.id)
        self.assertLessEqual(len(b._cards), card_bus.MAX_CARDS)


class TestUiPriority(unittest.TestCase):
    """界面优先级。"""

    def setUp(self):
        # 复位计数，避免用例间相互影响
        ui_priority._ui_active = 0

    def tearDown(self):
        ui_priority._ui_active = 0

    def test_enter_exit_counts(self):
        """进入 +1、结束 -1。"""
        ui_priority.ui_request_enter()
        self.assertEqual(ui_priority.ui_active_count(), 1)
        ui_priority.ui_request_exit()
        self.assertEqual(ui_priority.ui_active_count(), 0)

    def test_exit_not_below_zero(self):
        """无请求时调用 exit，计数不应变为负数。"""
        ui_priority.ui_request_exit()
        self.assertEqual(ui_priority.ui_active_count(), 0)

    def test_yield_no_wait_when_idle(self):
        """无界面请求时不应等待。"""
        self.assertFalse(ui_priority.maintenance_yield(step=0.001, max_wait=0.05))

    def test_yield_waits_when_active(self):
        """有界面请求时会等待，直到计数归零或超上限。"""
        ui_priority.ui_request_enter()
        t0 = time.time()
        yielded = ui_priority.maintenance_yield(step=0.001, max_wait=0.05)
        self.assertTrue(yielded)
        self.assertGreaterEqual(time.time() - t0, 0.001)


if __name__ == "__main__":
    unittest.main()
