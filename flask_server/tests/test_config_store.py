"""主配置读写：定义/运行时合并与回写的边界测试。

背景：
    config_store 把 definition.yaml（定义）与 runtime.yaml（运行时）合并成
    完整 CONFIG，并负责回写。它是所有功能的配置入口，读写错会连锁影响全局。
    此前无任何测试。

隔离策略：
    config_file 在导入时读取 CHAT_BRIDGE_CONFIG_DIR 决定配置目录。测试在
    setUp 里设置该环境变量并重载 config_file / config_store，使读写落在临时
    目录，结束后清除环境变量并重载复原。

验证目标：
    1. _tool_entry_for：补齐 enabled、run_command 补齐 languages；
    2. init_config：关键字段兜底默认值、每个内置工具都有开关；
    3. save_config_to_yaml + load_yaml_config：往返一致，定义入 definition、
       运行时入 runtime；
    4. 运行时字段覆盖定义中的同名字段。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_config_store -v
"""
import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import runtime
import config_file
import config_store


class _CfgBase(unittest.TestCase):
    """把配置目录重定向到临时目录，测试互不干扰、不碰真实配置。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cfgstore_test_")
        os.environ["CHAT_BRIDGE_CONFIG_DIR"] = self.tmp
        # 重载以读取新的配置目录（config_file 在导入时确定路径）
        importlib.reload(config_file)
        importlib.reload(config_store)
        self._orig_tools = dict(runtime.TOOLS)
        self._orig_config = dict(runtime.CONFIG)

    def tearDown(self):
        os.environ.pop("CHAT_BRIDGE_CONFIG_DIR", None)
        importlib.reload(config_file)
        importlib.reload(config_store)
        runtime.TOOLS = self._orig_tools
        runtime.CONFIG = self._orig_config
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_isolation(self):
        """隔离自检：配置路径必须落在临时目录内。"""
        self.assertEqual(os.path.realpath(str(config_file.DEFINITION_PATH.parent)),
                         os.path.realpath(self.tmp))


class TestToolEntry(_CfgBase):
    """_tool_entry_for：为单个工具补齐配置项。"""

    def test_default_enabled_true(self):
        """未声明 enabled 时默认为真。"""
        entry = config_store._tool_entry_for("read_file", {})
        self.assertTrue(entry["enabled"])

    def test_explicit_enabled_false(self):
        """显式 enabled=false 应保留为假。"""
        entry = config_store._tool_entry_for("read_file", {"enabled": False})
        self.assertFalse(entry["enabled"])

    def test_run_command_gets_languages(self):
        """run_command 应补齐语言清单。"""
        runtime.impl = None   # 无实现模块时退回内置默认语言
        entry = config_store._tool_entry_for("run_command", {"languages": ["PYTHON", "Git"]})
        self.assertEqual(entry["languages"], ["python", "git"])


class TestInitConfig(_CfgBase):
    """init_config：合并与兜底。"""

    def test_fallback_defaults(self):
        """空配置时，关键字段应取兜底默认值。"""
        runtime.TOOLS = {}
        cfg = config_store.init_config()
        self.assertEqual(cfg["flask"]["host"], "127.0.0.1")
        self.assertEqual(cfg["flask"]["port"], 5000)
        self.assertEqual(cfg["limits"]["max_json_chars"], 100000)

    def test_every_tool_has_enabled(self):
        """每个内置工具都应补上 enabled 开关。"""
        runtime.TOOLS = {"read_file": {}, "run_command": {}}
        cfg = config_store.init_config()
        self.assertIn("enabled", cfg["tools"]["read_file"])
        self.assertIn("enabled", cfg["tools"]["run_command"])


class TestSaveAndLoad(_CfgBase):
    """回写与回读：定义入 definition、运行时入 runtime。"""

    def test_save_then_load_roundtrip(self):
        """保存后回读，端口与工具开关应一致。"""
        runtime.TOOLS = {"read_file": {}, "run_command": {}}
        runtime.CONFIG = {
            "flask": {"host": "0.0.0.0", "port": 5001},
            "limits": {"max_json_chars": 123456},
            "default_profile": "glm",
            "site_profiles": {"a.com": "glm"},
            "tools": {"read_file": {"enabled": False},
                      "run_command": {"enabled": True, "languages": ["python"]}},
        }
        ok = config_store.save_config_to_yaml()
        self.assertTrue(ok)
        loaded = config_store.load_yaml_config()
        # 运行时字段
        self.assertEqual(loaded["flask"]["port"], 5001)
        self.assertFalse(loaded["tools"]["read_file"]["enabled"])
        # 定义字段
        self.assertEqual(loaded["flask"]["host"], "0.0.0.0")
        self.assertEqual(loaded["limits"]["max_json_chars"], 123456)

    def test_runtime_overrides_definition(self):
        """运行时字段应覆盖定义中的同名字段。"""
        # 定义写 host，运行时写 port，二者合并应同时存在
        config_file.update_definition_section("app", {"flask": {"host": "1.2.3.4"}})
        config_file.update_runtime_section("app", {"flask": {"port": 6000}})
        loaded = config_store.load_yaml_config()
        self.assertEqual(loaded["flask"]["host"], "1.2.3.4")
        self.assertEqual(loaded["flask"]["port"], 6000)


if __name__ == "__main__":
    unittest.main()


class TestProfiles(_CfgBase):
    """profiles：站点档案的载入、规整与回写（真源 definition.yaml）。"""

    def test_roundtrip(self):
        """档案整体往返：写入定义、init 读出、save 回写保持一致。"""
        import yaml
        data = {"app": {
            "flask": {"host": "127.0.0.1"},
            "default_profile": "glm",
            "site_profiles": {},
            "profiles": {"glm": {
                "label": "GLM", "hosts": ["chatglm.cn"], "container": ".c",
                "split": True, "newConversation": "",
            }},
        }}
        config_file.DEFINITION_PATH.write_text(
            yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
        cfg = config_store.init_config()
        self.assertEqual(cfg["profiles"]["glm"]["container"], ".c")
        self.assertEqual(cfg["profiles"]["glm"]["newConversation"], "")
        runtime.CONFIG.clear()
        runtime.CONFIG.update(cfg)
        self.assertTrue(config_store.save_config_to_yaml())
        loaded = yaml.safe_load(config_file.DEFINITION_PATH.read_text(encoding="utf-8"))
        self.assertEqual(loaded["app"]["profiles"]["glm"]["hosts"], ["chatglm.cn"])
        self.assertEqual(loaded["app"]["profiles"]["glm"]["label"], "GLM")

    def test_missing_profiles_defaults_empty(self):
        """未配置 profiles 时兜底为空字典。"""
        cfg = config_store.init_config()
        self.assertEqual(cfg["profiles"], {})

    def test_sanitize_rules(self):
        """规整：非法 id / 非字典条目丢弃；hosts 单串转列表；split 非布尔与数字丢弃。"""
        raw = {
            "glm": {"label": "GLM", "hosts": "chatglm.cn", "split": "yes",
                    "newConversation": "", "scrollToBottomButton": ["a", "b"],
                    "maxRetry": 3},
            "bad id!": {"label": "x"},
            "notdict": "junk",
        }
        out = config_store.sanitize_profiles(raw)
        self.assertEqual(set(out), {"glm"})
        self.assertEqual(out["glm"]["hosts"], ["chatglm.cn"])
        self.assertNotIn("split", out["glm"])
        self.assertNotIn("maxRetry", out["glm"])
        self.assertEqual(out["glm"]["newConversation"], "")
        self.assertEqual(out["glm"]["scrollToBottomButton"], ["a", "b"])


class TestDeriveSiteProfiles(unittest.TestCase):
    """derive_site_profiles：域名映射一律由档案 hosts 派生。

    背景：site_profiles 是冗余的历史字段，真正被消费的是每个档案自己的 hosts。
    两处分别维护必然漂移——实际发生过两次：POST /config 只带 profiles 时，
    内存里的 site_profiles 仍是旧值，写盘把文件里刚补的新站点映射覆盖掉。
    本测试锁定「映射由档案派生、不再独立维护」这条不变量。
    """

    def test_多域名档案全部展开(self):
        """一个档案可声明多个域名，每个都映射到它。"""
        out = config_store.derive_site_profiles({
            "glm": {"hosts": ["chatglm.cn", "chatglm.com"]},
            "deepseek": {"hosts": ["deepseek.com"]},
        })
        self.assertEqual(out, {
            "chatglm.cn": "glm",
            "chatglm.com": "glm",
            "deepseek.com": "deepseek",
        })

    def test_新增站点自动进入映射(self):
        """新增站点只要写了 hosts，映射自动出现，无需另改 site_profiles。"""
        out = config_store.derive_site_profiles({
            "yuanbao": {"hosts": ["yuanbao.tencent.com"]},
        })
        self.assertEqual(out.get("yuanbao.tencent.com"), "yuanbao")

    def test_hosts_为字符串时按单元素处理(self):
        """hosts 容忍字符串写法，不因类型宽松而丢映射。"""
        out = config_store.derive_site_profiles({"x": {"hosts": "x.com"}})
        self.assertEqual(out, {"x.com": "x"})

    def test_空与非法输入不抛异常(self):
        """档案集为空 / 非字典 / 条目非法时安全返回空映射。"""
        self.assertEqual(config_store.derive_site_profiles(None), {})
        self.assertEqual(config_store.derive_site_profiles([]), {})
        self.assertEqual(config_store.derive_site_profiles({"a": "junk"}), {})
        self.assertEqual(config_store.derive_site_profiles({"a": {}}), {})

    def test_域名大小写与空白被规整(self):
        """域名统一小写去空白，避免大小写差异导致匹配失败。"""
        out = config_store.derive_site_profiles({"a": {"hosts": [" A.COM ", ""]}})
        self.assertEqual(out, {"a.com": "a"})
