"""指令注册表测试（command_registry 执行路径）

背景：
  该模块负责自定义指令的保存校验。校验口径若与分发口径不一致，会出现
  「能执行的指令存不下来」或「存下来了却执行不了」。文件里专门强调：
  校验必须含外部指令，因为分发时会查外部指令表。

覆盖点：
  1. 命令名格式：必须以 / 开头
  2. 重名校验：与内置、别名、其它自定义指令冲突
  3. 修改时排除自身（否则改自己的名字会被判成重复）
  4. 组合指令的子指令必须存在
  5. 校验口径与分发口径一致：外部指令算存在
  6. help_text 分组输出

运行：python -m pytest tests/test_command_registry.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import command_registry as cr
from remote_bridge import bridge_store


class ResolveCmdTest(unittest.TestCase):
    """别名解析。"""

    def test_alias_mapped(self):
        """别名归一为主名。"""
        self.assertEqual(cr.resolve_cmd("/sp"), "/screenshot")

    def test_main_unchanged(self):
        """主名原样返回。"""
        self.assertEqual(cr.resolve_cmd("/screenshot"), "/screenshot")

    def test_unknown_unchanged(self):
        """未知命令原样返回。"""
        self.assertEqual(cr.resolve_cmd("/xyz"), "/xyz")

    def test_all_aliases_map_to_builtin(self):
        """每个别名都能映回一个存在的内置指令——别名表与指令表不能脱节。"""
        for alias, main in cr._ALIAS_MAP.items():
            self.assertIn(main, cr.BUILTIN, "别名 %s 指向不存在的指令 %s" % (alias, main))


class ValidateCommandTest(unittest.TestCase):
    """自定义指令保存校验。"""

    def setUp(self):
        """替换配置读取，避免依赖真实配置。"""
        self._orig = bridge_store.get_config
        self._customs = []
        bridge_store.get_config = lambda: {"commands": self._customs}

    def tearDown(self):
        """还原。"""
        bridge_store.get_config = self._orig

    def test_name_must_start_with_slash(self):
        """命令名不以 / 开头时报错。"""
        err = cr.validate_command({"name": "nodash"})
        self.assertIn("以 / 开头", err)

    def test_empty_name_rejected(self):
        """空命令名报错（不是以 / 开头）。"""
        self.assertIn("以 / 开头", cr.validate_command({"name": ""}))

    def test_conflict_with_builtin(self):
        """与内置指令冲突时报错。"""
        err = cr.validate_command({"name": "/screenshot"})
        self.assertIn("内置指令冲突", err)

    def test_conflict_with_builtin_alias(self):
        """与内置指令的别名冲突同样报错。"""
        err = cr.validate_command({"name": "/sp"})
        self.assertIn("内置指令冲突", err)

    def test_conflict_with_other_custom(self):
        """与其它自定义指令冲突时报错。"""
        self._customs = [{"name": "/mine", "label": "我的"}]
        err = cr.validate_command({"name": "/mine"})
        self.assertIn("已存在", err)

    def test_conflict_with_other_custom_alias(self):
        """与其它自定义指令的别名冲突同样报错。

        别名选 /myalias：不能用 /m 这类短名，它们多半已被内置指令占用，
        那样测到的是「与内置冲突」而不是「与其它自定义冲突」。
        """
        self._customs = [{"name": "/mine", "aliases": ["/myalias"]}]
        self.assertIn("已存在", cr.validate_command({"name": "/myalias"}))

    def test_editing_self_not_conflict(self):
        """修改自己时排除自身，不判成重复。"""
        self._customs = [{"name": "/mine", "label": "我的"}]
        self.assertEqual(cr.validate_command({"name": "/mine"}, index=0), "")

    def test_valid_new_command(self):
        """全新的合法命令通过校验。"""
        self.assertEqual(cr.validate_command({"name": "/brand-new"}), "")

    def test_case_insensitive_conflict(self):
        """重名比对不区分大小写。"""
        self._customs = [{"name": "/Mine"}]
        self.assertIn("已存在", cr.validate_command({"name": "/mine"}))


class ComboStepsTest(unittest.TestCase):
    """组合指令的子指令存在性校验。"""

    def setUp(self):
        """替换配置读取与外部指令来源。"""
        self._orig_cfg = bridge_store.get_config
        self._customs = []
        bridge_store.get_config = lambda: {"commands": self._customs}
        import custom_tools.commands as ext
        self._orig_ext = ext.external_command_names

    def tearDown(self):
        """还原。"""
        bridge_store.get_config = self._orig_cfg
        import custom_tools.commands as ext
        ext.external_command_names = self._orig_ext

    def _stub_external(self, names):
        """替换外部指令名集合。

        @param names 名字集合
        """
        import custom_tools.commands as ext
        ext.external_command_names = lambda: set(names)

    def test_builtin_subcommand_ok(self):
        """引用内置指令作为子指令：合法。"""
        self._stub_external([])
        self.assertEqual(cr.validate_command(
            {"name": "/combo", "steps": ["/screenshot"]}), "")

    def test_alias_subcommand_ok(self):
        """引用内置指令的别名：合法。"""
        self._stub_external([])
        self.assertEqual(cr.validate_command(
            {"name": "/combo", "steps": ["/sp"]}), "")

    def test_external_subcommand_ok(self):
        """引用外部指令：合法。

        这是文件里强调的口径一致：分发时会查外部指令表，
        校验时若漏掉它们，用户引用一个能执行的指令却被判定不存在。
        """
        self._stub_external(["/dc"])
        self.assertEqual(cr.validate_command(
            {"name": "/combo", "steps": ["/dc"]}), "")

    def test_other_custom_subcommand_ok(self):
        """引用其它自定义指令：合法。"""
        self._stub_external([])
        self._customs = [{"name": "/other"}]
        self.assertEqual(cr.validate_command(
            {"name": "/combo", "steps": ["/other"]}), "")

    def test_missing_subcommand_rejected(self):
        """引用不存在的子指令：报错。"""
        self._stub_external([])
        err = cr.validate_command({"name": "/combo", "steps": ["/nosuch"]})
        self.assertIn("不存在", err)

    def test_subcommand_with_args_stripped(self):
        """子指令带参数时只取命令名部分判定。"""
        self._stub_external([])
        self.assertEqual(cr.validate_command(
            {"name": "/combo", "steps": ["/screenshot 参数"]}), "")

    def test_empty_step_skipped(self):
        """空步骤被跳过，不判成不存在。"""
        self._stub_external([])
        self.assertEqual(cr.validate_command(
            {"name": "/combo", "steps": ["  "]}), "")


class HelpTextTest(unittest.TestCase):
    """指令列表输出。"""

    def setUp(self):
        """替换配置与外部指令来源。"""
        self._orig = bridge_store.get_config
        bridge_store.get_config = lambda: {"commands": []}
        import custom_tools.commands as ext
        self._orig_ext = ext.list_external_commands
        ext.list_external_commands = lambda: []

    def tearDown(self):
        """还原。"""
        bridge_store.get_config = self._orig
        import custom_tools.commands as ext
        ext.list_external_commands = self._orig_ext

    def test_contains_builtin_groups(self):
        """输出含内置指令的分组标题。"""
        text = cr.help_text()
        for g in ("抽屉外观", "会话管理", "卡片与结果"):
            self.assertIn(g, text)

    def test_contains_shortcut_and_fullname(self):
        """有别名时同时显示快捷键与完整名。"""
        text = cr.help_text()
        self.assertIn("/sp", text)
        self.assertIn("/screenshot", text)

    def test_custom_combo_expands_steps(self):
        """自定义组合指令逐条展开子步骤。"""
        bridge_store.get_config = lambda: {"commands": [
            {"name": "/mycombo", "label": "我的组合", "steps": ["/sp", "/rs"]}]}
        text = cr.help_text()
        self.assertIn("/mycombo", text)
        self.assertIn("1. /sp", text)
        self.assertIn("2. /rs", text)


if __name__ == "__main__":
    unittest.main()
