"""日志落盘边界：级别过滤 / 队列满丢弃 / 跨天切换 测试。

被测：core/app_log.py 与 core/log_sink.py。
补充 test_app_log_async.py 未覆盖的边界：
- app_log.set_level：低于阈值的日志被过滤，不落盘；
- AsyncDayFileSink.dropped：队列满时丢弃最旧，丢弃计数递增；
- DayFileSink 跨天切换：日期变化后写入落到新文件。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_log_sink_boundaries -v
"""
import os
import sys
import tempfile
import shutil
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))

import paths
import app_log
import log_sink


def _read(path):
    """读取文件文本；不存在返回空串。"""
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestLevelFilter(unittest.TestCase):
    """验证 app_log.set_level 的级别过滤。"""

    def setUp(self):
        # 重定向日志目录到临时目录，隔离真实日志
        self._orig_logs_dir = paths.LOGS_DIR
        self._orig_level = app_log._min_level
        self.tmp = tempfile.mkdtemp(prefix="loglevel_test_")
        paths.LOGS_DIR = self.tmp

    def tearDown(self):
        app_log._min_level = self._orig_level       # 复原级别阈值
        paths.LOGS_DIR = self._orig_logs_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _log_file_text(self):
        """读取当天 app 日志内容。"""
        day = time.strftime("%Y-%m-%d")
        return _read(os.path.join(self.tmp, "app-%s.log" % day))

    def test_debug_filtered_at_info_level(self):
        """阈值 INFO 时，DEBUG 日志应被过滤、不落盘。"""
        app_log.set_level("INFO")
        app_log.debug("[t]", "debug-marker-AAAA")
        app_log.info("[t]", "info-marker-BBBB")
        app_log.drain(timeout=3.0)
        text = self._log_file_text()
        self.assertNotIn("debug-marker-AAAA", text, "DEBUG 不应落盘")
        self.assertIn("info-marker-BBBB", text, "INFO 应落盘")

    def test_debug_passes_at_debug_level(self):
        """阈值 DEBUG 时，DEBUG 日志应落盘。"""
        app_log.set_level("DEBUG")
        app_log.debug("[t]", "debug-marker-CCCC")
        app_log.drain(timeout=3.0)
        self.assertIn("debug-marker-CCCC", self._log_file_text())


class TestQueueDrop(unittest.TestCase):
    """验证队列满时丢弃最旧并计数。"""

    def test_dropped_increments_when_full(self):
        """队列容量设为 1，狂写应触发丢弃，dropped() 递增。"""
        tmp = tempfile.mkdtemp(prefix="drop_test_")
        try:
            # 容量 1 的异步落盘器：不启动消费线程（不调 write），
            # 直接调内部队列与 _ensure_worker 会消费，故这里用极小容量 + 快速写
            sink = log_sink.AsyncDayFileSink("drop", lambda: tmp, maxsize=1)
            # 连续写多条：消费速度赶不上时必然发生丢弃
            for i in range(200):
                sink.write("line-%03d" % i)
            # 丢弃计数应大于 0（容量 1，写入 200 条，消费有限）
            self.assertGreater(sink.dropped(), 0, "队列满未触发丢弃")
            sink.drain(timeout=3.0)
            sink.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestDrainTimeout(unittest.TestCase):
    """验证 drain 在超时后返回 False（队列未排空）。"""

    def test_drain_returns_false_on_timeout(self):
        """有未完成项且无人消费时，drain 应超时返回 False。

        确定性做法：直接往内部队列塞一条（绕过 write，不启动消费线程），
        使 unfinished_tasks 恒大于 0，drain 必然等到超时并返回 False。
        """
        tmp = tempfile.mkdtemp(prefix="drainto_test_")
        try:
            sink = log_sink.AsyncDayFileSink("dto", lambda: tmp)
            sink._queue.put("never-consumed-line")   # 只入队，不启动消费者
            ok = sink.drain(timeout=0.2)             # 无人消费，必定超时
            self.assertFalse(ok, "队列未排空时 drain 应返回 False")
            # 收尾：手动标记该条已处理，避免残留 unfinished 计数影响其它用例
            sink._queue.get_nowait()
            sink._queue.task_done()
            sink.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_drain_true_when_empty(self):
        """队列为空时，drain 应立即返回 True。"""
        tmp = tempfile.mkdtemp(prefix="drainempty_test_")
        try:
            sink = log_sink.AsyncDayFileSink("de", lambda: tmp)
            self.assertTrue(sink.drain(timeout=1.0), "空队列应返回 True")
            sink.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestDaySwitch(unittest.TestCase):
    """验证 DayFileSink 跨天切换文件。"""

    def test_switch_to_new_day_file(self):
        """日期变化后，写入应落到新日期的文件。"""
        tmp = tempfile.mkdtemp(prefix="dayswitch_test_")
        try:
            sink = log_sink.DayFileSink("day", lambda: tmp)
            # 用 mock：替换 day_str 返回不同日期
            orig = log_sink.day_str
            try:
                log_sink.day_str = lambda: "2026-01-01"  # 第一天
                sink.append("first-day-line")
                log_sink.day_str = lambda: "2026-01-02"  # 第二天
                sink.append("second-day-line")
            finally:
                log_sink.day_str = orig
            sink.close()
            f1 = _read(os.path.join(tmp, "day-2026-01-01.log"))
            f2 = _read(os.path.join(tmp, "day-2026-01-02.log"))
            self.assertIn("first-day-line", f1, "第一天内容未落对文件")
            self.assertIn("second-day-line", f2, "跨天后未切到新文件")
            self.assertNotIn("second-day-line", f1, "新内容不应写进旧文件")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
