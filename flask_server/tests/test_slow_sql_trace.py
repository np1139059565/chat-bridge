"""慢 SQL 追踪的计时正确性：测试（空闲时间不得被算作 SQL 耗时）。

背景（从日志发现）：
    app-2026-10-06.log 反复出现同一条告警：
        WARN [db] 慢SQL 1800005.1ms: SELECT id, keywords FROM nodes ...
    1800005ms ≈ 30 分钟，且每次都精确接近 1800 秒——正好等于后台调度的
    sleep 间隔。若用「两次回调时间差」当作上一条 SQL 的耗时，就会把语句
    之间线程的空闲（含 sleep）也算进去。progress_handler 只在语句真运行时
    回调，用它计时可避免把空闲算进耗时。

验证目标（对准真实行为）：
    - 语句之间有空闲时，不把空闲算作上一条 SQL 的耗时；
    - 快速语句不告警；
    - 真正执行很久的语句要告警。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_slow_sql_trace -v
"""
import os
import sys
import tempfile
import shutil
import time
import unittest
import unittest.mock as mock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401
import memory_db


class TestSlowSqlTrace(unittest.TestCase):
    """验证慢 SQL 计时只算语句执行时间，不含空闲。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="slowsql_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")
        # 捕获 app_log.warn 调用
        self.warns = []
        self._patch = mock.patch.object(
            memory_db.app_log, "warn",
            side_effect=lambda *a: self.warns.append(" ".join(str(x) for x in a)))
        self._patch.start()
        self.conn = memory_db.get_conn()

    def tearDown(self):
        self._patch.stop()
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _slow_warns(self):
        """只看包含「慢SQL」的告警。"""
        return [w for w in self.warns if "慢SQL" in w]

    def test_idle_gap_not_reported(self):
        """两条语句之间空闲（模拟调度 sleep），不得把空闲算作 SQL 耗时。

        这是本次修复的核心：原实现会在此误报「慢SQL 约 300ms」。
        """
        self.conn.execute("SELECT 1")
        time.sleep(0.3)                 # 模拟线程空闲（如调度 sleep）
        self.conn.execute("SELECT 2")
        self.assertEqual(self._slow_warns(), [],
                         "空闲时间被误算为慢 SQL：%s" % self._slow_warns())

    def test_fast_queries_not_reported(self):
        """连续快速语句不应产生慢 SQL 告警。"""
        for i in range(20):
            self.conn.execute("SELECT %d" % i)
        self.assertEqual(self._slow_warns(), [])

    def test_actually_slow_query_reported(self):
        """真正执行很久的语句应产生告警（证明检测能力仍在）。"""
        # 递归 CTE 制造一条确实耗时的查询
        slow_sql = (
            "WITH RECURSIVE cnt(x) AS ("
            "SELECT 1 UNION ALL SELECT x+1 FROM cnt WHERE x < 2000000) "
            "SELECT count(*) FROM cnt"
        )
        self.conn.execute(slow_sql)
        # 结算发生在「下一条语句执行前」，故补一条语句触发结算
        self.conn.execute("SELECT 1")
        self.assertTrue(self._slow_warns(),
                        "真正耗时的查询未被检测到")


if __name__ == "__main__":
    unittest.main()
