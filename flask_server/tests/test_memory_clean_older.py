"""清理旧节点的会话隔离测试。

背景：
    图谱页面的「清理该节点之前的全部旧节点」原按全库时间轴筛选，
    未按会话隔离——所有会话共用一条时间轴，会跨会话误删其它会话更早的
    节点（不可恢复）。已修复为强制按 conv_id 过滤，并给接口加必填校验。
    本文件锁定该行为，防止回退。

验证目标：
    1. ids_older_than 只返回同会话内更早的节点，不波及其它会话；
    2. 同会话内按时间正确取「更早」，参照节点自身不含在内；
    3. site_key 传入时限定站点。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_clean_older -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import memory_db
import memory_nodes


def _ins(conn, node_id, conv, ts, site_key="glm"):
    """插入一个最简节点行（只填会话隔离与时间相关字段）。"""
    conn.execute(
        "INSERT INTO nodes(id,msg_id,conv_id,site_key,parent_id,source,role,created_at) "
        "VALUES(?,?,?,?,0,?,?,?)",
        (node_id, "m%d" % node_id, conv, site_key, "user", "user", ts),
    )


class TestIdsOlderThanIsolation(unittest.TestCase):
    """ids_older_than 的会话隔离边界。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="clean_older_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")
        conn = memory_db.get_conn()
        # 会话 A：节点 1(100)、2(200)；会话 B：节点 3(150)、4(300)
        _ins(conn, 1, "A", 100)
        _ins(conn, 2, "A", 200)
        _ins(conn, 3, "B", 150)
        _ins(conn, 4, "B", 300)
        conn.commit()

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path

    def test_only_same_conversation(self):
        """A 会话内更早的只有节点 1，不包含 B 会话的 3。"""
        got = sorted(memory_nodes.ids_older_than(2, "A"))
        self.assertEqual(got, [1])

    def test_other_conversation_unaffected(self):
        """从 B 会话取更早：只含 3，不含 A 会话的 1、2。"""
        got = sorted(memory_nodes.ids_older_than(4, "B"))
        self.assertEqual(got, [3])

    def test_reference_node_excluded(self):
        """参照节点自身不在结果里。"""
        got = memory_nodes.ids_older_than(2, "A")
        self.assertNotIn(2, got)

    def test_no_earlier_returns_empty(self):
        """会话内没有更早节点时返回空。"""
        got = memory_nodes.ids_older_than(1, "A")
        self.assertEqual(got, [])

    def test_site_key_scopes(self):
        """传入不同 site_key 时，取不到该站点下的更早节点。"""
        got = memory_nodes.ids_older_than(2, "A", site_key="deepseek")
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
