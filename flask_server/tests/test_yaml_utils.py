"""YAML 公共原语：标量转换、注释剥离、引号转义、分区合并的边界测试。

背景：
    yaml_utils 集中了主配置与自定义工具配置两套受限解析器共用的底层函数，
    以及 config_store / load_config_dict 共用的分区合并核心。此前无任何测试。

验证目标：
    1. coerce_scalar：布尔、null、整数、浮点、引号字符串与转义还原；
    2. strip_comment：行首/空白后的 # 截断、引号内 # 保留；
    3. quote：反斜杠与双引号转义；
    4. merge_app_sections：运行时字段覆盖定义、空运行时原样返回。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_yaml_utils -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import yaml_utils


class TestCoerceScalar(unittest.TestCase):
    """标量转换。"""

    def test_booleans(self):
        """true / false（大小写不敏感）转布尔。"""
        self.assertIs(yaml_utils.coerce_scalar("true"), True)
        self.assertIs(yaml_utils.coerce_scalar("False"), False)

    def test_null_markers(self):
        """null / ~ / 空串转 None。"""
        self.assertIsNone(yaml_utils.coerce_scalar("null"))
        self.assertIsNone(yaml_utils.coerce_scalar("~"))
        self.assertIsNone(yaml_utils.coerce_scalar(""))

    def test_integer(self):
        """整数串转 int。"""
        self.assertEqual(yaml_utils.coerce_scalar("42"), 42)
        self.assertIsInstance(yaml_utils.coerce_scalar("42"), int)

    def test_float(self):
        """浮点串转 float。"""
        self.assertEqual(yaml_utils.coerce_scalar("3.14"), 3.14)

    def test_plain_string_stays(self):
        """普通文本原样返回字符串。"""
        self.assertEqual(yaml_utils.coerce_scalar("hello"), "hello")

    def test_double_quoted_string(self):
        """双引号包裹的内容去引号。"""
        self.assertEqual(yaml_utils.coerce_scalar('"hello"'), "hello")

    def test_quoted_number_stays_string(self):
        """引号内的数字保持字符串，不参与数值转换。"""
        self.assertEqual(yaml_utils.coerce_scalar('"42"'), "42")

    def test_escape_restore(self):
        """引号内的转义应还原。"""
        self.assertEqual(yaml_utils.coerce_scalar('"a\\"b"'), 'a"b')

    def test_strips_surrounding_space(self):
        """首尾空白应先被去除。"""
        self.assertEqual(yaml_utils.coerce_scalar("  42  "), 42)


class TestStripComment(unittest.TestCase):
    """注释剥离。"""

    def test_hash_after_space_truncates(self):
        """空白之后的 # 起注释作用，应截断。"""
        self.assertEqual(yaml_utils.strip_comment("key: value # 注释"), "key: value")

    def test_hash_at_start(self):
        """行首 # 整行注释，结果为空。"""
        self.assertEqual(yaml_utils.strip_comment("# 整行注释"), "")

    def test_hash_inside_quotes_kept(self):
        """引号内的 # 不是注释，应保留。"""
        self.assertEqual(yaml_utils.strip_comment('desc: "含 # 号"'), 'desc: "含 # 号"')

    def test_hash_without_space_kept(self):
        """紧贴内容的 # 不视为注释（如 a#b）。"""
        self.assertEqual(yaml_utils.strip_comment("a#b"), "a#b")

    def test_trailing_space_removed(self):
        """结果应去掉尾部空白。"""
        self.assertEqual(yaml_utils.strip_comment("key: v   "), "key: v")


class TestQuote(unittest.TestCase):
    """写出时的引号转义。"""

    def test_plain_wrapped_in_quotes(self):
        """普通字符串应被双引号包裹。"""
        self.assertEqual(yaml_utils.quote("hello"), '"hello"')

    def test_double_quote_escaped(self):
        """内部双引号应转义。"""
        self.assertEqual(yaml_utils.quote('a"b'), '"a\\"b"')

    def test_backslash_escaped(self):
        """反斜杠应转义。"""
        self.assertEqual(yaml_utils.quote("a\\b"), '"a\\\\b"')


class TestMergeAppSections(unittest.TestCase):
    """分区合并。"""

    def test_empty_runtime_returns_base(self):
        """运行时为空时原样返回定义。"""
        base = {"flask": {"host": "a"}}
        self.assertIs(yaml_utils.merge_app_sections(base, {}), base)
        self.assertEqual(base, {"flask": {"host": "a"}})

    def test_runtime_overrides_flask(self):
        """运行时 flask 字段覆盖定义中的同名项。"""
        base = {"flask": {"host": "a", "port": 1}}
        yaml_utils.merge_app_sections(base, {"flask": {"port": 2}})
        self.assertEqual(base["flask"]["host"], "a")
        self.assertEqual(base["flask"]["port"], 2)

    def test_runtime_overrides_tool_field(self):
        """运行时 tools 字段逐工具覆盖。"""
        base = {"tools": {"read_file": {"enabled": True, "note": "x"}}}
        yaml_utils.merge_app_sections(base, {"tools": {"read_file": {"enabled": False}}})
        self.assertFalse(base["tools"]["read_file"]["enabled"])
        self.assertEqual(base["tools"]["read_file"]["note"], "x")

    def test_adds_new_tool_from_runtime(self):
        """运行时出现的新工具应并入结果。"""
        base = {"tools": {}}
        yaml_utils.merge_app_sections(base, {"tools": {"new_tool": {"enabled": True}}})
        self.assertIn("new_tool", base["tools"])


if __name__ == "__main__":
    unittest.main()
