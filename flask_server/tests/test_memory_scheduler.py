"""后台调度：单轮维护容错与启动幂等的测试。

背景：
    memory_scheduler 由后台守护线程周期性执行衰减、事件聚类与 WAL 检查点。
    此前无任何测试。

安全策略：
    不真正启动后台线程。用替身拦截 threading.Thread，只验证 run_once 的
    容错聚合与 start_background_tasks 的启动幂等。

验证目标：
    1. run_once：三步都成功时 errors 为空；
    2. run_once：某一步抛异常时，errors 记录该步且不向上抛，其它步照常执行；
    3. start_background_tasks：首次返回真、重复调用返回假（幂等）。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_scheduler -v
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import memory_scheduler


class TestRunOnce(unittest.TestCase):
    """单轮维护的容错聚合。"""

    def test_all_steps_ok(self):
        """三步都正常时，errors 应为空。"""
        with mock.patch.object(memory_scheduler.memory_decay, "recompute_all", return_value=1), \
             mock.patch.object(memory_scheduler.memory_events, "cluster_events", return_value={}), \
             mock.patch.object(memory_scheduler.memory_wal, "wal_checkpoint", return_value={"ok": True}):
            res = memory_scheduler.run_once()
        self.assertEqual(res["errors"], [])
        self.assertIsNotNone(res["decay"])
        self.assertIsNotNone(res["events"])

    def test_decay_error_recorded_not_raised(self):
        """衰减抛异常时应被记录，不向上抛，其它步照常。"""
        with mock.patch.object(memory_scheduler.memory_decay, "recompute_all",
                               side_effect=RuntimeError("boom")), \
             mock.patch.object(memory_scheduler.memory_events, "cluster_events", return_value={}), \
             mock.patch.object(memory_scheduler.memory_wal, "wal_checkpoint", return_value={"ok": True}):
            res = memory_scheduler.run_once()
        self.assertTrue(any("decay" in e for e in res["errors"]))
        # 事件聚类仍被执行
        self.assertIsNotNone(res["events"])

    def test_events_error_recorded(self):
        """事件聚类抛异常时应被记录，不阻断检查点步骤。"""
        with mock.patch.object(memory_scheduler.memory_decay, "recompute_all", return_value=1), \
             mock.patch.object(memory_scheduler.memory_events, "cluster_events",
                               side_effect=RuntimeError("boom")), \
             mock.patch.object(memory_scheduler.memory_wal, "wal_checkpoint", return_value={"ok": True}):
            res = memory_scheduler.run_once()
        self.assertTrue(any("events" in e for e in res["errors"]))
        self.assertIsNotNone(res["checkpoint"])


class TestStartIdempotent(unittest.TestCase):
    """后台线程启动幂等。"""

    def setUp(self):
        self._orig = memory_scheduler._started
        memory_scheduler._started = False

    def tearDown(self):
        memory_scheduler._started = self._orig

    def test_start_once_then_noop(self):
        """首次启动返回真，重复调用返回假。"""
        with mock.patch.object(memory_scheduler.threading, "Thread") as thread:
            first = memory_scheduler.start_background_tasks(interval=1)
            second = memory_scheduler.start_background_tasks(interval=1)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(thread.call_count, 1)


if __name__ == "__main__":
    unittest.main()
