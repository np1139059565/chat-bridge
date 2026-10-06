"""数据库连接显式关闭：测试。

背景（走查发现）：
    memory_db 的连接存在 threading.local 中，get_conn() 首次调用时建立，
    但没有显式关闭路径。线程退出时连接随引用计数归零被 GC 回收，
    时机不够确定。改为提供 close_conn() 显式关闭，更稳健。

修复目标：
    提供 close_conn()，关闭当前线程的连接并从线程局部清除；
    关闭后可安全重建；未建连接时调用安全。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_db_conn -v
"""
import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import memory_db


class TestCloseConn(unittest.TestCase):
    """验证 close_conn() 显式关闭当前线程连接，且可安全重建。"""

    def setUp(self):
        # 把数据库重定向到临时目录，避免触碰真实库
        self.tmp = tempfile.mkdtemp(prefix="memdb_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_conn_creates_connection(self):
        """get_conn 应能建立连接。"""
        conn = memory_db.get_conn()
        self.assertIsNotNone(conn)

    def test_close_conn_clears_thread_local(self):
        """close_conn 后，线程局部里不应再留有连接。"""
        memory_db.get_conn()
        memory_db.close_conn()
        self.assertIsNone(getattr(memory_db._local, "conn", None))

    def test_get_conn_recreates_after_close(self):
        """关闭后再次 get_conn 应重建一个新连接。"""
        c1 = memory_db.get_conn()
        memory_db.close_conn()
        c2 = memory_db.get_conn()
        self.assertIsNotNone(c2)
        self.assertIsNot(c1, c2)

    def test_close_conn_idempotent(self):
        """未建连接时多次调用 close_conn 不应报错。"""
        memory_db.close_conn()
        memory_db.close_conn()


if __name__ == "__main__":
    unittest.main()
