"""配置读写底座：分区读取、更新、缺失文件兜底的测试。

背景：
    config_file 是所有配置读写的统一入口（definition.yaml + runtime.yaml 的
    分区读写）。它读写错会连锁影响全部功能。此前无任何测试。

隔离策略：
    config_file 在导入时读取 CHAT_BRIDGE_CONFIG_DIR 决定配置目录。测试设置
    该环境变量并重载 config_file，使读写落在临时目录；结束后清除并重载复原。

验证目标：
    1. 文件缺失时各 get_* 返回空字典，不抛异常；
    2. update_definition_section / update_runtime_section 写入后可回读；
    3. 更新只替换目标分区，保留同一文件内的其它分区；
    4. definition 与 runtime 分区互相独立，同名分区各取各的。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_config_file -v
"""
import importlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import config_file


class _CfgBase(unittest.TestCase):
    """把配置目录重定向到临时目录。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cfgfile_test_")
        os.environ["CHAT_BRIDGE_CONFIG_DIR"] = self.tmp
        importlib.reload(config_file)

    def tearDown(self):
        os.environ.pop("CHAT_BRIDGE_CONFIG_DIR", None)
        importlib.reload(config_file)
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestMissingFile(unittest.TestCase):
    """文件缺失时的兜底（不重定向，避免影响其它用例的模块状态）。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cfgfile_missing_")
        os.environ["CHAT_BRIDGE_CONFIG_DIR"] = self.tmp
        importlib.reload(config_file)

    def tearDown(self):
        os.environ.pop("CHAT_BRIDGE_CONFIG_DIR", None)
        importlib.reload(config_file)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_sections_empty(self):
        """文件不存在时各 get_* 返回空字典。"""
        self.assertEqual(config_file.get_definition_section("app"), {})
        self.assertEqual(config_file.get_runtime_section("app"), {})
        self.assertEqual(config_file.load_definition(), {})
        self.assertEqual(config_file.load_runtime(), {})


class TestUpdateAndRead(_CfgBase):
    """更新与回读。"""

    def test_definition_roundtrip(self):
        """写定义分区后可回读。"""
        ok = config_file.update_definition_section("app", {"flask": {"host": "1.1.1.1"}})
        self.assertTrue(ok)
        self.assertEqual(config_file.get_definition_section("app")["flask"]["host"], "1.1.1.1")

    def test_runtime_roundtrip(self):
        """写运行时分区后可回读。"""
        ok = config_file.update_runtime_section("app", {"flask": {"port": 7000}})
        self.assertTrue(ok)
        self.assertEqual(config_file.get_runtime_section("app")["flask"]["port"], 7000)

    def test_update_preserves_other_sections(self):
        """更新一个分区不应覆盖同文件内的其它分区。"""
        config_file.update_definition_section("app", {"flask": {"host": "a"}})
        config_file.update_definition_section("custom_tools", {"tools": []})
        # app 分区应仍在
        self.assertIn("flask", config_file.get_definition_section("app"))
        # custom_tools 分区已写入
        self.assertIn("tools", config_file.get_definition_section("custom_tools"))

    def test_definition_and_runtime_independent(self):
        """definition 与 runtime 的同名分区互不影响。"""
        config_file.update_definition_section("app", {"flask": {"host": "def-host"}})
        config_file.update_runtime_section("app", {"flask": {"port": 1234}})
        d = config_file.get_definition_section("app")
        r = config_file.get_runtime_section("app")
        self.assertEqual(d["flask"].get("host"), "def-host")
        self.assertNotIn("port", d["flask"])
        self.assertEqual(r["flask"].get("port"), 1234)
        self.assertNotIn("host", r["flask"])

    def test_update_overwrites_same_section(self):
        """对同一分区再次更新应整体替换该分区内容。"""
        config_file.update_definition_section("app", {"a": 1})
        config_file.update_definition_section("app", {"b": 2})
        section = config_file.get_definition_section("app")
        self.assertEqual(section, {"b": 2})


if __name__ == "__main__":
    unittest.main()
