"""外部工具转发：结果泄漏修复的测试（对应修复方向 5）。

背景（走查发现）：
    dispatch 超时后会调用 _abort_request 做善后，但它只清理了 _events（等待事件），
    没有清理 _results（结果表）。若提供方恰好在「超时判定」与「善后执行」之间的
    瞬间回传结果，resolve 会把结果写进 _results[request_id]，而等待方早已离场，
    这条结果就永远留在字典里，形成内存泄漏。

修复目标：
    _abort_request 在清理等待事件的同时，一并清掉 _results 里可能残留的同名结果。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_external_tools -v
"""
import os
import sys
import threading
import unittest

# 把服务根目录加入导入路径后，再导入被测模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 先导入 paths：它会把 core/ 与 tools/ 加入模块搜索路径，
# 之后才能按扁平名导入 external_tools 等核心模块。
import paths  # noqa: F401
import external_tools


class TestAbortRequestClearsResult(unittest.TestCase):
    """验证 _abort_request 善后时会清掉结果表里的残留。"""

    def setUp(self):
        # 每个用例用独立 hub，避免相互影响
        self.hub = external_tools.ProviderHub()
        self.provider = "demo_provider"
        self.rid = "req-0001"

    def test_abort_clears_pending_event(self):
        """善后应清掉挂起的等待事件。"""
        ev = threading.Event()
        self.hub._events[self.rid] = ev
        self.hub._abort_request(self.provider, self.rid)
        self.assertNotIn(self.rid, self.hub._events)

    def test_abort_clears_leaked_result(self):
        """善后应清掉结果表里的残留（本次修复的核心）。

        构造「超时善后时结果表已有同名残留」的场景，断言善后后被清空。
        """
        self.hub._results[self.rid] = {"data": {"ok": True}}
        self.hub._abort_request(self.provider, self.rid)
        self.assertNotIn(self.rid, self.hub._results)

    def test_abort_removes_command_from_queue(self):
        """善后应把尚未被取走的命令从队列撤回（原有行为，防回归）。"""
        self.hub._queues[self.provider] = [
            {"request_id": self.rid, "tool": "demo"},
            {"request_id": "other", "tool": "demo2"},
        ]
        self.hub._abort_request(self.provider, self.rid)
        remaining = [c.get("request_id") for c in self.hub._queues[self.provider]]
        self.assertEqual(remaining, ["other"])


if __name__ == "__main__":
    unittest.main()
