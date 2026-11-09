"""页面登记表与多页面指令隔离的测试。

背景：一台电脑同时开多个网页 AI 时，指令卡片没有目标页面概念，
取件接口返回全部未确认卡片，任何页面的抽屉都可能取走别人的指令，
表现为指令串台。修复方案是给卡片加 target_page，取件时按页面过滤。

验证目标：
1. page_registry 的登记 / 在线列表 / 接管 / 选择器解析；
2. card_bus 的按页面取件规则（不限页面、指定页面、不匹配时取不到）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import page_registry
from card_bus import CardBus


class _PageBase(unittest.TestCase):
    """每个用例前清空页面登记，互不干扰。"""

    def setUp(self):
        page_registry.reset()

    def tearDown(self):
        page_registry.reset()


class TestPageRegistry(_PageBase):
    """页面登记表本身的行为。"""

    def test_register_登记后出现在在线列表(self):
        page_registry.register("https://a.com/chat")           # 显式上线
        self.assertIn("https://a.com/chat", page_registry.online())  # 立即出现在列表

    def test_register_空地址被忽略(self):
        page_registry.register("")                             # 空串不登记
        page_registry.register(None)                           # None 也不登记
        self.assertEqual(page_registry.online(), [])           # 列表仍为空

    def test_重复登记不产生重复项(self):
        page_registry.register("https://a.com")                # 第一次登记
        page_registry.register("https://a.com")                # 重复登记
        self.assertEqual(page_registry.online(), ["https://a.com"])  # 集合去重，只有一条

    def test_unregister_下线后立即消失(self):
        """下线是显式的：不再有 90 秒超时窗口。"""
        page_registry.register("https://a.com")                # 先上线
        page_registry.unregister("https://a.com")              # 再显式下线
        self.assertNotIn("https://a.com", page_registry.online())    # 立刻查不到

    def test_unregister_不存在的页面不报错(self):
        page_registry.unregister("https://never.com")          # 注销未登记的页面
        self.assertEqual(page_registry.online(), [])           # 不抛异常，列表为空

    def test_unregister_空地址被忽略(self):
        page_registry.register("https://a.com")                # 先有一条
        page_registry.unregister("")                           # 空地址注销应被忽略
        self.assertEqual(page_registry.online(), ["https://a.com"])  # 原记录不受影响

    def test_在线列表按地址排序(self):
        page_registry.register("https://c.com")                # 乱序登记
        page_registry.register("https://a.com")
        page_registry.register("https://b.com")
        self.assertEqual(page_registry.online(),
                         ["https://a.com", "https://b.com", "https://c.com"])  # 输出有序

    def test_默认未接管(self):
        self.assertEqual(page_registry.get_active(), "")      # 初始无接管页

    def test_设置接管页面(self):
        page_registry.register("https://a.com")                # 页面需先在线
        self.assertTrue(page_registry.set_active("https://a.com"))   # 设置在线的页面成功
        self.assertEqual(page_registry.get_active(), "https://a.com")

    def test_不能接管离线页面(self):
        self.assertFalse(page_registry.set_active("https://nope.com"))  # 未登记的页面不可接管
        self.assertEqual(page_registry.get_active(), "")

    def test_空串取消接管(self):
        page_registry.register("https://a.com")                # 先上线
        page_registry.set_active("https://a.com")              # 再接管
        self.assertTrue(page_registry.set_active(""))          # 空串表示取消
        self.assertEqual(page_registry.get_active(), "")

    def test_按序号选择页面(self):
        page_registry.register("https://a.com")                # 第 1 个
        page_registry.register("https://b.com")                # 第 2 个
        url, err = page_registry.resolve("2")                  # 按序号选第 2 个
        self.assertEqual(err, "")
        self.assertEqual(url, "https://b.com")

    def test_序号越界报错(self):
        page_registry.register("https://a.com")                # 只有 1 个页面
        url, err = page_registry.resolve("5")                  # 取第 5 个必然越界
        self.assertEqual(url, "")
        self.assertIn("超出范围", err)

    def test_按地址片段选择(self):
        page_registry.register("https://a.com/chat")           # 两个页面都含 chat
        page_registry.register("https://b.com/chat")
        url, err = page_registry.resolve("a.com")              # 用更精确的片段消歧
        self.assertEqual(err, "")
        self.assertEqual(url, "https://a.com/chat")

    def test_片段匹配多个时报错(self):
        """歧义时必须报错，不能随便挑一个——挑错等于串台。"""
        page_registry.register("https://a.com/chat")           # 两个页面都含 chat
        page_registry.register("https://b.com/chat")
        url, err = page_registry.resolve("chat")                # 片段有歧义
        self.assertEqual(url, "")
        self.assertIn("匹配到", err)

    def test_无匹配时报错(self):
        page_registry.register("https://a.com")                # 只有一个无关页面
        url, err = page_registry.resolve("zzz")                # 无任何匹配
        self.assertEqual(url, "")
        self.assertIn("没有页面匹配", err)

    def test_off_表示取消接管(self):
        url, err = page_registry.resolve("off")
        self.assertEqual(url, "")
        self.assertEqual(err, "")

    def test_空选择器报错(self):
        url, err = page_registry.resolve("")
        self.assertEqual(url, "")
        self.assertIn("请给出", err)


class TestCardBusPageIsolation(unittest.TestCase):
    """卡片总线的按页面取件规则。"""

    def _make(self, bus, target=""):
        return bus.create(source="bridge", card_type="drawer-command",
                          title="t", content="{}", payload={}, target_page=target)

    def test_不限页面的卡片任何页面都能取(self):
        bus = CardBus()
        self._make(bus)
        self.assertEqual(len(bus.claim_pending("https://a.com")), 1)
        self.assertEqual(len(bus.claim_pending("https://b.com")), 1)

    def test_指定页面的卡片只有该页面能取(self):
        bus = CardBus()
        self._make(bus, target="https://a.com")
        self.assertEqual(len(bus.claim_pending("https://a.com")), 1)
        self.assertEqual(len(bus.claim_pending("https://b.com")), 0)

    def test_未声明页面的取件方取不到指定页面卡片(self):
        """宁可不给，也不串台。"""
        bus = CardBus()
        self._make(bus, target="https://a.com")
        self.assertEqual(len(bus.claim_pending("")), 0)

    def test_确认后不再投递(self):
        bus = CardBus()
        card = self._make(bus, target="https://a.com")
        bus.confirm_delivered(card.id)
        self.assertEqual(len(bus.claim_pending("https://a.com")), 0)

    def test_多页面各取各的(self):
        bus = CardBus()
        self._make(bus, target="https://a.com")
        self._make(bus, target="https://b.com")
        self._make(bus, target="")
        # a 页面：自己的 1 张 + 不限页面的 1 张
        self.assertEqual(len(bus.claim_pending("https://a.com")), 2)
        # b 页面：同理
        self.assertEqual(len(bus.claim_pending("https://b.com")), 2)
        # c 页面：只有不限页面的那张
        self.assertEqual(len(bus.claim_pending("https://c.com")), 1)

    def test_卡片字典带出目标页面(self):
        bus = CardBus()
        self._make(bus, target="https://a.com")
        cards = bus.claim_pending("https://a.com")
        self.assertEqual(cards[0]["target_page"], "https://a.com")


if __name__ == "__main__":
    unittest.main()
