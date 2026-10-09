"""规则程序化：三类机械判定的边界测试。

背景：
    rule_enforce 承担「可机械判定的规则」的强制检查——写后回读、
    破坏性操作是否触碰真实数据、输出禁用词扫描。此前无任何测试。

验证目标：
    1. check_readback_after_write：写后有读判通过、写后无读判违规、
       连续两次写未回读时前一次记违规、空输入不报错；
    2. check_destructive_call：非破坏性放行、真实路径报警、
       临时标记放行、破坏性但无真实路径特征放行；
    3. check_forbidden_words：干净文本通过、命中禁用词时列出、去重；
    4. run_all：只检查传入项、all_ok 聚合正确。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_rule_enforce -v
"""
import os
import sys
import unittest

# 把服务根目录（flask_server/）加入模块搜索路径：
# 本文件位于 flask_server/tests/ 下，上一级才是被测模块所在目录。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导（把 core/ 与 tools/ 加入搜索路径）
import rule_enforce


class TestReadbackAfterWrite(unittest.TestCase):
    """验证「写文件后必须回读」的判定。"""

    def test_write_then_read_is_ok(self):
        """写完紧跟一次读，应判通过。"""
        calls = [{"tool": "write_to_file", "file": "a.txt"},
                 {"tool": "read_file", "file": "a.txt"}]
        res = rule_enforce.check_readback_after_write(calls)
        self.assertTrue(res["ok"])
        self.assertEqual(res["violations"], [])

    def test_write_without_read_is_violation(self):
        """写之后没有任何读，应判违规并列出该写操作。"""
        calls = [{"tool": "replace_in_file", "file": "a.py"}]
        res = rule_enforce.check_readback_after_write(calls)
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["violations"]), 1)
        self.assertEqual(res["violations"][0]["tool"], "replace_in_file")

    def test_two_writes_before_read_flags_first(self):
        """连续两次写都未回读时，前一次写应被记为违规。"""
        calls = [{"tool": "write_to_file", "file": "a"},
                 {"tool": "write_to_file", "file": "b"},
                 {"tool": "read_file", "file": "b"}]
        res = rule_enforce.check_readback_after_write(calls)
        self.assertFalse(res["ok"])
        # 第一次写未回读即被第二次写顶掉，记违规；第二次写被后面的读清空
        self.assertEqual(len(res["violations"]), 1)
        self.assertEqual(res["violations"][0]["index"], 0)

    def test_empty_input_is_ok(self):
        """空列表 / None 不应报错，也不产生违规。"""
        self.assertTrue(rule_enforce.check_readback_after_write([])["ok"])
        self.assertTrue(rule_enforce.check_readback_after_write(None)["ok"])


class TestDestructiveCall(unittest.TestCase):
    """验证破坏性操作扫描的判定。"""

    def test_non_destructive_is_safe(self):
        """非破坏性命令应放行。"""
        res = rule_enforce.check_destructive_call("ls -la", target="")
        self.assertFalse(res["risk"])

    def test_destructive_real_path_is_flagged(self):
        """破坏性操作指向真实路径且无临时标记，应报警。"""
        res = rule_enforce.check_destructive_call(
            "rm -rf", target="D:\\mydata\\chat-bridge\\flask_server\\data")
        self.assertTrue(res["risk"])

    def test_destructive_with_temp_marker_is_safe(self):
        """目标含临时/测试标记时，即使破坏性也应判定安全。"""
        res = rule_enforce.check_destructive_call(
            "delete", target="D:\\mydata\\temp\\test_db")
        self.assertFalse(res["risk"])

    def test_destructive_without_real_path_is_safe(self):
        """破坏性但未命中真实路径特征，应放行（避免误报）。"""
        res = rule_enforce.check_destructive_call("drop table foo")
        self.assertFalse(res["risk"])


class TestForbiddenWords(unittest.TestCase):
    """验证输出禁用词扫描。"""

    def test_clean_text_passes(self):
        """不含禁用词的文本应通过。"""
        res = rule_enforce.check_forbidden_words("这是一段普通说明。")
        self.assertTrue(res["ok"])
        self.assertEqual(res["hits"], [])

    def test_flattery_opening_flagged(self):
        """奉承开场应被命中。"""
        res = rule_enforce.check_forbidden_words("你说得太对了，不过……")
        self.assertFalse(res["ok"])
        self.assertIn("你说得太对了", res["hits"])

    def test_meta_leak_flagged(self):
        """元指令泄漏词应被命中。"""
        res = rule_enforce.check_forbidden_words("已移除旧逻辑")
        self.assertIn("已移除", res["hits"])

    def test_hits_deduplicated(self):
        """同一禁用词出现多次，只计一次。"""
        res = rule_enforce.check_forbidden_words("好问题，好问题！")
        self.assertEqual(res["hits"].count("好问题"), 1)

    def test_empty_text_is_ok(self):
        """空文本不应报错。"""
        self.assertTrue(rule_enforce.check_forbidden_words("")["ok"])
        self.assertTrue(rule_enforce.check_forbidden_words(None)["ok"])


class TestRunAll(unittest.TestCase):
    """验证汇总入口只检查传入项、all_ok 聚合正确。"""

    def test_only_checks_provided(self):
        """只传 text 时，结果里不应出现 readback / destructive。"""
        res = rule_enforce.run_all(text="普通文本")
        self.assertIn("forbidden", res)
        self.assertNotIn("readback", res)
        self.assertNotIn("destructive", res)

    def test_all_ok_true_when_clean(self):
        """全部干净时 all_ok 应为真。"""
        res = rule_enforce.run_all(tool_calls=[], command="ls", text="普通文本")
        self.assertTrue(res["all_ok"])

    def test_all_ok_false_when_violation(self):
        """任一检查不通过时 all_ok 应为假。"""
        res = rule_enforce.run_all(tool_calls=[{"tool": "write_to_file"}])
        self.assertFalse(res["all_ok"])


if __name__ == "__main__":
    unittest.main()
