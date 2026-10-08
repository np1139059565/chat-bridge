"""外部调用信封解包（envelope）测试。

被测：core/envelope.py 与 core/memory_distill._essence_for。

背景：桥接投递的用户消息被包成 external-call 信封（可能两层嵌套），
此前蒸馏对用户消息「原句即精华」，导致精华照抄整段 JSON、不可检索。
本测试锁定修复：用户消息的精华与关键词应基于解包后的真实文本。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_envelope_unwrap -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))

import envelope
import memory_distill


class TestUnwrapUserText(unittest.TestCase):
    """验证 unwrap_user_text 对各类输入的剥离行为。"""

    def test_single_layer_envelope(self):
        """单层信封：取出 request 里的用户话。"""
        text = '{"type":"external-call","request":"帮我看看日志"}'
        self.assertEqual(envelope.unwrap_user_text(text), "帮我看看日志")

    def test_nested_envelope(self):
        """双层嵌套信封：逐层剥到最内层真实文本。"""
        inner = '{"type":"external-call","request":"B","source":"web"}'
        outer = '{"type":"external-call","nonce":"x","request":%s}' % (
            __import__("json").dumps(inner))
        self.assertEqual(envelope.unwrap_user_text(outer), "B")

    def test_plain_text_unchanged(self):
        """普通话（非 JSON）：原样返回。"""
        self.assertEqual(envelope.unwrap_user_text("普通的一句话"), "普通的一句话")

    def test_empty_returns_empty(self):
        """空输入：返回空串。"""
        self.assertEqual(envelope.unwrap_user_text(""), "")

    def test_invalid_json_returns_raw(self):
        """非法 JSON：按普通文本原样返回，不吞内容。"""
        raw = "{不是合法json"
        self.assertEqual(envelope.unwrap_user_text(raw), raw)

    def test_merge_nested_envelope_passthrough(self):
        """非嵌套对象：merge 应原样返回。"""
        obj = {"type": "external-call", "request": "plain"}
        self.assertEqual(envelope.merge_nested_envelope(obj), obj)


class TestUserEssenceUnwrapped(unittest.TestCase):
    """验证蒸馏对用户消息的精华取自解包后的文本。"""

    def test_user_essence_is_inner_text(self):
        """用户消息是信封时，精华应是内层用户话，而非整段 JSON。"""
        text = '{"type":"external-call","request":"继续走查记忆系统"}'
        essence = memory_distill._essence_for("user", text, None)
        self.assertEqual(essence, "继续走查记忆系统")
        self.assertNotIn("external-call", essence)   # 不含信封结构
        self.assertNotIn("nonce", essence)

    def test_user_plain_text_still_intact(self):
        """普通用户发言：精华仍是原句。"""
        essence = memory_distill._essence_for("user", "帮我看下这个函数", None)
        self.assertEqual(essence, "帮我看下这个函数")


if __name__ == "__main__":
    unittest.main()
