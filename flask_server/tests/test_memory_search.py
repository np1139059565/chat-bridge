"""检索层：双接口防幻觉测试。

背景：
    memory_search 是防幻觉核心——关键词必须逐字出现在计划原文里，
    否则拒绝；三路检索融合后乘关键词交集置信度。此前无任何测试。

验证目标：
    1. plan_submit 存计划原文并返回 plan_id；
    2. 锚定验证：不在计划原文里的关键词被拒；
    3. 命中：关键词在计划原文中，且库里有含该词的节点，则返回；
    4. 全被拒时返回空 hits；
    5. 内存倒排索引预筛（keyword_prefilter）可用时不影响结果。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_search -v
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
import memory_search


def _mk_node(msg_id, essence, keywords):
    """写入一个带蒸馏字段的节点，供检索命中。

    节点先 upsert（只需 msg_id），再 set_essence 写精华/关键词/向量。
    @return 节点 id
    """
    nid = memory_nodes.upsert_node(
        {"msg_id": msg_id, "conv_id": "c1", "site_key": "s1"},
        {"source": "assistant", "role": "assistant", "name": "ai", "blocks": []},
    )
    import memory_keywords as kw
    vec = kw.text_to_vector(essence)
    memory_nodes.set_essence(nid, essence, keywords, vec)
    return nid


class TestMemorySearch(unittest.TestCase):
    """验证锚定验证、命中与拒绝、内存预筛。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memsearch_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_plan_submit_returns_id(self):
        """plan_submit 应返回非空 plan_id，且能取回原文。"""
        pid = memory_search.plan_submit("排查网页版机器人连接断开问题")
        self.assertTrue(pid)
        plan = memory_search.get_plan(pid)
        self.assertIn("机器人", plan["text"])

    def test_anchor_rejects_absent_keywords(self):
        """关键词不在计划原文里时，应被拒绝、返回空 hits。"""
        pid = memory_search.plan_submit("任务：修复登录")
        res = memory_search.memory_search(pid, ["不存在的词"], top_k=5)
        self.assertEqual(res["hits"], [])
        self.assertIn("不存在的词", res["rejected"])

    def test_search_hits_matching_node(self):
        """关键词在计划原文中、且库里有匹配节点时，应命中。"""
        _mk_node("m1", "网页版机器人语音自动播放的实现", ["网页版机器人语音"])
        pid = memory_search.plan_submit("继续处理 网页版机器人语音 的问题")
        res = memory_search.memory_search(pid, ["网页版机器人语音"], top_k=5)
        self.assertGreaterEqual(len(res["hits"]), 1)
        self.assertTrue(res["plan_found"])

    def test_all_rejected_returns_empty(self):
        """全部关键词都不在计划原文里时，返回空结果。"""
        pid = memory_search.plan_submit("另一个完全不同的任务")
        res = memory_search.memory_search(pid, ["alpha", "beta"], top_k=5)
        self.assertEqual(res["hits"], [])
        self.assertEqual(set(res["rejected"]), {"alpha", "beta"})

    def test_keyword_prefilter_returns_none_when_unloaded(self):
        """内存缓存未加载时，keyword_prefilter 应返回 None（调用方回退查库）。"""
        import memory_loader
        memory_loader.invalidate()
        self.assertIsNone(memory_loader.keyword_prefilter(["任意词"]))

    def test_keyword_prefilter_after_load(self):
        """加载后，keyword_prefilter 应能命中已入库的关键词。"""
        _mk_node("m2", "突触权重进检索排序", ["突触权重"])
        import memory_loader
        memory_loader.load_all()
        pre = memory_loader.keyword_prefilter(["突触权重"])
        self.assertIsNotNone(pre)
        self.assertGreaterEqual(len(pre), 1)


if __name__ == "__main__":
    unittest.main()
