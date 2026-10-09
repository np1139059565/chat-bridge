"""路由层集成测试：用 Flask 测试客户端走一遍关键接口。

背景：
    路由层此前没有任何端到端测试，问题只能靠手工验证才发现（例如网页前端
    日志上报接口收到 JSON 数组时报 500）。本文件用 Flask 的 test_client 覆盖
    若干关键接口，作为回归安全网。

隔离策略：
    不调用 create_app（它会启动看门狗、后台调度与远程桥接等带副作用的线程），
    而是新建独立 Flask 实例、只注册被测蓝图。日志目录与记忆库重定向到临时目录，
    测试不触碰真实数据。

验证目标：
    1. /api/web/client_log：单条对象与数组都能成功（数组曾是 500 回归点）；
    2. /api/cards：创建、缺 content 返回 400、确认投递幂等、未知卡片 404；
    3. /tool：未知工具 404、内置工具可调用、OPTIONS 预检返回 204；
    4. /tools、/prompt_sections、/ 三个只读接口可正常响应。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_routes_integration -v
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
from flask import Flask

import runtime
import tools_impl

from routes.tools import bp as tools_bp
from routes.prompts import bp as prompts_bp
from routes.cards import bp as cards_bp
from routes.rules import bp as rules_bp
from routes.web_clientlog import bp as web_clientlog_bp


def _build_app():
    """构造只注册被测蓝图的最小应用，并统一处理 OPTIONS 预检。"""
    app = Flask("routes_test")
    app.register_blueprint(tools_bp)
    app.register_blueprint(prompts_bp)
    app.register_blueprint(cards_bp)
    app.register_blueprint(rules_bp)
    app.register_blueprint(web_clientlog_bp)

    @app.before_request
    def _preflight():
        from flask import request
        if request.method == "OPTIONS":
            return ("", 204)

    return app


class _RouteBase(unittest.TestCase):
    """重定向日志与记忆库到临时目录，并初始化运行时工具表。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="routes_test_")
        # 重定向日志目录（client 日志会落到这里）
        self._orig_logs = paths.LOGS_DIR
        paths.LOGS_DIR = Path(self.tmp) / "logs"
        # 重定向记忆库
        self._orig_dbdir = paths.MEMORY_DB_DIR
        self._orig_dbpath = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp) / "memory"
        import memory_db
        memory_db.reset_for_tests(Path(self.tmp) / "memory" / "test.db")
        # 初始化运行时工具表（等价于 create_app 的 _init_runtime）
        self._orig_impl = runtime.impl
        self._orig_tools = runtime.TOOLS
        self._orig_dispatch = runtime.DISPATCH
        runtime.impl = tools_impl
        runtime.TOOLS = dict(tools_impl.TOOLS)
        runtime.DISPATCH = dict(tools_impl.DISPATCH)
        self.app = _build_app()
        self.client = self.app.test_client()

    def tearDown(self):
        paths.LOGS_DIR = self._orig_logs
        paths.MEMORY_DB_DIR = self._orig_dbdir
        paths.MEMORY_DB_PATH = self._orig_dbpath
        runtime.impl = self._orig_impl
        runtime.TOOLS = self._orig_tools
        runtime.DISPATCH = self._orig_dispatch
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestClientLog(_RouteBase):
    """网页前端日志上报接口（数组 500 的回归点）。"""

    def test_single_object_ok(self):
        """单条对象应返回成功。"""
        r = self.client.post("/api/web/client_log", json={"tag": "poll", "msg": "hi"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])

    def test_array_batch_ok(self):
        """数组批量上报应返回成功（此前返回 500）。"""
        r = self.client.post("/api/web/client_log",
                             json=[{"tag": "a", "msg": "1"}, {"tag": "b", "msg": "2"}])
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])

    def test_garbage_body_ok(self):
        """非数组非对象的请求体不应报错，仍返回成功。"""
        r = self.client.post("/api/web/client_log", data="not json",
                             content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_options_preflight(self):
        """OPTIONS 预检应返回 204。"""
        r = self.client.options("/api/web/client_log")
        self.assertEqual(r.status_code, 204)


class TestCards(_RouteBase):
    """外部卡片接口。"""

    def test_create_and_get(self):
        """创建卡片后可按 id 取回。"""
        r = self.client.post("/api/cards", json={"type": "t", "title": "标题", "content": "正文"})
        self.assertEqual(r.status_code, 200)
        cid = r.get_json()["id"]
        g = self.client.get("/api/cards/%s" % cid)
        self.assertEqual(g.status_code, 200)
        self.assertTrue(g.get_json()["success"])

    def test_missing_content_returns_400(self):
        """缺 content 应返回 400。"""
        r = self.client.post("/api/cards", json={"type": "t"})
        self.assertEqual(r.status_code, 400)

    def test_unknown_card_returns_404(self):
        """取不存在的卡片应返回 404。"""
        r = self.client.get("/api/cards/nope")
        self.assertEqual(r.status_code, 404)

    def test_confirm_delivered_idempotent(self):
        """确认投递可重复调用且幂等。"""
        cid = self.client.post("/api/cards",
                               json={"content": "正文"}).get_json()["id"]
        first = self.client.post("/api/cards/%s/delivered" % cid)
        second = self.client.post("/api/cards/%s/delivered" % cid)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

    def test_pending_returns_list(self):
        """待投递列表应返回数组。"""
        r = self.client.get("/api/cards/pending")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.get_json()["cards"], list)


class TestToolRoutes(_RouteBase):
    """工具目录与工具调用路由。"""

    def test_tools_list(self):
        """/tools 应返回工具数组。"""
        r = self.client.get("/tools")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.get_json()["tools"], list)

    def test_unknown_tool_404(self):
        """未知工具应返回 404，并给出可用工具清单。"""
        r = self.client.post("/tool", json={"tool": "__no_such_tool__", "parameters": {}})
        self.assertEqual(r.status_code, 404)
        body = r.get_json()
        self.assertFalse(body["success"])
        self.assertIn("available", body)

    def test_builtin_tool_call(self):
        """调用内置 list_dir 应成功并返回结果。"""
        r = self.client.post("/tool", json={"tool": "list_dir",
                                             "parameters": {"dir_path": "."}})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["success"])

    def test_missing_required_param(self):
        """缺少必填参数应返回错误（参数类）。"""
        r = self.client.post("/tool", json={"tool": "list_dir", "parameters": {}})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["success"])


class TestReadonlyRoutes(_RouteBase):
    """只读接口可用性。"""

    def test_prompt_sections(self):
        """/prompt_sections 应返回 sections / skills / skillsManage。"""
        r = self.client.get("/prompt_sections")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        for key in ("sections", "skills", "skillsManage"):
            self.assertIn(key, body)

    def test_rules_list(self):
        """/rules GET 应返回规则数组与优先级定义。"""
        r = self.client.get("/rules")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIsInstance(body["rules"], list)
        self.assertIn("priorities", body)

    def test_index_html(self):
        """首页应返回 HTML。"""
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.content_type)


if __name__ == "__main__":
    unittest.main()
