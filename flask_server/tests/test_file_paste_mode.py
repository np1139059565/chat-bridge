"""read_file 投递模式：按站点禁用附件粘贴 + boolean 严格解析。"""
import os
import sys
import unittest

_ROOT = os.path.join(os.path.dirname(__file__), "..")
for _p in (_ROOT, os.path.join(_ROOT, "core"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import file_delivery
import tool_config
import runtime


class TestFilePasteMode(unittest.TestCase):
    def setUp(self):
        self._host = file_delivery._current_host
        self._paste = file_delivery.paste_enabled
        self._cfg = dict(runtime.CONFIG)
        file_delivery.paste_enabled = lambda: True

    def tearDown(self):
        file_delivery._current_host = self._host
        file_delivery.paste_enabled = self._paste
        runtime.CONFIG.clear()
        runtime.CONFIG.update(self._cfg)

    def _site(self, prof):
        runtime.CONFIG["site_profiles"] = {"arena.ai": "arena", "deepseek.com": "deepseek"}
        runtime.CONFIG["profiles"] = {"arena": prof, "deepseek": {}}

    def test_no_host_uses_global(self):
        file_delivery._current_host = lambda: ""
        self._site({})
        self.assertTrue(file_delivery.should_paste("a.md"))

    def test_site_disabled_forces_inline(self):
        file_delivery._current_host = lambda: "https://arena.ai/c/abc"
        self._site({"filePaste": False})
        self.assertFalse(file_delivery.should_paste("a.md"))

    def test_site_default_allows(self):
        file_delivery._current_host = lambda: "https://arena.ai/c/abc"
        self._site({})
        self.assertTrue(file_delivery.should_paste("a.md"))

    def test_other_site_still_pastes(self):
        file_delivery._current_host = lambda: "https://deepseek.com/chat/x"
        self._site({"filePaste": False})
        self.assertTrue(file_delivery.should_paste("a.md"))

    def test_unknown_host_falls_back(self):
        file_delivery._current_host = lambda: "https://unknown.com/x"
        self._site({"filePaste": False})
        self.assertTrue(file_delivery.should_paste("a.md"))

    def test_global_switch_off(self):
        file_delivery._current_host = lambda: ""
        file_delivery.paste_enabled = lambda: False
        self._site({})
        self.assertFalse(file_delivery.should_paste("a.md"))


class TestBooleanCoerce(unittest.TestCase):
    SPEC = {"type": "boolean", "label": "测试开关"}

    def test_string_false_is_false(self):
        self.assertIs(tool_config.coerce(self.SPEC, "false"), False)
        self.assertIs(tool_config.coerce(self.SPEC, "FALSE"), False)
        self.assertIs(tool_config.coerce(self.SPEC, "0"), False)

    def test_string_true_is_true(self):
        self.assertIs(tool_config.coerce(self.SPEC, "true"), True)
        self.assertIs(tool_config.coerce(self.SPEC, "1"), True)

    def test_real_bool_unchanged(self):
        self.assertIs(tool_config.coerce(self.SPEC, False), False)
        self.assertIs(tool_config.coerce(self.SPEC, True), True)

    def test_invalid_string_raises(self):
        with self.assertRaises(ValueError):
            tool_config.coerce(self.SPEC, "maybe")


if __name__ == "__main__":
    unittest.main()
