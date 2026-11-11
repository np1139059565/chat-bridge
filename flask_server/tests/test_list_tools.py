"""list_tools 工具的行为测试。

为什么需要这个文件：
    list_tools 是 AI 发现自己有哪些工具可用的唯一正规入口。它一旦返回空表，
    或把已下线的工具、指令执行端混进来，AI 就会调用不存在的工具、或把指令
    当成工具执行。本文件把这些口径固定下来，避免以后改目录逻辑时静默退化。
"""
import unittest

from app import create_app
from tools import tools_impl
from tools.list_tools_impl import _has_params
from tool_meta import TOOLS


class TestListTools(unittest.TestCase):
    """验证工具清单的内容与过滤口径。"""

    @classmethod
    def setUpClass(cls):
        """建立应用上下文：工具上线状态取自配置，裸调用会一律判为下线。"""
        cls.app = create_app()
        cls.ctx = cls.app.app_context()
        cls.ctx.push()

    @classmethod
    def tearDownClass(cls):
        """退出上下文，避免影响其它用例。"""
        cls.ctx.pop()

    def test_returns_non_empty_catalog(self):
        """清单不能为空：空表等于 AI 看不到任何工具。"""
        res = tools_impl.t_list_tools({})
        self.assertGreater(res["count"], 0)
        self.assertEqual(res["count"], len(res["tools"]))

    def test_contains_itself_and_core_tools(self):
        """清单必须包含自身与常用文件工具，便于 AI 二次查询参数。"""
        names = [t["name"] for t in tools_impl.t_list_tools({})["tools"]]
        self.assertIn("list_tools", names)
        self.assertIn("get_tool_params", names)
        self.assertIn("read_file", names)

    def test_each_entry_has_required_fields(self):
        """每项都要有名称、说明与有无参数标记，缺项会让 AI 无从判断。"""
        for item in tools_impl.t_list_tools({})["tools"]:
            self.assertTrue(item.get("name"))
            self.assertIn("description", item)
            self.assertIn("has_params", item)

    def test_names_are_unique(self):
        """名称不得重复：同一工具从多条来源并入时只能出现一次。"""
        names = [t["name"] for t in tools_impl.t_list_tools({})["tools"]]
        self.assertEqual(len(names), len(set(names)))

    def test_sorted_by_name(self):
        """结果按名称排序，保证多次调用顺序一致、便于比对。"""
        names = [t["name"] for t in tools_impl.t_list_tools({})["tools"]]
        self.assertEqual(names, sorted(names))

    def test_disabled_tool_excluded(self):
        """已下线的内置工具不得出现在清单中，否则 AI 会调用必失败的接口。"""
        import runtime
        # 临时挑一个未在清单中的内置工具：若全部都在线则跳过该断言
        names = {t["name"] for t in tools_impl.t_list_tools({})["tools"]}
        offline = [k for k in TOOLS if not runtime.is_tool_enabled(k)]
        for k in offline:
            self.assertNotIn(k, names)

    def test_registered_in_dispatch(self):
        """必须在派发表中登记，否则工具能列出却无法调用。"""
        self.assertIn("list_tools", tools_impl.DISPATCH)

    def test_has_params_empty_schema_vs_param_schema(self):
        """空参数 schema 判 False、有参数 schema 判 True（Q-7 回归固定）。

        迁移到 JSON Schema 后，无参工具的 parameters 是空 properties 的
        object schema，按 parameters 本身判真假会把无参工具误报成有参，
        诱导 AI 多做一次 get_tool_params 查询。本用例固定对照口径，
        并覆盖历史数组格式的兼容判断。
        """
        names = {t["name"]: t["has_params"]
                 for t in tools_impl.t_list_tools({})["tools"]}
        # 空参数 schema：清单/规则/技能三个无参工具不得误报有参
        for name in ("list_tools", "list_rules", "list_skills"):
            self.assertIn(name, names)
            self.assertFalse(names[name],
                              name + " 空参数 schema 应判 has_params=False")
        # 有参数 schema：get_tool_params 要 tool_id、read_file 要 path
        for name in ("get_tool_params", "read_file"):
            self.assertIn(name, names)
            self.assertTrue(names[name],
                             name + " 有参数 schema 应判 has_params=True")
        # 历史数组格式兼容：非空数组仍有参；空数组、空 schema、缺键均无参
        empty_schema = {"type": "object", "properties": {}}
        path_schema = {"type": "object", "properties": {"path": {}}}
        self.assertTrue(_has_params({"parameters": [{"name": "path"}]}))
        self.assertFalse(_has_params({"parameters": []}))
        self.assertFalse(_has_params({"parameters": empty_schema}))
        self.assertTrue(_has_params({"parameters": path_schema}))
        self.assertFalse(_has_params({}))


if __name__ == "__main__":
    unittest.main()
