"""全局日志异步化：测试（对应修复方向 4）。

背景（走查发现）：
    app_log.write 在 _write_lock 内做磁盘 open + write + close。
    每个请求写多条日志，都要抢同一把全局锁并做磁盘 IO。
    磁盘繁忙或日志文件巨大时，这把锁成为全局串行点，拖慢所有请求。

修复目标：
    写入改为「入队即返回」，由单个后台线程消费队列、落盘。
    请求线程不再碰锁、不做磁盘 IO。同时提供 drain（排空）机制，
    保证进程正常退出或测试时可等待日志全部落盘，不丢日志。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_app_log_async -v
"""
import os
import sys
import tempfile
import shutil
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths
import app_log


class TestAppLogAsync(unittest.TestCase):
    """验证日志异步写入：不阻塞、最终落盘、顺序保持。"""

    def setUp(self):
        # 把日志目录重定向到临时目录，避免污染真实日志
        self._orig_logs_dir = paths.LOGS_DIR
        self.tmp = tempfile.mkdtemp(prefix="applog_test_")
        paths.LOGS_DIR = self.tmp

    def tearDown(self):
        paths.LOGS_DIR = self._orig_logs_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _log_file_text(self):
        """读取当天日志文件内容；不存在返回空串。"""
        day = time.strftime("%Y-%m-%d")
        p = os.path.join(self.tmp, "app-%s.log" % day)
        if not os.path.exists(p):
            return ""
        with open(p, "r", encoding="utf-8") as f:
            return f.read()

    def test_write_returns_quickly(self):
        """写入调用应快速返回，不做同步磁盘等待。"""
        t0 = time.time()
        for i in range(200):
            app_log.info("[test]", "line", i)
        elapsed = time.time() - t0
        # 200 条日志若同步落盘通常远慢于此；这里只要求「不明显阻塞」
        self.assertLess(elapsed, 1.0, "写入疑似同步阻塞")

    def test_logs_eventually_persisted(self):
        """写入后，日志最终应出现在文件里（异步落盘可达）。"""
        app_log.info("[test]", "persist-marker-12345")
        app_log.drain(timeout=3.0)
        text = self._log_file_text()
        self.assertIn("persist-marker-12345", text)

    def test_drain_flushes_all(self):
        """drain 后，全部已入队日志都应落盘，不丢。"""
        n = 50
        for i in range(n):
            app_log.info("[test]", "drain-line-%03d" % i)
        app_log.drain(timeout=3.0)
        text = self._log_file_text()
        for i in range(n):
            self.assertIn("drain-line-%03d" % i, text)

    def test_order_preserved(self):
        """同一线程写入的多条日志，落盘顺序应与写入顺序一致。"""
        for i in range(10):
            app_log.info("[test]", "order-%02d" % i)
        app_log.drain(timeout=3.0)
        text = self._log_file_text()
        positions = [text.find("order-%02d" % i) for i in range(10)]
        self.assertTrue(all(p >= 0 for p in positions), "有日志未落盘")
        self.assertEqual(positions, sorted(positions), "日志顺序错乱")


if __name__ == "__main__":
    unittest.main()
