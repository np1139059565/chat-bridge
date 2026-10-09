"""规则文件管理：增删改、优先级、列举的测试。

背景：
    rules 负责规则 markdown 文件的增删改与优先级元数据管理，规则内容与优先级
    会进入 System Prompt。此前无任何测试。

隔离策略：
    rules 在导入时由 paths.RULES_DIR 确定规则目录。测试设置 paths.RULES_DIR 到
    临时目录并重载 rules，使读写落在临时目录；结束后复原并重载。

验证目标：
    1. valid_name / valid_priority：合法与非法取值；
    2. write_rule / read_rule / delete_rule 往返；
    3. list_rules：摘要取首个非空行，优先级正确回填；
    4. get_priority / set_priority：默认值与非法值处理；
    5. 非法规则名写规则时抛错。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_rules -v
"""
import importlib
import shutil
import sys
import tempfile
import os
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import rules


class _RulesBase(unittest.TestCase):
    """把规则目录重定向到临时目录。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rules_test_")
        self._orig = paths.RULES_DIR
        paths.RULES_DIR = Path(self.tmp) / "rules"
        importlib.reload(rules)

    def tearDown(self):
        paths.RULES_DIR = self._orig
        importlib.reload(rules)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestValidators(unittest.TestCase):
    """取值校验（不依赖目录）。"""

    def test_valid_name(self):
        """字母数字下划线连字符合法，其余非法。"""
        self.assertTrue(rules.valid_name("my-rule_1"))
        self.assertFalse(rules.valid_name("bad name"))
        self.assertFalse(rules.valid_name("a/b"))
        self.assertFalse(rules.valid_name(""))

    def test_valid_priority(self):
        """三种优先级合法，其余非法。"""
        self.assertTrue(rules.valid_priority("always"))
        self.assertTrue(rules.valid_priority("on-demand"))
        self.assertTrue(rules.valid_priority("off"))
        self.assertFalse(rules.valid_priority("sometimes"))


class TestCrud(_RulesBase):
    """增删改查往返。"""

    def test_write_and_read(self):
        """写入后可读回内容。"""
        rules.write_rule("r1", "# 标题\n正文")
        self.assertIn("正文", rules.read_rule("r1"))

    def test_read_missing_raises(self):
        """读取不存在的规则应抛 FileNotFoundError。"""
        with self.assertRaises(FileNotFoundError):
            rules.read_rule("nope")

    def test_write_invalid_name_raises(self):
        """非法规则名应抛 ValueError。"""
        with self.assertRaises(ValueError):
            rules.write_rule("bad name", "x")

    def test_delete_removes_file(self):
        """删除后文件不存在，再读抛错。"""
        rules.write_rule("r1", "内容")
        self.assertTrue(rules.delete_rule("r1"))
        with self.assertRaises(FileNotFoundError):
            rules.read_rule("r1")

    def test_delete_missing_returns_false(self):
        """删除不存在的规则返回 False。"""
        self.assertFalse(rules.delete_rule("nope"))


class TestList(_RulesBase):
    """规则列举。"""

    def test_summary_first_nonempty_line(self):
        """摘要应取首个非空行并去井号。"""
        rules.write_rule("r1", "\n\n# 我的标题\n正文")
        items = rules.list_rules()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["summary"], "我的标题")

    def test_list_sorted_by_name(self):
        """列举应按名称排序。"""
        rules.write_rule("b_rule", "b")
        rules.write_rule("a_rule", "a")
        names = [i["name"] for i in rules.list_rules()]
        self.assertEqual(names, ["a_rule", "b_rule"])

    def test_priority_reflected_in_list(self):
        """优先级设置后应在列举里回填。"""
        rules.write_rule("r1", "x", priority="always")
        items = rules.list_rules()
        self.assertEqual(items[0]["priority"], "always")


class TestPriority(_RulesBase):
    """优先级管理。"""

    def test_default_priority(self):
        """未设置时取默认 on-demand。"""
        rules.write_rule("r1", "x")
        self.assertEqual(rules.get_priority("r1"), "on-demand")

    def test_set_and_get_priority(self):
        """设置后可取回。"""
        rules.write_rule("r1", "x")
        rules.set_priority("r1", "off")
        self.assertEqual(rules.get_priority("r1"), "off")

    def test_set_invalid_priority_raises(self):
        """非法优先级应抛 ValueError。"""
        with self.assertRaises(ValueError):
            rules.set_priority("r1", "sometimes")

    def test_set_invalid_name_raises(self):
        """非法规则名应抛 ValueError。"""
        with self.assertRaises(ValueError):
            rules.set_priority("bad name", "always")


if __name__ == "__main__":
    unittest.main()
