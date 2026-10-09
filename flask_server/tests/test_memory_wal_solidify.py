"""WAL 检查点与固化层：数据完整性与升格通道的测试。

背景：
    memory_wal 主动执行 checkpoint 回收 -wal 文件；memory_solidify 把记忆节点
    升格为规则文件或错题本条目。两者此前无任何测试。

隔离策略：
    记忆库重定向到临时目录；规则目录（paths.RULES_DIR）也临时重定向，
    确保固化产物只落在临时目录、不触碰真实 rules/。

验证目标：
    1. wal_checkpoint：合法模式返回结构完整、非法模式回退 TRUNCATE；
    2. promote_to_rule：新建规则文件含标题与条目，二次固化改为追加；
    3. promote_to_rule：节点不存在返回 None；
    4. promote_to_notebook：写入错题本返回条目 id，节点不存在返回 None。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_wal_solidify -v
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
import memory_wal
import memory_solidify
import memory_notes


def _mk_node(msg_id, essence, keywords):
    """写入一个带蒸馏字段的节点，供固化使用。"""
    nid = memory_nodes.upsert_node(
        {"msg_id": msg_id, "conv_id": "c1", "site_key": "s1"},
        {"source": "assistant", "role": "assistant", "name": "ai", "blocks": []},
    )
    import memory_keywords as kw
    memory_nodes.set_essence(nid, essence, keywords, kw.text_to_vector(essence))
    return nid


class _Base(unittest.TestCase):
    """记忆库与规则目录都重定向到临时目录。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memsolidify_test_")
        self._orig_dbdir = paths.MEMORY_DB_DIR
        self._orig_dbpath = paths.MEMORY_DB_PATH
        self._orig_rules = paths.RULES_DIR
        paths.MEMORY_DB_DIR = Path(self.tmp) / "memory"
        paths.RULES_DIR = Path(self.tmp) / "rules"
        memory_db.reset_for_tests(Path(self.tmp) / "memory" / "test.db")

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dbdir
        paths.MEMORY_DB_PATH = self._orig_dbpath
        paths.RULES_DIR = self._orig_rules
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestWalCheckpoint(_Base):
    """WAL 检查点。"""

    def test_truncate_returns_shape(self):
        """TRUNCATE 模式应返回结构完整的结果。"""
        res = memory_wal.wal_checkpoint("TRUNCATE")
        for key in ("ok", "mode"):
            self.assertIn(key, res)
        self.assertEqual(res["mode"], "TRUNCATE")

    def test_passive_mode(self):
        """PASSIVE 模式应被接受。"""
        res = memory_wal.wal_checkpoint("PASSIVE")
        self.assertEqual(res["mode"], "PASSIVE")

    def test_invalid_mode_falls_back(self):
        """非法模式应回退为 TRUNCATE（防拼串注入）。"""
        res = memory_wal.wal_checkpoint("EVIL; DROP TABLE")
        self.assertEqual(res["mode"], "TRUNCATE")


class TestPromoteToRule(_Base):
    """固化为规则文件。"""

    def test_creates_new_rule_file(self):
        """首次固化应新建规则文件，含标题与条目。"""
        nid = _mk_node("m1", "提交前必须回读文件", ["回读", "提交"])
        res = memory_solidify.promote_to_rule(nid, "myrule", title="我的规则")
        self.assertEqual(res["rule"], "myrule")
        self.assertFalse(res["appended"])
        content = (paths.RULES_DIR / "myrule.md").read_text(encoding="utf-8")
        self.assertIn("# 我的规则", content)
        self.assertIn("提交前必须回读文件", content)
        self.assertIn("回读", content)

    def test_second_promote_appends(self):
        """二次固化应追加条目，不覆盖原文件。"""
        nid1 = _mk_node("m1", "第一条", ["a"])
        nid2 = _mk_node("m2", "第二条", ["b"])
        memory_solidify.promote_to_rule(nid1, "r2")
        res = memory_solidify.promote_to_rule(nid2, "r2")
        self.assertTrue(res["appended"])
        content = (paths.RULES_DIR / "r2.md").read_text(encoding="utf-8")
        self.assertIn("第一条", content)
        self.assertIn("第二条", content)

    def test_missing_node_returns_none(self):
        """节点不存在时返回 None。"""
        self.assertIsNone(memory_solidify.promote_to_rule(999999, "r"))


class TestPromoteToNotebook(_Base):
    """固化为错题本。"""

    def test_writes_notebook_entry(self):
        """固化应写入错题本并返回条目 id。"""
        nid = _mk_node("m1", "一个教训", ["教训"])
        res = memory_solidify.promote_to_notebook(nid, note="补充说明")
        self.assertTrue(res["note_id"])
        rows = memory_notes.list_notes(kind="notebook")
        self.assertEqual(len(rows), 1)
        self.assertIn("一个教训", rows[0]["text"])
        self.assertIn("补充说明", rows[0]["text"])

    def test_missing_node_returns_none(self):
        """节点不存在时返回 None。"""
        self.assertIsNone(memory_solidify.promote_to_notebook(999999))


if __name__ == "__main__":
    unittest.main()
