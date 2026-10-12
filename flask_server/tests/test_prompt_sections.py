"""技能数据收集：System Prompt 技能清单与管理视图的测试。

背景：
    prompt_sections 决定哪些技能进入 System Prompt 的技能清单，以及设置页的完整
    技能视图。技能的上下线由技能自身的开关决定（见 custom_tools.skills），与
    「有没有工具」无关——没有工具、只有说明文档的技能同样可上线并注入说明。
    口径不一致会让 AI 看到不该看的技能或漏掉该看的技能。

隔离策略：
    用 unittest.mock 替换外部依赖：本模块的工具表（ct.load_tools / list_skills）
    以及技能级判定（custom_tools.skills 的 is_skill_online / skill_dir_map）。
    只验证本模块的筛选与整形逻辑，不触碰真实技能目录与真实配置。

验证目标：
    1. _tools_by_skill：只统计已上线且 kind=tool 的工具；
    2. skills：按技能开关判定；无工具但在线的技能也纳入（tools 为空）；
    3. skills_manage：覆盖全部技能，带工具计数、启用计数与技能自身开关；
    4. _manage_row：工具按名排序、计数正确、开关透传。

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
import custom_tools.skills as ct_skills


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

    def _patches(self, tools, dirs, online, summaries):
        """统一替换：工具表、技能目录、技能开关、技能摘要。"""
        return [
            mock.patch.object(prompt_sections.ct, "load_tools", return_value=tools),
            mock.patch.object(ct_skills, "skill_dir_map", return_value=dirs),
            mock.patch.object(ct_skills, "is_skill_online",
                              side_effect=lambda n: n in online),
            mock.patch.object(prompt_sections, "list_skills", return_value=summaries),
        ]

    def test_excludes_offline_skill(self):
        """技能开关关闭时，不纳入清单。"""
        tools = {"t1": {"name": "t1", "skill_name": "s1", "enabled": True}}
        ps = self._patches(tools, {"s1": "x"}, set(), [{"name": "s1", "summary": "x"}])
        with ps[0], ps[1], ps[2], ps[3]:
            out = prompt_sections.skills()
        self.assertEqual(out, [])

    def test_includes_online_skill_with_tools(self):
        """已上线技能应纳入，并带上其已上线工具名。"""
        tools = {"t1": {"name": "t1", "skill_name": "s1", "enabled": True}}
        ps = self._patches(tools, {"s1": "x"}, {"s1"},
                           [{"name": "s1", "summary": "摘要"}])
        with ps[0], ps[1], ps[2], ps[3]:
            out = prompt_sections.skills()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "s1")
        self.assertEqual(out[0]["tools"], ["t1"])

    def test_includes_online_skill_without_tools(self):
        """无工具但在线的技能也应纳入，tools 为空列表（本次修复的核心）。"""
        ps = self._patches({}, {"s1": "x"}, {"s1"},
                           [{"name": "s1", "summary": "纯文档技能"}])
        with ps[0], ps[1], ps[2], ps[3]:
            out = prompt_sections.skills()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "s1")
        self.assertEqual(out[0]["tools"], [])


class TestManageRow(unittest.TestCase):
    """设置页技能行组装。"""

    def test_sorts_tools_and_counts(self):
        """工具应按名排序，计数正确，技能开关透传。"""
        tools = [{"name": "b", "enabled": True}, {"name": "a", "enabled": False}]
        row = prompt_sections._manage_row("s1", tools, {"s1": "摘要"}, True)
        self.assertEqual([t["name"] for t in row["tools"]], ["a", "b"])
        self.assertEqual(row["tool_count"], 2)
        self.assertEqual(row["enabled_count"], 1)
        self.assertEqual(row["doc_file"], "SKILL.md")
        self.assertTrue(row["enabled"])

    def test_empty_skill_row(self):
        """无工具技能的行：工具数为 0，但开关状态照常携带。"""
        row = prompt_sections._manage_row("s2", [], {}, False)
        self.assertEqual(row["tool_count"], 0)
        self.assertEqual(row["enabled_count"], 0)
        self.assertFalse(row["enabled"])


class TestSkillsManage(unittest.TestCase):
    """设置页完整技能视图。"""

    def _patches(self, tools, dirs, online, summaries):
        return [
            mock.patch.object(prompt_sections.ct, "load_tools", return_value=tools),
            mock.patch.object(ct_skills, "skill_dir_map", return_value=dirs),
            mock.patch.object(ct_skills, "is_skill_online",
                              side_effect=lambda n: n in online),
            mock.patch.object(prompt_sections, "list_skills", return_value=summaries),
        ]

    def test_includes_all_skills(self):
        """应覆盖全部技能目录，含无工具的技能。"""
        tools = {"t1": {"name": "t1", "skill_name": "s1", "enabled": True}}
        ps = self._patches(tools, {"s1": "x", "s2": "y"}, {"s1"},
                           [{"name": "s1", "summary": "摘要"}])
        with ps[0], ps[1], ps[2], ps[3]:
            out = prompt_sections.skills_manage()
        names = [r["name"] for r in out]
        self.assertIn("s1", names)
        self.assertIn("s2", names)   # 无工具的技能也应出现

    def test_offline_tools_still_listed(self):
        """设置页应列出已下线工具，供界面操作。"""
        tools = {"t1": {"name": "t1", "skill_name": "s1", "enabled": False}}
        ps = self._patches(tools, {"s1": "x"}, set(), [])
        with ps[0], ps[1], ps[2], ps[3]:
            out = prompt_sections.skills_manage()
        s1 = [r for r in out if r["name"] == "s1"][0]
        self.assertEqual(s1["tool_count"], 1)
        self.assertEqual(s1["enabled_count"], 0)


if __name__ == "__main__":
    unittest.main()
