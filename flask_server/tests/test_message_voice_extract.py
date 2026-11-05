"""语音文本提取测试（message_voice 执行路径）

背景：
  该模块此前只有 7% 覆盖。语音块有两种形态——标准代码块与漂移后的裸 JSON，
  提取器要兼容两者。曾经出过「合成 100% 失败但测试全绿」的事故，
  原因就是测试全部替换了执行函数，真实解析一次没跑过。本文件直接调真实函数。

覆盖点：
  1. 标准形态：代码块里的 bridge-voice 取其 text
  2. 漂移形态：正文里的裸 JSON 能被扫描捞取
  3. 都不是：返回空串
  4. 正文恰好提到 marker 但不构成 JSON：不误判
  5. md 优先于块文本
  6. strip_voice_blocks 能从正文中移除两种形态的语音块

运行：python -m pytest tests/test_message_voice_extract.py -q
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import message_voice as mv


def _voice_code(text):
    """造一个标准形态的语音代码块。

    @param text 朗读文本
    @returns 代码块对象
    """
    return {"type": "code", "code": json.dumps(
        {"type": "bridge-voice", "text": text}, ensure_ascii=False)}


class ExtractFromCodeBlocksTest(unittest.TestCase):
    """标准形态：代码块。"""

    def test_voice_taken_from_code_block(self):
        """代码块里的语音文本能被取出。"""
        m = {"blocks": [{"type": "paragraph", "text": "正文"},
                        _voice_code("朗读内容")]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "朗读内容")

    def test_empty_when_no_voice_block(self):
        """没有语音块时返回空串。"""
        m = {"blocks": [{"type": "paragraph", "text": "只有正文"}]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "")

    def test_ignores_non_voice_json_block(self):
        """别的 JSON 代码块不被误认成语音。"""
        m = {"blocks": [{"type": "code", "code": json.dumps(
            {"type": "bridge-chat-call", "tool": "x"})}]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "")

    def test_broken_json_block_ignored(self):
        """代码块内容不是合法 JSON 时跳过，不抛异常。"""
        m = {"blocks": [{"type": "code", "code": "{不是合法 json"}]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "")

    def test_code_block_without_type_field(self):
        """代码块是 JSON 但没有 type 字段：不算语音。"""
        m = {"blocks": [{"type": "code", "code": json.dumps({"text": "x"})}]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "")


class ExtractFromRawTextTest(unittest.TestCase):
    """漂移形态：正文里的裸 JSON。"""

    def test_voice_found_in_raw_text(self):
        """正文里混着裸 JSON 语音块时能捞出来。"""
        raw = '先说点别的。{"type":"bridge-voice","text":"裸形态语音"}'
        m = {"blocks": [{"type": "paragraph", "text": raw}]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "裸形态语音")

    def test_md_checked_before_blocks(self):
        """md 字段优先于块文本。"""
        m = {"md": '{"type":"bridge-voice","text":"来自 md"}',
             "blocks": [{"type": "paragraph",
                         "text": '{"type":"bridge-voice","text":"来自块"}'}]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "来自 md")

    def test_marker_without_json_not_matched(self):
        """正文提到 marker 但后面不构成 JSON：不误判。"""
        m = {"blocks": [{"type": "paragraph",
                         "text": '讨论一下 "type":"bridge-voice" 这个标记'}]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "")

    def test_first_voice_wins(self):
        """出现多个裸语音块时取第一个。"""
        raw = ('{"type":"bridge-voice","text":"第一"}'
               '{"type":"bridge-voice","text":"第二"}')
        m = {"blocks": [{"type": "paragraph", "text": raw}]}
        self.assertEqual(mv.extract_voice_from_blocks(m), "第一")


class StripVoiceBlocksTest(unittest.TestCase):
    """正文净化：移除语音块。"""

    def test_strip_raw_voice_block(self):
        """裸 JSON 形态的语音块被移除，其它文字保留。"""
        raw = '正文开头{"type":"bridge-voice","text":"要删的"}正文结尾'
        out = mv.strip_voice_blocks(raw)
        self.assertIn("正文开头", out)
        self.assertIn("正文结尾", out)
        self.assertNotIn("要删的", out)

    def test_strip_keeps_clean_text(self):
        """没有语音块时原样返回。"""
        self.assertEqual(mv.strip_voice_blocks("干净正文"), "干净正文")

    def test_strip_empty_returns_empty(self):
        """空输入返回空串。"""
        self.assertEqual(mv.strip_voice_blocks(""), "")


if __name__ == "__main__":
    unittest.main()
