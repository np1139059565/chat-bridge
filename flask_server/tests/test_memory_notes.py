"""笔记层：每日记忆与错题本的读写测试。

背景：
    memory_notes 承载 journal（每日记忆）与 notebook（错题本）两类文本记忆，
    按用户规范属结构化记忆的一部分。此前无任何测试。

验证目标：
    1. add_note / list_notes：写入与按类型、日期列举；
    2. journal 自动补当天日期，notebook 不带 day；
    3. list_days：只列出有笔记的日期且倒序；
    4. delete_note：删除成功返回真、不存在返回假；
    5. keywords 往返：写入的关键词能原样取回。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_notes -v
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
import memory_notes


class _DBBase(unittest.TestCase):
    """记忆库重定向到临时目录，测试互不干扰、不碰真实库。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memnotes_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestAddAndList(_DBBase):
    """写入与列举。"""

    def test_add_journal_returns_id(self):
        """写入每日记忆应返回非空 id。"""
        nid = memory_notes.add_note("journal", "今天的进展", day="2026-10-09")
        self.assertTrue(nid)

    def test_journal_uses_today_when_day_absent(self):
        """未传 day 时，journal 应自动补当天日期。"""
        memory_notes.add_note("journal", "条目")
        rows = memory_notes.list_notes(kind="journal")
        self.assertTrue(rows)
        self.assertTrue(rows[0]["day"])   # day 非空

    def test_notebook_has_no_day(self):
        """错题本条目不应带日期。"""
        memory_notes.add_note("notebook", "一个教训")
        rows = memory_notes.list_notes(kind="notebook")
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["day"])

    def test_list_filter_by_kind(self):
        """按类型过滤应只返回该类型条目。"""
        memory_notes.add_note("journal", "j")
        memory_notes.add_note("notebook", "n")
        self.assertEqual(len(memory_notes.list_notes(kind="journal")), 1)
        self.assertEqual(len(memory_notes.list_notes(kind="notebook")), 1)

    def test_list_filter_by_day(self):
        """按日期过滤应只返回该日条目。"""
        memory_notes.add_note("journal", "a", day="2026-10-08")
        memory_notes.add_note("journal", "b", day="2026-10-09")
        rows = memory_notes.list_notes(kind="journal", day="2026-10-09")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "b")

    def test_keywords_roundtrip(self):
        """写入的关键词应能原样取回。"""
        memory_notes.add_note("notebook", "教训", keywords=["测试", "教训"])
        rows = memory_notes.list_notes(kind="notebook")
        self.assertEqual(rows[0]["keywords"], ["测试", "教训"])


class TestListDays(_DBBase):
    """日期列表。"""

    def test_lists_days_desc(self):
        """应列出有笔记的日期且倒序。"""
        memory_notes.add_note("journal", "a", day="2026-10-07")
        memory_notes.add_note("journal", "b", day="2026-10-09")
        days = memory_notes.list_days()
        self.assertEqual(days, ["2026-10-09", "2026-10-07"])

    def test_no_journal_returns_empty(self):
        """无每日记忆时返回空列表。"""
        memory_notes.add_note("notebook", "n")
        self.assertEqual(memory_notes.list_days(), [])


class TestDelete(_DBBase):
    """删除。"""

    def test_delete_existing(self):
        """删除存在的条目返回真。"""
        nid = memory_notes.add_note("journal", "x", day="2026-10-09")
        self.assertTrue(memory_notes.delete_note(nid))
        self.assertEqual(memory_notes.list_notes(kind="journal"), [])

    def test_delete_missing_returns_false(self):
        """删除不存在的条目返回假。"""
        self.assertFalse(memory_notes.delete_note(999999))


if __name__ == "__main__":
    unittest.main()
