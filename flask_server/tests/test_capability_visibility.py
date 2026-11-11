"""能力入口常驻 + 技能下线的工具从 AI 可见清单撤出。"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(__file__), "..")
for p in (ROOT, os.path.join(ROOT, "core"), os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import system_prompt as sp
import custom_tools.meta as cmeta
import custom_tools.skills as cskills

TOOLS = {
    "a": {"name": "a", "skill_name": "skill_off", "enabled": True,
           "kind": "tool", "description": "A", "parameters": []},
    "b": {"name": "b", "skill_name": "skill_on", "enabled": True,
           "kind": "tool", "description": "B", "parameters": []},
    "c": {"name": "c", "skill_name": "", "enabled": True,
           "kind": "tool", "description": "C", "parameters": []},
}


class TestDiscoveryToolsResident(unittest.TestCase):
    def test_subject_lists_discovery_tools(self):
        text = sp.build_system_prompt()["system_prompt"]
        for n in ("list_tools", "get_tool_params", "list_skills", "read_skill",
                  "list_rules", "read_rule", "list_dir", "search_file",
                  "search_content", "read_file"):
            self.assertIn(n, text)

    def test_subject_still_no_full_tool_catalog(self):
        text = sp.build_system_prompt()["system_prompt"]
        self.assertNotIn("run_command", text)


class TestOfflineSkillToolsHidden(unittest.TestCase):
    def fake_online(self, name):
        return name != "skill_off"

    def test_offline_skill_tool_absent(self):
        with mock.patch.object(cmeta, "load_tools", return_value=TOOLS), \
             mock.patch.object(cskills, "is_skill_online", side_effect=self.fake_online):
            names = [m["name"] for m in cmeta.all_meta()]
        self.assertEqual(names, ["b", "c"])

    def test_online_skill_tool_present(self):
        with mock.patch.object(cmeta, "load_tools", return_value=TOOLS), \
             mock.patch.object(cskills, "is_skill_online", return_value=True):
            names = [m["name"] for m in cmeta.all_meta()]
        self.assertIn("a", names)

    def test_external_providers_filtered(self):
        ext = {"x": {"name": "x", "skill_name": "skill_off", "enabled": True,
                      "kind": "tool", "executor": "external", "provider": "p"}}
        with mock.patch.object(cmeta, "load_tools", return_value=ext), \
             mock.patch.object(cskills, "is_skill_online", return_value=False):
            self.assertEqual(cmeta.external_providers(), {})

    def test_manage_view_keeps_offline_tools(self):
        with mock.patch.object(cmeta, "load_tools", return_value=TOOLS):
            names = [m["name"] for m in cmeta.all_meta_full()]
        self.assertIn("a", names)


if __name__ == "__main__":
    unittest.main()
