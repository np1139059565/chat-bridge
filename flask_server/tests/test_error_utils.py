"""错误分类与定位、错误响应辅助的边界测试。

背景：
    error_utils 把工具异常归类为 parameter / environment / tool_internal，
    responses 据此构造统一错误响应。这套分类直接决定 AI 是「改参数重试」
    还是「反馈工具代码缺陷」，分错会误导后续动作。此前无任何测试。

验证目标：
    1. classify_error：参数类、环境类、超时类、内部缺陷类各自归类正确；
    2. error_location：从堆栈里挑出服务目录内的那一帧，无堆栈返回 None；
    3. exception_payload：字段齐全、按异常类型给出正确 origin；
    4. disabled_resp：返回 200、success=false、origin=disabled，含可用工具列表。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_error_utils -v
"""
import os
import subprocess
import sys
import traceback
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import runtime
import error_utils
import responses
import tool_helpers


class _ImplStub:
    """最小工具实现替身：只暴露 ToolParamError，供分类函数现取。"""
    ToolParamError = tool_helpers.ToolParamError


class _Base(unittest.TestCase):
    """为分类函数准备好 runtime.impl 与工具表。"""

    def setUp(self):
        self._orig_impl = runtime.impl
        self._orig_tools = runtime.TOOLS
        self._orig_isenabled = runtime.is_tool_enabled
        runtime.impl = _ImplStub

    def tearDown(self):
        runtime.impl = self._orig_impl
        runtime.TOOLS = self._orig_tools
        runtime.is_tool_enabled = self._orig_isenabled


class TestClassifyError(_Base):
    """异常分类。"""

    def test_tool_param_error_is_parameter(self):
        """ToolParamError 应归为参数类。"""
        self.assertEqual(error_utils.classify_error(tool_helpers.ToolParamError("x")), "parameter")

    def test_value_error_is_parameter(self):
        """ValueError / TypeError / KeyError 归为参数类。"""
        self.assertEqual(error_utils.classify_error(ValueError("x")), "parameter")
        self.assertEqual(error_utils.classify_error(TypeError("x")), "parameter")
        self.assertEqual(error_utils.classify_error(KeyError("x")), "parameter")

    def test_file_not_found_is_environment(self):
        """文件不存在 / 权限不足归为环境类。"""
        self.assertEqual(error_utils.classify_error(FileNotFoundError("x")), "environment")
        self.assertEqual(error_utils.classify_error(PermissionError("x")), "environment")

    def test_timeout_is_environment(self):
        """执行超时归为环境类（不是代码缺陷）。"""
        self.assertEqual(
            error_utils.classify_error(subprocess.TimeoutExpired("c", 1)), "environment")

    def test_unknown_is_tool_internal(self):
        """其它异常归为工具内部缺陷。"""
        self.assertEqual(error_utils.classify_error(RuntimeError("x")), "tool_internal")

    def test_param_cls_empty_when_impl_none(self):
        """runtime.impl 为 None 时，param_error_cls 返回空元组，isinstance 不报错。"""
        runtime.impl = None
        self.assertEqual(error_utils.param_error_cls(), ())


class TestErrorLocation(_Base):
    """错误定位。"""

    def test_location_points_into_service_dir(self):
        """应挑出服务目录内那一帧。"""
        try:
            raise ValueError("boom")
        except ValueError:
            loc = error_utils.error_location(sys.exc_info()[2])
        self.assertIsNotNone(loc)
        self.assertIn("file", loc)
        self.assertIn("line", loc)
        self.assertIn("function", loc)

    def test_location_none_for_empty_tb(self):
        """无堆栈信息时返回 None。"""
        self.assertIsNone(error_utils.error_location(None))


class TestExceptionPayload(_Base):
    """异常响应体构造。"""

    def test_payload_fields_and_origin(self):
        """字段齐全，ValueError 的 origin 应为 parameter。"""
        try:
            raise ValueError("bad param")
        except ValueError as e:
            payload = responses.exception_payload(e, include_tool="read_file")
        self.assertFalse(payload["success"])
        self.assertEqual(payload["origin"], "parameter")
        self.assertEqual(payload["errorType"], "ValueError")
        self.assertEqual(payload["tool"], "read_file")
        for key in ("originLabel", "location", "traceback", "hint"):
            self.assertIn(key, payload)

    def test_payload_without_tool_field(self):
        """include_tool 为 None 时不应含 tool 字段。"""
        try:
            raise RuntimeError("x")
        except RuntimeError as e:
            payload = responses.exception_payload(e)
        self.assertNotIn("tool", payload)
        self.assertEqual(payload["origin"], "tool_internal")


class TestDisabledResp(_Base):
    """工具已下线响应。"""

    def test_disabled_shape(self):
        """应返回 200、success=false、origin=disabled，并列出可用工具。

        disabled_resp 内部用 jsonify，需要 Flask 应用上下文，故用临时 app 包裹。
        """
        from flask import Flask
        runtime.TOOLS = {"read_file": {}, "list_dir": {}}
        runtime.is_tool_enabled = lambda k: k == "read_file"
        app = Flask("err_test")
        with app.app_context():
            resp, code = responses.disabled_resp("list_dir")
            body = resp.get_json()
        self.assertEqual(code, 200)
        self.assertFalse(body["success"])
        self.assertEqual(body["origin"], "disabled")
        self.assertIn("read_file", body["available"])
        self.assertNotIn("list_dir", body["available"])


if __name__ == "__main__":
    unittest.main()
