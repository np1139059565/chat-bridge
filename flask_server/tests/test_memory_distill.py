"""蒸馏管道：工具精华摘要器测试。

背景：
    工具节点的 blocks 是 bridge-chat-res 的 JSON 原文。旧实现把整个 result
    序列化成 JSON 再截断，产出腰斩的机器串（无检索价值）。修复后按工具名
    分派专属摘要器，未登记工具走通用兜底，绝不整体 json.dumps。

验证目标：
    1. 已登记工具产出「工具名 + 结果摘要」形态的人话，含关键信息；
    2. 未登记工具走通用兜底，不返回腰斩 JSON；
    3. 告警结构取 message；
    4. 非 JSON 输入退回文本截断。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_distill -v
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import memory_distill as md


def _tool_text(tool, result):
    """构造 bridge-chat-res 的纯文本，供 _tool_essence 解析。"""
    return json.dumps({"tool": tool, "result": result}, ensure_ascii=False)


class TestToolEssence(unittest.TestCase):
    """验证工具精华摘要器按工具名分派、不产出腰斩 JSON。"""

    def _assert_no_json_dump(self, text):
        """断言摘要不是被截断的 JSON：不含花括号起始、不含大量引号。"""
        self.assertNotIn('{"', text, "摘要不应含 JSON 起始")
        self.assertLess(text.count('"'), 4, "摘要不应堆满引号")

    def test_search_content_summary(self):
        """search_content：应报命中数与首条文件位置。"""
        text = _tool_text("search_content",
                          {"count": 124, "matches": [{"file": "a.py", "line": 47}]})
        out = md._tool_essence(text)
        self.assertIn("search_content", out)
        self.assertIn("124", out)
        self.assertIn("a.py", out)
        self._assert_no_json_dump(out)

    def test_read_file_summary(self):
        """read_file：应报路径与总行数。"""
        text = _tool_text("read_file",
                          {"path": "D:/x/y.py", "total_lines": 150, "content": "line1\nline2"})
        out = md._tool_essence(text)
        self.assertIn("read_file", out)
        self.assertIn("D:/x/y.py", out)
        self.assertIn("150", out)
        self._assert_no_json_dump(out)

    def test_run_command_summary(self):
        """run_command：应报退出码与输出开头。"""
        text = _tool_text("run_command",
                          {"exitCode": 0, "stdout": "OK done\n", "stderr": ""})
        out = md._tool_essence(text)
        self.assertIn("run_command", out)
        self.assertIn("0", out)
        self.assertIn("OK done", out)
        self._assert_no_json_dump(out)

    def test_generic_fallback(self):
        """未登记工具：走通用兜底，取标量字段与数组计数，不整体序列化。"""
        text = _tool_text("some_new_tool",
                          {"ok": True, "message": "hello", "items": [1, 2, 3]})
        out = md._tool_essence(text)
        self.assertIn("some_new_tool", out)
        self.assertIn("hello", out)
        self.assertIn("3", out)   # items 3 项
        self._assert_no_json_dump(out)

    def test_issue_uses_message(self):
        """告警结构（含 issue 字段）：应取 message 当摘要。"""
        text = _tool_text("x", {"issue": "memory_stale", "message": "请抽检"})
        out = md._tool_essence(text)
        self.assertIn("请抽检", out)
        self.assertNotIn("issue", out)

    def test_invalid_json_fallback(self):
        """非 JSON 输入：退回文本截断，不抛异常。"""
        out = md._tool_essence("这不是 JSON，只是一段普通文本")
        self.assertIn("这不是 JSON", out)


if __name__ == "__main__":
    unittest.main()
