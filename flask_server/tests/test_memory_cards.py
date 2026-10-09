"""卡片表读写：写入 / 更新 / 按节点列举 / 卡片字典的测试。

背景：
    memory_cards 维护 cards 表，记录消息节点上挂着的工具卡片；
    蒸馏时 tool 来源节点的精华主要来自这里。此前无任何测试。

验证目标：
    1. upsert_card：首次插入返回 id，同 (node_id, block_id) 再次写入为更新；
    2. list_by_node：列出某节点全部卡片，result 字段反序列化；
    3. cards_map：按 block_id 建字典；
    4. result 为空时不报错。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_cards -v
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import memory_db
import memory_nodes
import memory_cards


def _mk_node(msg_id):
    """写入一个最简节点，供卡片挂靠。"""
    return memory_nodes.upsert_node(
        {"msg_id": msg_id, "conv_id": "c1", "site_key": "s1"},
        {"source": "assistant", "role": "assistant", "name": "ai", "blocks": []},
    )


class _DBBase(unittest.TestCase):
    """记忆库重定向到临时目录。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memcards_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestUpsertCard(_DBBase):
    """卡片写入与更新。"""

    def test_insert_returns_id(self):
        """首次写入应返回非空 id。"""
        nid = _mk_node("m1")
        cid = memory_cards.upsert_card(nid, "b1", tool="read_file", status="done",
                                       result={"ok": True})
        self.assertTrue(cid)

    def test_same_block_updates_not_duplicates(self):
        """同 (node_id, block_id) 再次写入应为更新，不新增。"""
        nid = _mk_node("m1")
        cid1 = memory_cards.upsert_card(nid, "b1", tool="t", status="pending")
        cid2 = memory_cards.upsert_card(nid, "b1", tool="t", status="done")
        self.assertEqual(cid1, cid2)
        cards = memory_cards.list_by_node(nid)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["status"], "done")

    def test_result_none_ok(self):
        """result 为空时应能正常写入。"""
        nid = _mk_node("m1")
        memory_cards.upsert_card(nid, "b1", tool="t", status="pending", result=None)
        cards = memory_cards.list_by_node(nid)
        self.assertEqual(len(cards), 1)


class TestListAndMap(_DBBase):
    """列举与字典。"""

    def test_list_result_roundtrip(self):
        """result 写入后应能反序列化取回。"""
        nid = _mk_node("m1")
        memory_cards.upsert_card(nid, "b1", tool="t", status="done",
                                 result={"msg": "你好"})
        cards = memory_cards.list_by_node(nid)
        self.assertEqual(cards[0]["result"], {"msg": "你好"})

    def test_cards_map_keyed_by_block(self):
        """cards_map 应以 block_id 为键。"""
        nid = _mk_node("m1")
        memory_cards.upsert_card(nid, "b1", tool="t1")
        memory_cards.upsert_card(nid, "b2", tool="t2")
        m = memory_cards.cards_map(nid)
        self.assertEqual(set(m.keys()), {"b1", "b2"})
        self.assertEqual(m["b1"]["tool"], "t1")

    def test_empty_node_returns_empty(self):
        """无卡片的节点应返回空列表与空字典。"""
        nid = _mk_node("m1")
        self.assertEqual(memory_cards.list_by_node(nid), [])
        self.assertEqual(memory_cards.cards_map(nid), {})


if __name__ == "__main__":
    unittest.main()
