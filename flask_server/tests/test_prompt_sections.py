"""技能数据收集：System Prompt 技能清单与管理视图的测试。

背景：
    prompt_sections 决定哪些技能进入 System Prompt 的技能清单（只含已上线且有
    说明文档的），以及设置页的完整技能视图。口径不一致会让 AI 看到不该看的技能
    或漏掉该看的技能。此前无任何测试。

隔离策略：
    用 unittest.mock 替换外部依赖（load_tools / list_skills / _skill_dirs），
    只验证本模块的筛选与整形逻辑，不触碰真实技能目录。

验证目标：
    1. _tools_by_skill：只统计已上线且 kind=tool 的工具；
    2. skills：无已上线工具的技能被排除；含说明文档的技能被纳入并带工具名；
    3. skills_manage：覆盖全部技能，带工具计数与启用计数；
    4. _manage_row：工具按名排序、计数正确。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_prompt_sections -v
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import prompt_sections


class TestToolsBySkill(unittest.TestCase):
    """按技能归集已上线工具。"""

    def _patch(self, tools):
        return mock.patch.object(prompt_sections.ct, "load_tools", return_value=tools)

    def test_only_enabled_counted(self):
        """只统计已上线的工具。"""
        tools = {
            "t1": {"name": "t1", "skill_name": "s1", "enabled": True},
            "t2": {"name": "t2", "skill_name": "s1", "enabled": False},
        }
        with self._patch(tools):
            out = prompt_sections._tools_by_skill()
        self.assertEqual(out["s1"], ["t1"])

    def test_command_action_excluded(self):
        """kind 非 tool 的指令端不进入归集。"""
        tools = {"c1": {"name": "c1", "skill_name": "s1", "enabled": True,
                         "kind": "command_action"}}
        with self._patch(tools):
            out = prompt_sections._tools_by_skill()
        self.assertEqual(out, {})

    def test_missing_skill_name_excluded(self):
        """无 skill_name 的工具不归集。"""
        tools = {"t1": {"name": "t1", "enabled": True}}
        with self._patch(tools):
            out = prompt_sections._tools_by_skill()
        self.assertEqual(out, {})


class TestSkills(unittest.TestCase):
    """System Prompt 技能清单。"""

    def test_excludes_skill_without_enabled_tools(self):
        """无已上线工具的技能不应出现在清单里。"""
        tools = {"t1": {"name": "t1", "skill_name": "s1", "enabled": False}}
        with mock.patch.object(prompt_sections.ct, "load_tools", return_value=tools), \
             mock.patch.object(prompt_sections, "list_skills",
                               return_value=[{"name": "s1", "summary": "x"}]):
            out = prompt_sections.skills()
        self.assertEqual(out, [])

    def test_includes_skill_with_tools(self):
        """有已上线工具的技能应纳入，并带上工具名。"""
        tools = {"t1": {"name": "t1", "skill_name": "s1", "enabled": True}}
        with mock.patch.object(prompt_sections.ct, "load_tools", return_value=tools), \
             mock.patch.object(prompt_sections, "list_skills",
                               return_value=[{"name": "s1", "summary": "摘要"}]):
            out = prompt_sections.skills()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "s1")
        self.assertEqual(out[0]["tools"], ["t1"])


class TestManageRow(unittest.TestCase):
    """设置页技能行组装。"""

    def test_sorts_tools_and_counts(self):
        """工具应按名排序，计数正确。"""
        tools = [{"name": "b", "enabled": True}, {"name": "a", "enabled": False}]
        row = prompt_sections._manage_row("s1", tools, {"s1": "摘要"})
        self.assertEqual([t["name"] for t in row["tools"]], ["a", "b"])
        self.assertEqual(row["tool_count"], 2)
        self.assertEqual(row["enabled_count"], 1)
        self.assertEqual(row["doc_file"], "SKILL.md")


class TestSkillsManage(unittest.TestCase):
    """设置页完整技能视图。"""

    def test_includes_all_skills(self):
        """应覆盖全部技能目录，含无工具的技能。"""
        tools = {"t1": {"name": "t1", "skill_name": "s1", "enabled": True}}
        with mock.patch.object(prompt_sections.ct, "load_tools", return_value=tools), \
             mock.patch.object(prompt_sections, "list_skills",
                               return_value=[{"name": "s1", "summary": "摘要"}]), \
             mock.patch.object(prompt_sections, "_skill_dirs",
                               return_value=["s1", "s2"]):
            out = prompt_sections.skills_manage()
        names = [r["name"] for r in out]
        self.assertIn("s1", names)
        self.assertIn("s2", names)   # 无工具的技能也应出现

    def test_offline_tools_still_listed(self):
        """设置页应列出已下线工具，供界面操作。"""
        tools = {"t1": {"name": "t1", "skill_name": "s1", "enabled": False}}
        with mock.patch.object(prompt_sections.ct, "load_tools", return_value=tools), \
             mock.patch.object(prompt_sections, "list_skills", return_value=[]), \
             mock.patch.object(prompt_sections, "_skill_dirs", return_value=[]):
            out = prompt_sections.skills_manage()
        s1 = [r for r in out if r["name"] == "s1"][0]
        self.assertEqual(s1["tool_count"], 1)
        self.assertEqual(s1["enabled_count"], 0)


if __name__ == "__main__":
    unittest.main()
