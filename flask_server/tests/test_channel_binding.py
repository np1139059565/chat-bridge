"""通道与页面绑定的测试。

背景：QQ 与企微都是单窗口，同时开多个网页 AI 时，两者的消息会混在
同一片页面池里。绑定后「QQ 只跟 DeepSeek 页面、企微只跟 GLM 页面」，
互不干扰。绑定对象就是页面本身（不再区分站点与页面两层概念）。

验证目标：
1. 绑定表的读写、解除、批量载入；
2. 推送过滤规则（未绑定全收、已绑定只收该页、已绑定通道拒收无页面消息）。
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import channel_binding

DEEPSEEK_PAGE = "https://chat.deepseek.com/chat/abc"
GLM_PAGE = "https://chatglm.cn/main/xyz"


class _BindBase(unittest.TestCase):
    """每个用例前清空绑定，互不干扰。"""

    def setUp(self):
        channel_binding.reset()

    def tearDown(self):
        channel_binding.reset()


class TestBindingTable(_BindBase):
    """绑定表本身。"""

    def test_默认未绑定(self):
        self.assertEqual(channel_binding.get("qq"), "")

    def test_绑定后能读回(self):
        self.assertTrue(channel_binding.bind("qq", DEEPSEEK_PAGE))
        self.assertEqual(channel_binding.get("qq"), DEEPSEEK_PAGE)

    def test_两条通道各自独立(self):
        """这是本次需求的核心：QQ 与企微互不影响。"""
        channel_binding.bind("qq", DEEPSEEK_PAGE)
        channel_binding.bind("wecom", GLM_PAGE)
        self.assertEqual(channel_binding.get("qq"), DEEPSEEK_PAGE)
        self.assertEqual(channel_binding.get("wecom"), GLM_PAGE)

    def test_空串解除绑定(self):
        channel_binding.bind("qq", DEEPSEEK_PAGE)
        self.assertTrue(channel_binding.bind("qq", ""))
        self.assertEqual(channel_binding.get("qq"), "")

    def test_重复绑定同一值返回假(self):
        channel_binding.bind("qq", DEEPSEEK_PAGE)
        self.assertFalse(channel_binding.bind("qq", DEEPSEEK_PAGE))

    def test_空通道名被忽略(self):
        self.assertFalse(channel_binding.bind("", DEEPSEEK_PAGE))

    def test_批量载入(self):
        channel_binding.load_from_config({"qq": DEEPSEEK_PAGE, "wecom": GLM_PAGE})
        self.assertEqual(channel_binding.get("qq"), DEEPSEEK_PAGE)
        self.assertEqual(channel_binding.get("wecom"), GLM_PAGE)

    def test_载入时非法项被跳过(self):
        channel_binding.load_from_config({"qq": "", "": GLM_PAGE, "wecom": GLM_PAGE})
        self.assertEqual(channel_binding.get("qq"), "")
        self.assertEqual(channel_binding.get("wecom"), GLM_PAGE)

    def test_载入非字典不报错(self):
        channel_binding.load_from_config(None)
        self.assertEqual(channel_binding.get("qq"), "")


class TestMatches(_BindBase):
    """推送侧的页面过滤规则。"""

    def test_未绑定通道接收全部页面(self):
        self.assertTrue(channel_binding.matches("qq", DEEPSEEK_PAGE))
        self.assertTrue(channel_binding.matches("qq", GLM_PAGE))

    def test_绑定通道只收该页面(self):
        channel_binding.bind("qq", DEEPSEEK_PAGE)
        self.assertTrue(channel_binding.matches("qq", DEEPSEEK_PAGE))
        self.assertFalse(channel_binding.matches("qq", GLM_PAGE))

    def test_两条通道各收各的(self):
        """同一条消息：QQ 收 DeepSeek 页，企微收 GLM 页，交叉收不到。"""
        channel_binding.bind("qq", DEEPSEEK_PAGE)
        channel_binding.bind("wecom", GLM_PAGE)
        self.assertTrue(channel_binding.matches("qq", DEEPSEEK_PAGE))
        self.assertFalse(channel_binding.matches("qq", GLM_PAGE))
        self.assertTrue(channel_binding.matches("wecom", GLM_PAGE))
        self.assertFalse(channel_binding.matches("wecom", DEEPSEEK_PAGE))

    def test_无页面来源的消息绑定通道拒收(self):
        """已绑定通道遇到无页面标记的消息一律拒收。

        取舍：页面未知时无法确认归属，放行等于让任意页面的内容流进这条通道，
        与「不许串台」相反。宁可漏推（消息在网页上仍在，可在电脑端查看），
        也不让来源不明的内容混进手机端对话。
        """
        channel_binding.bind("qq", DEEPSEEK_PAGE)
        self.assertFalse(channel_binding.matches("qq", ""))

    def test_未绑定时无页面来源也接收(self):
        self.assertTrue(channel_binding.matches("qq", ""))


if __name__ == "__main__":
    unittest.main()
