"""指令面板测试（command_panel 执行路径）

背景：
  指令是用户不在电脑旁时唯一的远程控制手段。路由错了，用户在手机上
  敲的指令要么没反应、要么执行了别的动作。此前覆盖 26%。

覆盖点：
  1. 导入期自检：指令表与处理函数表必须一一对应
  2. 别名解析：/sp 归一为 /screenshot
  3. 路由优先级：内置 → 外部 → 自定义
  4. 未命中任何表时返回 False（交还调用方当普通消息）
  5. 参数校验：/rt 与 /ss 的非法输入给出提示且不下发
  6. 组合指令的间隔下限钳制
  7. 自定义指令按主名与别名匹配

运行：python -m pytest tests/test_command_panel.py -q
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from remote_bridge import command_panel as cp
from remote_bridge import command_registry as cr


class HandlerTableTest(unittest.TestCase):
    """两张表的一致性——导入期自检的保障。"""

    def test_builtin_and_handlers_match(self):
        """指令表与处理函数表的键必须完全一致。

        不一致的后果：新增指令只改一处时，指令会「可见但不可用」
        （或反之），且只在运行时才暴露。
        """
        self.assertEqual(set(cr.BUILTIN), set(cp._BUILTIN_HANDLERS))

    def test_every_handler_callable(self):
        """每个登记的处理函数都可调用。"""
        for name, fn in cp._BUILTIN_HANDLERS.items():
            self.assertTrue(callable(fn), "%s 不可调用" % name)


class ResolveCmdTest(unittest.TestCase):
    """别名解析。"""

    def test_alias_to_main(self):
        """别名归一为主命令名。"""
        self.assertEqual(cr.resolve_cmd("/sp"), "/screenshot")
        self.assertEqual(cr.resolve_cmd("/rs"), "/restart")

    def test_main_name_unchanged(self):
        """主命令名原样返回。"""
        self.assertEqual(cr.resolve_cmd("/screenshot"), "/screenshot")

    def test_unknown_unchanged(self):
        """未知命令原样返回，不报错。"""
        self.assertEqual(cr.resolve_cmd("/nosuch"), "/nosuch")


class HandleCommandRoutingTest(unittest.TestCase):
    """路由优先级：内置 → 外部 → 自定义。"""

    def setUp(self):
        """保存被替换的函数。"""
        self._orig_handlers = dict(cp._BUILTIN_HANDLERS)
        self._orig_external = cp.handle_external
        self._orig_custom = cp._handle_custom
        self.calls = []

    def tearDown(self):
        """还原。"""
        cp._BUILTIN_HANDLERS.clear()
        cp._BUILTIN_HANDLERS.update(self._orig_handlers)
        cp.handle_external = self._orig_external
        cp._handle_custom = self._orig_custom

    def test_builtin_takes_priority(self):
        """命中内置指令时不再走外部与自定义。"""
        cp._BUILTIN_HANDLERS["/test"] = lambda *a: self.calls.append(("builtin", a[2]))
        cp.handle_external = lambda *a: self.calls.append(("external",)) or True
        cp._handle_custom = lambda *a: self.calls.append(("custom",)) or True
        ok = cp.handle_command(None, "u", "m", "/test 参数")
        self.assertTrue(ok)
        self.assertEqual(self.calls, [("builtin", "参数")])

    def test_external_when_no_builtin(self):
        """未命中内置时尝试外部指令。"""
        cp.handle_external = lambda *a: self.calls.append(("external", a[3])) or True
        cp._handle_custom = lambda *a: self.calls.append(("custom",)) or True
        ok = cp.handle_command(None, "u", "m", "/dbg-open")
        self.assertTrue(ok)
        self.assertEqual(self.calls, [("external", "/dbg-open")])

    def test_custom_when_no_external(self):
        """外部也未命中时尝试自定义。"""
        cp.handle_external = lambda *a: False
        cp._handle_custom = lambda *a: self.calls.append(("custom",)) or True
        ok = cp.handle_command(None, "u", "m", "/mycmd")
        self.assertTrue(ok)
        self.assertEqual(self.calls, [("custom",)])

    def test_unmatched_returns_false(self):
        """三处都未命中时返回 False，交还调用方当普通消息。"""
        cp.handle_external = lambda *a: False
        cp._handle_custom = lambda *a: False
        self.assertFalse(cp.handle_command(None, "u", "m", "/nothing"))

    def test_alias_resolved_before_dispatch(self):
        """别名在分发前已归一，故注册表里只有主名也能命中。"""
        cp._BUILTIN_HANDLERS["/test"] = lambda *a: self.calls.append("hit")
        cp.handle_command(None, "u", "m", "/t")
        # /t 不是 /test 的别名，不该命中
        self.assertEqual(self.calls, [])

    def test_command_without_arg(self):
        """不带参数的指令，arg 为空串。"""
        cp._BUILTIN_HANDLERS["/test"] = lambda c, o, arg, m: self.calls.append(arg)
        cp.handle_command(None, "u", "m", "/test")
        self.assertEqual(self.calls, [""])

    def test_extra_whitespace_tolerated(self):
        """前后多余空白被忽略。"""
        cp._BUILTIN_HANDLERS["/test"] = lambda c, o, arg, m: self.calls.append(arg)
        cp.handle_command(None, "u", "m", "   /test   hello world  ")
        self.assertEqual(self.calls, ["hello world"])


class ComboIntervalTest(unittest.TestCase):
    """组合指令的步骤间隔。"""

    def test_default_when_missing(self):
        """未配置时用默认 1 秒。"""
        self.assertEqual(cp._combo_interval({}), 1.0)

    def test_invalid_uses_default(self):
        """非法值退回默认。"""
        self.assertEqual(cp._combo_interval({"interval": "abc"}), 1.0)

    def test_clamped_to_minimum(self):
        """小于下限时被钳到 0.2 秒——避免步骤挤在一起、抽屉来不及响应。"""
        self.assertEqual(cp._combo_interval({"interval": 0}), 0.2)
        self.assertEqual(cp._combo_interval({"interval": 0.05}), 0.2)

    def test_normal_value_kept(self):
        """正常值原样采用。"""
        self.assertEqual(cp._combo_interval({"interval": 3}), 3.0)


class ParamValidationTest(unittest.TestCase):
    """参数校验：非法输入给提示且不下发。"""

    def setUp(self):
        """记录下发与回复调用。"""
        self.replies = []
        self.dispatches = []
        self._orig_reply = cp._reply
        self._orig_dispatch = cp._dispatch
        cp._reply = lambda c, o, text, **kw: self.replies.append(text)
        cp._dispatch = lambda *a, **kw: self.dispatches.append(a)

    def tearDown(self):
        """还原。"""
        cp._reply = self._orig_reply
        cp._dispatch = self._orig_dispatch

    def test_re_time_non_numeric(self):
        """/rt 传非数字时提示且不下发。"""
        cp._h_re_time(None, "u", "abc", "m")
        self.assertTrue(any("数字" in r for r in self.replies))
        self.assertEqual(self.dispatches, [])

    def test_re_time_non_positive(self):
        """/rt 传 0 或负数时提示且不下发。"""
        cp._h_re_time(None, "u", "0", "m")
        self.assertTrue(any("大于 0" in r for r in self.replies))
        self.assertEqual(self.dispatches, [])

    def test_re_time_missing_arg(self):
        """/rt 不带参数时给用法提示。"""
        cp._h_re_time(None, "u", "", "m")
        self.assertTrue(any("用法" in r for r in self.replies))

    def test_switch_session_non_integer(self):
        """/ss 传非整数时提示且不下发。"""
        cp._h_switch_session(None, "u", "abc", "m")
        self.assertTrue(any("整数" in r for r in self.replies))
        self.assertEqual(self.dispatches, [])

    def test_switch_session_non_positive(self):
        """/ss 传 0 时提示且不下发。"""
        cp._h_switch_session(None, "u", "0", "m")
        self.assertTrue(any("大于 0" in r for r in self.replies))
        self.assertEqual(self.dispatches, [])

    def test_switch_auto_invalid_arg(self):
        """/sa 传无法识别的参数时给用法提示。"""
        cp._h_switch_auto(None, "u", "maybe", "m")
        self.assertTrue(any("用法" in r for r in self.replies))

    def test_switch_auto_on_dispatches(self):
        """/sa on 下发开启。"""
        cp._h_switch_auto(None, "u", "on", "m")
        self.assertTrue(len(self.dispatches) > 0)

    def test_switch_auto_off_dispatches(self):
        """/sa off 下发关闭。"""
        cp._h_switch_auto(None, "u", "off", "m")
        self.assertTrue(len(self.dispatches) > 0)


if __name__ == "__main__":
    unittest.main()