"""通道绑定与按通道隔离的测试。

背景：QQ 与企微都是单窗口，同时开多个网页 AI 时，两者的消息会混在
同一片页面池里。绑定后「QQ 只跟 DeepSeek、企微只跟 GLM」，互不干扰。

验证目标：
1. 绑定表的读写、解除、批量载入；
2. 通道解析目标页面的规则（接管页优先、无页面退回空串）；
3. 推送侧的站点过滤（未绑定全收、绑定只收本站点、未知站点仍收）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import channel_binding
import page_registry


class _BindBase(unittest.TestCase):
    """每个用例前清空绑定与页面表，互不干扰。"""

    def setUp(self):
        channel_binding.reset()
        page_registry.reset()

    def tearDown(self):
        channel_binding.reset()
        page_registry.reset()


class TestBindingTable(_BindBase):
    """绑定表本身。"""

    def test_默认未绑定(self):
        self.assertEqual(channel_binding.get("qq"), "")

    def test_绑定后能读回(self):
        self.assertTrue(channel_binding.bind("qq", "deepseek"))
        self.assertEqual(channel_binding.get("qq"), "deepseek")

    def test_两条通道各自独立(self):
        """这是本次需求的核心：QQ 与企微互不影响。"""
        channel_binding.bind("qq", "deepseek")
        channel_binding.bind("wecom", "glm")
        self.assertEqual(channel_binding.get("qq"), "deepseek")
        self.assertEqual(channel_binding.get("wecom"), "glm")

    def test_空串解除绑定(self):
        channel_binding.bind("qq", "deepseek")
        self.assertTrue(channel_binding.bind("qq", ""))
        self.assertEqual(channel_binding.get("qq"), "")

    def test_重复绑定同一值返回假(self):
        channel_binding.bind("qq", "deepseek")
        self.assertFalse(channel_binding.bind("qq", "deepseek"))

    def test_空通道名被忽略(self):
        self.assertFalse(channel_binding.bind("", "deepseek"))

    def test_批量载入(self):
        channel_binding.load_from_config({"qq": "deepseek", "wecom": "glm"})
        self.assertEqual(channel_binding.get("qq"), "deepseek")
        self.assertEqual(channel_binding.get("wecom"), "glm")

    def test_载入时非法项被跳过(self):
        channel_binding.load_from_config({"qq": "", "": "glm", "wecom": "glm"})
        self.assertEqual(channel_binding.get("qq"), "")
        self.assertEqual(channel_binding.get("wecom"), "glm")

    def test_载入非字典不报错(self):
        channel_binding.load_from_config(None)
        self.assertEqual(channel_binding.get("qq"), "")


class TestResolveTargetPage(_BindBase):
    """通道 → 页面地址的解析。"""

    def test_未绑定返回空串(self):
        self.assertEqual(channel_binding.resolve_target_page("qq"), "")

    def test_绑定但无在线页面返回空串(self):
        """无在线页面时退回广播，不卡住消息。"""
        channel_binding.bind("qq", "deepseek")
        self.assertEqual(channel_binding.resolve_target_page("qq"), "")

    def test_绑定且有在线页面时解析出地址(self):
        channel_binding.bind("qq", "deepseek")
        page_registry.touch("https://chat.deepseek.com/chat/1")
        url = channel_binding.resolve_target_page("qq")
        self.assertIn("deepseek", url)

    def test_两条通道解析到各自的页面(self):
        """QQ 解析到 deepseek 页、企微解析到 glm 页，互不串。"""
        channel_binding.bind("qq", "deepseek")
        channel_binding.bind("wecom", "glm")
        page_registry.touch("https://chat.deepseek.com/chat/1")
        page_registry.touch("https://chatglm.cn/main/2")
        self.assertIn("deepseek", channel_binding.resolve_target_page("qq"))
        self.assertIn("chatglm", channel_binding.resolve_target_page("wecom"))

    def test_接管页优先于首个在线页(self):
        channel_binding.bind("qq", "deepseek")
        page_registry.touch("https://chat.deepseek.com/chat/aaa")
        page_registry.touch("https://chat.deepseek.com/chat/zzz")
        page_registry.set_active("https://chat.deepseek.com/chat/zzz")
        self.assertEqual(channel_binding.resolve_target_page("qq"),
                         "https://chat.deepseek.com/chat/zzz")


class TestSiteFilter(_BindBase):
    """推送侧的站点过滤规则。"""

    def _ok(self, channel, site):
        """复刻 RemoteBridge._site_ok 的判定逻辑。"""
        bound = channel_binding.get(channel)
        if not bound:
            return True
        if not site:
            return True
        return bound == site

    def test_未绑定通道接收全部站点(self):
        self.assertTrue(self._ok("qq", "deepseek"))
        self.assertTrue(self._ok("qq", "glm"))

    def test_绑定通道只收本站点(self):
        channel_binding.bind("qq", "deepseek")
        self.assertTrue(self._ok("qq", "deepseek"))
        self.assertFalse(self._ok("qq", "glm"))

    def test_两条通道各收各的(self):
        """同一条消息：QQ 收 deepseek，企微收 glm，交叉收不到。"""
        channel_binding.bind("qq", "deepseek")
        channel_binding.bind("wecom", "glm")
        self.assertTrue(self._ok("qq", "deepseek"))
        self.assertFalse(self._ok("qq", "glm"))
        self.assertTrue(self._ok("wecom", "glm"))
        self.assertFalse(self._ok("wecom", "deepseek"))

    def test_未知站点的消息绑定通道也接收(self):
        """历史数据没站点标记，绑定通道也收，避免丢历史。"""
        channel_binding.bind("qq", "deepseek")
        self.assertTrue(self._ok("qq", ""))


if __name__ == "__main__":
    unittest.main()
