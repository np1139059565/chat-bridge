"""边表 keywords 列与迁移：测试。

背景：
    突触边新增 keywords 列（存导致关联的关键词，供前端解释连线原因）。
    但 CREATE TABLE IF NOT EXISTS 对「已存在的旧库」不生效——表已存在时它不改动，
    故后加的列必须靠 _migrate_columns 显式 ALTER 补上。
    若迁移失效，add_edge 写入 keywords 会报 no such column，中断记忆保存链路。

验证目标：
    1. 新库建表后 edges 表就带 keywords 列；
    2. add_edge 带 keywords 能写入并原样取回；
    3. 对「缺 keywords 列的旧库」，_migrate_columns 能补上该列（迁移有效）。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_edges_keywords -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import memory_db
import memory_edges


class TestEdgeKeywords(unittest.TestCase):
    """验证 keywords 列存在、可读写，且迁移对旧库有效。"""

    def setUp(self):
        # 重定向到临时库，避免触碰真实库
        self.tmp = tempfile.mkdtemp(prefix="memedges_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _edge_columns(self):
        """取 edges 表当前全部列名。"""
        conn = memory_db.get_conn()
        return [r[1] for r in conn.execute("PRAGMA table_info(edges)").fetchall()]

    def test_new_db_has_keywords_column(self):
        """新库建表后，edges 表应直接带 keywords 列。"""
        cols = self._edge_columns()
        self.assertIn("keywords", cols)

    def test_add_edge_with_keywords_roundtrip(self):
        """add_edge 带 keywords 应能写入，并在查询中原样取回。"""
        memory_edges.add_edge(1, 2, "associative", weight=2.0,
                              keywords=["语音", "播放"])
        rows = memory_edges.all_edges()
        hit = [r for r in rows if r["kind"] == "associative"]
        self.assertEqual(len(hit), 1)
        # 取回的关键词是 JSON 字符串，应能解析出原列表
        kw = json.loads(hit[0]["keywords"])
        self.assertEqual(sorted(kw), sorted(["语音", "播放"]))

    def test_migration_adds_missing_column(self):
        """对缺 keywords 列的旧库，_migrate_columns 应补上该列。"""
        conn = memory_db.get_conn()
        # 造一个旧结构：删掉带 keywords 的表，重建为不含该列的版本
        conn.execute("DROP TABLE edges")
        conn.execute(
            "CREATE TABLE edges (id INTEGER PRIMARY KEY, src_node INTEGER,"
            " dst_node INTEGER, kind TEXT, weight REAL, created_at INTEGER,"
            " last_active_at INTEGER, UNIQUE(src_node, dst_node, kind))")
        conn.commit()
        self.assertNotIn("keywords", self._edge_columns())
        # 跑迁移，应补上 keywords 列
        memory_db._migrate_columns(conn)
        conn.commit()
        self.assertIn("keywords", self._edge_columns())


if __name__ == "__main__":
    unittest.main()
