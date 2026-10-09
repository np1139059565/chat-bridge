"""JSON 安全反序列化与消息块文本抽取的边界测试。

背景：
    json_utils.safe_json_loads 与 memory_text.blocks_to_text 是两个被多处
    复用的纯函数——前者兜住非法 JSON，后者把消息块拍平成文本供蒸馏与抽检。
    它们此前无任何测试，边界（空值 / 脏数据 / 类型混杂）容易被忽略。

验证目标：
    1. safe_json_loads：合法解析、空值兜底、非法 JSON 兜底、默认值原样返回；
    2. blocks_to_text：text 与 code 抽取、跳过非字典项、空列表返回空串、
       strip 参数生效、非字符串内容转字符串。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_json_and_text_utils -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import json_utils
import memory_text


class TestSafeJsonLoads(unittest.TestCase):
    """安全反序列化。"""

    def test_valid_object(self):
        """合法 JSON 对象应正确解析。"""
        self.assertEqual(json_utils.safe_json_loads('{"a": 1}', {}), {"a": 1})

    def test_valid_array(self):
        """合法 JSON 数组应正确解析。"""
        self.assertEqual(json_utils.safe_json_loads('[1, 2]', []), [1, 2])

    def test_none_returns_default(self):
        """None 直接返回默认值，不抛异常。"""
        self.assertEqual(json_utils.safe_json_loads(None, []), [])

    def test_empty_string_returns_default(self):
        """空串返回默认值。"""
        self.assertEqual(json_utils.safe_json_loads("", {}), {})

    def test_invalid_json_returns_default(self):
        """非法 JSON 返回默认值，不向上抛。"""
        self.assertEqual(json_utils.safe_json_loads("{bad", {"x": 1}), {"x": 1})

    def test_default_is_returned_as_is(self):
        """默认值原样返回（同一对象）。"""
        d = []
        self.assertIs(json_utils.safe_json_loads("nope", d), d)


class TestBlocksToText(unittest.TestCase):
    """消息块文本抽取。"""

    def test_extract_text_blocks(self):
        """多个 text 块应用换行拼接。"""
        blocks = [{"type": "text", "text": "一"}, {"type": "text", "text": "二"}]
        self.assertEqual(memory_text.blocks_to_text(blocks), "一\n二")

    def test_extract_code_block(self):
        """无 text 时应取 code 字段。"""
        blocks = [{"type": "code", "code": "print(1)"}]
        self.assertEqual(memory_text.blocks_to_text(blocks), "print(1)")

    def test_skip_non_dict_items(self):
        """非字典项应被跳过，不报错。"""
        blocks = ["脏数据", {"text": "正常"}, 123]
        self.assertEqual(memory_text.blocks_to_text(blocks), "正常")

    def test_empty_and_none(self):
        """空列表与 None 均返回空串。"""
        self.assertEqual(memory_text.blocks_to_text([]), "")
        self.assertEqual(memory_text.blocks_to_text(None), "")

    def test_strip_flag(self):
        """strip=True 时去掉首尾空白。"""
        blocks = [{"text": "  内容  "}]
        self.assertEqual(memory_text.blocks_to_text(blocks, strip=True), "内容")
        self.assertEqual(memory_text.blocks_to_text(blocks), "  内容  ")

    def test_non_string_content_coerced(self):
        """非字符串内容应转成字符串。"""
        blocks = [{"text": 123}]
        self.assertEqual(memory_text.blocks_to_text(blocks), "123")

    def test_empty_text_skipped(self):
        """空字符串的块应被跳过。"""
        blocks = [{"text": ""}, {"text": "有效"}]
        self.assertEqual(memory_text.blocks_to_text(blocks), "有效")


if __name__ == "__main__":
    unittest.main()
