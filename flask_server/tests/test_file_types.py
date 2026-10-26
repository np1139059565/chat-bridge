"""可粘贴文件类型清单与投递判定：测试。

覆盖三件事：
    1) 后缀解析对普通扩展名、点开头整名、无扩展名的处理；
    2) 清单内外的类型判定；
    3) 投递判定同时受开关与类型两个条件约束。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_file_types -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发 core/ 与 tools/ 的路径引导
import runtime
from file_types import is_pasteable, suffix_of
from file_delivery import should_paste


class TestSuffix(unittest.TestCase):
    """后缀解析。"""

    def test_common_extension(self):
        """普通文件取末段扩展名。"""
        self.assertEqual(suffix_of("a/b/readme.md"), ".md")
        self.assertEqual(suffix_of("C:\\\\x\\\\Y.PY"), ".py")

    def test_dotfile_without_extension(self):
        """点开头且仅一个点的文件名整体作为后缀。"""
        self.assertEqual(suffix_of("a/.gitignore"), ".gitignore")
        self.assertEqual(suffix_of("a/.gitkeep"), ".gitkeep")

    def test_no_extension(self):
        """无扩展名返回空串。"""
        self.assertEqual(suffix_of("a/Makefile"), "")
        self.assertEqual(suffix_of(""), "")

    def test_multi_dot_takes_last(self):
        """多点文件名取最后一段。"""
        self.assertEqual(suffix_of("a/archive.tar.gz"), ".gz")


class TestPasteable(unittest.TestCase):
    """清单类型判定。"""

    def test_common_types_in_list(self):
        """常见源码与文档类型在清单内。"""
        for name in ("a.py", "a.md", "a.json", "a.yaml", "a.js", "a.txt"):
            self.assertTrue(is_pasteable(name), name)

    def test_dotfile_not_pasteable(self):
        """无主名的点文件不参与附件粘贴，即使后缀在清单内。"""
        for name in (".gitignore", ".gitkeep", ".gitmodules", ".env", ".example", "a/.gitignore"):
            self.assertFalse(is_pasteable(name), name)

    def test_dotted_name_still_pasteable(self):
        """带主名的点文件按正常后缀判定。"""
        self.assertTrue(is_pasteable("a/.b.txt"))

    def test_unknown_type_not_in_list(self):
        """清单外的自定义后缀判定为不可粘贴。"""
        self.assertFalse(is_pasteable("a.weirdfmt"))
        self.assertFalse(is_pasteable("a.bin"))

    def test_no_extension_not_in_list(self):
        """无扩展名不在清单内。"""
        self.assertFalse(is_pasteable("Makefile"))


class TestShouldPaste(unittest.TestCase):
    """投递判定：开关与类型两个条件同时成立才走粘贴。"""

    def setUp(self):
        """保存原始配置以便还原。"""
        self._orig_config = runtime.CONFIG
        runtime.CONFIG = {}

    def tearDown(self):
        """还原配置。"""
        runtime.CONFIG = self._orig_config

    def _set(self, enabled):
        """设置全局开关当前值。"""
        runtime.CONFIG.setdefault("tool_config", {}).setdefault("read_file", {})[
            "paste_delivery"] = enabled

    def test_on_and_known_type_pastes(self):
        """开关开启且类型在清单内：走粘贴。"""
        self._set(True)
        self.assertTrue(should_paste("a.py"))

    def test_on_and_unknown_type_inlines(self):
        """开关开启但类型不在清单内：走直返。"""
        self._set(True)
        self.assertFalse(should_paste("a.weirdfmt"))

    def test_off_and_known_type_inlines(self):
        """开关关闭：即使类型在清单内也走直返。"""
        self._set(False)
        self.assertFalse(should_paste("a.py"))


if __name__ == "__main__":
    unittest.main()
