"""卡片投递：文本与文件（channel/delivery 执行路径）

背景：
  deliver_text 把用户消息包成 external-call 信封投成卡片，前端按这个结构
  识别来源与语音标记。改结构会直接破坏前端识别——用户发的消息在网页 AI
  那边认不出来源，甚至被当成普通文本。deliver_file 同理，路径写错模型就
  拿不到文件。

  这两个函数此前无测试覆盖，只有 deliver_images 有。

覆盖点：
  1. deliver_text 的信封结构：type / source / openid / from_voice 各字段
  2. from_voice 为真时信封标记要如实反映
  3. msg_id 为空时的容错
  4. deliver_file 的正文包含路径与体积
  5. 文件不存在时体积按 0 记，不抛异常
  6. 卡片总线抛异常时返回空串，不向上传播

运行：python -m pytest tests/test_channel_delivery_text_file.py -q
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import channel_binding
from remote_bridge.channel import delivery


class FakeCard:
    """卡片替身：只带 id。"""

    def __init__(self, cid):
        """@param cid 卡片 id"""
        self.id = cid


class FakeBus:
    """卡片总线替身：记录调用参数，可预设抛异常。"""

    def __init__(self, raise_exc=False):
        """@param raise_exc 是否在 create 时抛异常"""
        self.calls = []
        self.raise_exc = raise_exc

    def create(self, **kwargs):
        """记录一次建卡调用。

        @returns 卡片对象
        """
        self.calls.append(kwargs)
        if self.raise_exc:
            raise RuntimeError("总线炸了")
        return FakeCard("card-123")


class DeliverTextTest(unittest.TestCase):
    """文本投递：信封结构是前端识别的契约。"""

    def setUp(self):
        """替换卡片总线。"""
        self._orig = delivery.card_bus.bus
        self.bus = FakeBus()
        delivery.card_bus.bus = self.bus

    def tearDown(self):
        """还原总线。"""
        delivery.card_bus.bus = self._orig

    def _envelope(self):
        """取最近一次投递的信封（content 是 JSON 文本）。"""
        return json.loads(self.bus.calls[-1]["content"])

    def test_returns_card_id(self):
        """成功时返回卡片 id。"""
        cid = delivery.deliver_text("qq", "openid-1", "你好")
        self.assertEqual(cid, "card-123")

    def test_envelope_core_fields(self):
        """信封核心字段齐全且取值正确——前端靠它们识别来源。"""
        delivery.deliver_text("wecom", "user-a", "正文内容", msg_id="m-1")
        env = self._envelope()
        self.assertEqual(env["type"], "external-call")
        self.assertEqual(env["source"], "wecom")
        self.assertEqual(env["openid"], "user-a")
        self.assertEqual(env["request"], "正文内容")
        self.assertEqual(env["msg_id"], "m-1")

    def test_from_voice_flagged(self):
        """语音确认投递时，from_voice 必须为真——前端据此要求回复含语音块。"""
        delivery.deliver_text("qq", "u", "语音转的文字", from_voice=True)
        self.assertTrue(self._envelope()["from_voice"])

    def test_from_voice_default_false(self):
        """普通投递时 from_voice 为假。"""
        delivery.deliver_text("qq", "u", "文字")
        self.assertFalse(self._envelope()["from_voice"])

    def test_msg_id_defaults_to_empty(self):
        """不传 msg_id 时信封里是空串而非缺失。"""
        delivery.deliver_text("qq", "u", "文字")
        self.assertEqual(self._envelope()["msg_id"], "")

    def test_card_type_is_external_call(self):
        """卡片类型必须是 external-call，前端按它分流渲染。"""
        delivery.deliver_text("qq", "u", "文字")
        self.assertEqual(self.bus.calls[-1]["card_type"], "external-call")

    def test_bus_exception_returns_empty(self):
        """总线异常时返回空串，不向上抛。"""
        delivery.card_bus.bus = FakeBus(raise_exc=True)
        self.assertEqual(delivery.deliver_text("qq", "u", "文字"), "")


class DeliverFileTest(unittest.TestCase):
    """文件投递：正文要让模型知道路径与体积。"""

    def setUp(self):
        """替换卡片总线并建临时文件。"""
        import tempfile
        self._orig = delivery.card_bus.bus
        self.bus = FakeBus()
        delivery.card_bus.bus = self.bus
        self.tmpdir = tempfile.mkdtemp(prefix="deliver_test_")

    def tearDown(self):
        """还原总线并清理临时目录。"""
        import shutil
        delivery.card_bus.bus = self._orig
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_file(self, name="a.txt", size=100):
        """造一个指定大小的文件。

        @returns 绝对路径
        """
        p = os.path.join(self.tmpdir, name)
        with open(p, "wb") as f:
            f.write(b"x" * size)
        return p

    def test_returns_card_id(self):
        """成功时返回卡片 id。"""
        p = self._make_file()
        self.assertEqual(delivery.deliver_file("qq", "u", p), "card-123")

    def test_body_contains_path_and_size(self):
        """正文必须写明路径与体积——模型靠路径取文件。"""
        p = self._make_file(size=42)
        delivery.deliver_file("qq", "u", p)
        content = self.bus.calls[-1]["content"]
        self.assertIn(p, content)
        self.assertIn("42", content)

    def test_default_name_from_path(self):
        """不传 name 时取文件基本名。"""
        p = self._make_file(name="报告.txt")
        delivery.deliver_file("qq", "u", p)
        self.assertEqual(self.bus.calls[-1]["payload"]["name"], "报告.txt")

    def test_missing_file_size_zero(self):
        """文件不存在时体积按 0 记，不抛异常。"""
        cid = delivery.deliver_file("qq", "u", "/no/such/file.bin")
        self.assertEqual(cid, "card-123")
        self.assertEqual(self.bus.calls[-1]["payload"]["size"], 0)

    def test_payload_kind(self):
        """payload 的 kind 标记为 qq-file，前端据此选渲染方式。"""
        p = self._make_file()
        delivery.deliver_file("qq", "u", p)
        self.assertEqual(self.bus.calls[-1]["payload"]["kind"], "qq-file")

    def test_bus_exception_returns_empty(self):
        """总线异常时返回空串。"""
        p = self._make_file()
        delivery.card_bus.bus = FakeBus(raise_exc=True)
        self.assertEqual(delivery.deliver_file("qq", "u", p), "")


class TargetPageTest(unittest.TestCase):
    """卡片归属：投递层按来源通道把目标页面补齐。"""

    PAGE = "https://chat.deepseek.com/chat/abc"

    def setUp(self):
        """清空绑定并替换卡片总线。"""
        channel_binding.reset()
        self._orig = delivery.card_bus.bus
        self.bus = FakeBus()
        delivery.card_bus.bus = self.bus

    def tearDown(self):
        """还原总线并清空绑定。"""
        delivery.card_bus.bus = self._orig
        channel_binding.reset()

    def test_bound_text_card_targets_bound_page(self):
        """通道绑定页面后，文本卡片的 target_page 等于该页面。"""
        channel_binding.bind("qq", self.PAGE)
        delivery.deliver_text("qq", "u", "文字")
        self.assertEqual(self.bus.calls[-1]["target_page"], self.PAGE)

    def test_unbound_text_card_has_no_target(self):
        """通道未绑定时，文本卡片不限页面。"""
        delivery.deliver_text("qq", "u", "文字")
        self.assertEqual(self.bus.calls[-1]["target_page"], "")

    def test_bound_file_card_targets_bound_page(self):
        """文件卡片与文本卡片共用同一套归属规则。"""
        import shutil
        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="deliver_target_")
        try:
            p = os.path.join(tmpdir, "a.txt")
            with open(p, "wb") as f:
                f.write(b"x")
            channel_binding.bind("qq", self.PAGE)
            delivery.deliver_file("qq", "u", p)
            self.assertEqual(self.bus.calls[-1]["target_page"], self.PAGE)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_explicit_target_page_wins(self):
        """调用方显式指定的页面优先于绑定表。"""
        channel_binding.bind("qq", self.PAGE)
        delivery.deliver_text("qq", "u", "文字",
                              target_page="https://chatglm.cn/main/xyz")
        self.assertEqual(self.bus.calls[-1]["target_page"],
                         "https://chatglm.cn/main/xyz")


if __name__ == "__main__":
    unittest.main()
