"""会话级读写：保存 / 取回 / 删除清理 / 悬空引用的边界测试。

背景：
    memory_conversations 负责把整棵消息树存进库、取出来，以及删除会话
    时清理节点、边、卡片、修订日志与笔记。此前无任何测试，且本项目发生过
    「会话删除后残留大量孤儿死数据」的事故，故本文件重点覆盖删除清理路径。

验证目标：
    1. 纯辅助：_key_child 取子指纹、_infer_source 来源推断、_scan_tree 建映射；
    2. 保存与取回：同步保存一棵树后能原样重建 msgTree；
    3. 删除清理：删除会话后，节点、会话元数据、卡片均不残留；
    4. 悬空引用：prune_dangling_refs 只剔除指向已删节点的引用。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_conversations -v
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
import memory_conversations as mc


def _conv(conv_id, tree, **kw):
    """构造一个前端会话对象（含 msgTree 与可选元数据）。"""
    base = {"title": "标题", "page_url": "http://x", "msgTree": tree}
    base.update(kw)
    return base


def _node(role, text):
    """构造一个最简前端节点。"""
    return {"role": role, "name": role, "source": role,
            "blocks": [{"type": "text", "text": text}], "cards": {}}


class _DBBase(unittest.TestCase):
    """记忆库重定向到临时目录，测试互不干扰、不碰真实库。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memconv_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")
        # 清空增量签名缓存，避免上一用例的缓存影响本用例
        with mc._sig_lock:
            mc._saved_sig.clear()

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPureHelpers(unittest.TestCase):
    """不依赖数据库的纯辅助函数。"""

    def test_key_child_extracts_child(self):
        """从树键里应取出子指纹。"""
        self.assertEqual(mc._key_child("0-abc"), "abc")
        self.assertEqual(mc._key_child("p-c"), "c")

    def test_key_child_without_dash(self):
        """无短横线时原样返回。"""
        self.assertEqual(mc._key_child("abc"), "abc")

    def test_infer_source_by_role(self):
        """按 role 推断来源。"""
        self.assertEqual(mc._infer_source({"role": "user"}), "user")
        self.assertEqual(mc._infer_source({"role": "assistant"}), "assistant")
        self.assertEqual(mc._infer_source({"role": "tool"}), "tool")

    def test_scan_tree_builds_maps(self):
        """预扫应正确建出父子映射与子边计数。"""
        tree = {"0-a": _node("user", "hi"), "a-b": _node("assistant", "yo"),
                "a-c": _node("assistant", "yo2")}
        node_by_msg, parent_of, child_count, edges = mc._scan_tree({"msgTree": tree})
        self.assertEqual(set(node_by_msg), {"a", "b", "c"})
        self.assertEqual(parent_of["b"], "a")
        self.assertEqual(child_count["a"], 2)   # a 有两个子，判 branch
        self.assertEqual(len(edges), 3)


class TestSaveAndLoad(_DBBase):
    """同步保存与取回。"""

    def test_roundtrip_restores_tree(self):
        """保存一棵树后取回，节点内容应一致。"""
        tree = {"0-a": _node("user", "你好"), "a-b": _node("assistant", "回复")}
        mc._save_conversation_sync("c1", "s1", _conv("c1", tree, title="会话一"))
        loaded = mc.load_conversation("c1", "s1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["title"], "会话一")
        self.assertIn("0-a", loaded["msgTree"])
        self.assertIn("a-b", loaded["msgTree"])

    def test_load_missing_returns_none(self):
        """取不存在的会话应返回 None。"""
        self.assertIsNone(mc.load_conversation("nope", "s1"))

    def test_list_conversations(self):
        """列出会话应包含已保存的会话。"""
        tree = {"0-a": _node("user", "x")}
        mc._save_conversation_sync("c1", "s1", _conv("c1", tree))
        items = mc.list_conversations(site_key="s1")
        self.assertTrue(any(i["conv_id"] == "c1" for i in items))


class TestDeleteCleanup(_DBBase):
    """删除会话：节点、边、卡片、元数据均不应残留。"""

    def test_delete_removes_nodes_and_meta(self):
        """删除后节点与会话元数据都应清空。"""
        tree = {"0-a": _node("user", "你好"), "a-b": _node("assistant", "回复")}
        mc._save_conversation_sync("c1", "s1", _conv("c1", tree))
        removed = mc.delete_conversation("c1", "s1")
        self.assertEqual(removed, 2)
        conn = memory_db.get_conn()
        left = conn.execute(
            "SELECT COUNT(*) AS n FROM nodes WHERE conv_id=? AND site_key=?",
            ("c1", "s1")).fetchone()["n"]
        self.assertEqual(left, 0)
        self.assertIsNone(mc.load_conversation("c1", "s1"))

    def test_delete_clears_sig_cache(self):
        """删除应清除该会话的增量签名缓存。"""
        tree = {"0-a": _node("user", "你好")}
        mc._save_conversation_sync("c1", "s1", _conv("c1", tree))
        self.assertTrue(any(k[0] == "c1" for k in mc._saved_sig))
        mc.delete_conversation("c1", "s1")
        self.assertFalse(any(k[0] == "c1" for k in mc._saved_sig))

    def test_delete_leaves_no_orphan_edges(self):
        """删除后不应残留指向已删节点的边（防孤儿死数据）。"""
        tree = {"0-a": _node("user", "你好"), "a-b": _node("assistant", "回复")}
        mc._save_conversation_sync("c1", "s1", _conv("c1", tree))
        mc.delete_conversation("c1", "s1")
        conn = memory_db.get_conn()
        n = conn.execute("SELECT COUNT(*) AS n FROM edges").fetchone()["n"]
        self.assertEqual(n, 0)


class TestPruneDangling(_DBBase):
    """悬空引用清理。"""

    def test_prune_removes_ref_to_deleted_node(self):
        """会话引用里指向已不存在节点的树键，应被剔除。"""
        tree = {"0-a": _node("user", "你好"), "a-b": _node("assistant", "回复")}
        # 会话元数据里带上对 a、b 的引用
        conv = _conv("c1", tree, visibleKeys=["0-a", "a-b"])
        mc._save_conversation_sync("c1", "s1", conv)
        # 删除节点 b，使 visibleKeys 里的 "a-b" 变成悬空
        b = memory_nodes.get_by_msg_id("b")
        memory_nodes.hard_delete(b["id"])
        removed = mc.prune_dangling_refs()
        self.assertGreaterEqual(removed, 1)
        loaded = mc.load_conversation("c1", "s1")
        self.assertNotIn("a-b", loaded["visibleKeys"])
        self.assertIn("0-a", loaded["visibleKeys"])

    def test_prune_keeps_valid_refs(self):
        """全部引用有效时，不应剔除任何项。"""
        tree = {"0-a": _node("user", "你好")}
        conv = _conv("c1", tree, visibleKeys=["0-a"])
        mc._save_conversation_sync("c1", "s1", conv)
        self.assertEqual(mc.prune_dangling_refs(), 0)


if __name__ == "__main__":
    unittest.main()
