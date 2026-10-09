"""事件层：聚类、突触、护栏的边界测试。

背景：
    memory_events 负责把跨会话讲同一件事的用户发言聚成事件、按关键词
    交集建突触边，并维护三条护栏（边界锚定 / 语义化延迟 / 修订留痕）。
    它由后台调度自动运行，此前无任何测试——出错会静默污染记忆结构。

验证目标：
    1. 纯判定：_related 包含式匹配、_adaptive_threshold 自适应门槛、
       _grams 子串提取、UnionFind 路径压缩；
    2. cluster_events：共享关键词达门槛的 user 节点聚成一簇，单节点不成事件；
    3. build_synapses：关键词交集达门槛时建关联边；
    4. 护栏：影子摘要读取、边界锚定留痕、事件合并与事件树组装。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_events -v
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
import memory_events


def _mk_user_node(msg_id, essence, keywords):
    """写入一个带蒸馏关键词的 user 节点，供聚类 / 建边命中。

    @return 节点 id
    """
    nid = memory_nodes.upsert_node(
        {"msg_id": msg_id, "conv_id": "c1", "site_key": "s1"},
        {"source": "user", "role": "user", "name": "u", "blocks": []},
    )
    import memory_keywords as kw
    memory_nodes.set_essence(nid, essence, keywords, kw.text_to_vector(essence))
    return nid


class _DBBase(unittest.TestCase):
    """把记忆库重定向到临时目录，测试互不干扰、不碰真实库。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memevents_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestPureHelpers(unittest.TestCase):
    """不依赖数据库的纯判定函数。"""

    def test_related_containment_hit(self):
        """一个词是另一个的子串，应算命中。"""
        hits = memory_events._related({"网页版机器人"}, {"网页版机器人语音"})
        self.assertEqual(hits, {"网页版机器人"})

    def test_related_takes_shorter(self):
        """命中项应取较短的那个词。"""
        hits = memory_events._related({"语音自动播放"}, {"语音"})
        self.assertEqual(hits, {"语音"})

    def test_related_no_overlap(self):
        """无包含关系时交集为空。"""
        self.assertEqual(memory_events._related({"苹果"}, {"香蕉"}), set())

    def test_adaptive_threshold_small_sets(self):
        """关键词各 1~2 个时，门槛降为 1，避免永远建不成边。"""
        self.assertEqual(memory_events._adaptive_threshold({"a"}, {"b"}), 1)
        self.assertEqual(memory_events._adaptive_threshold({"a", "b"}, {"c", "d"}), 1)

    def test_adaptive_threshold_mid_sets(self):
        """各 3~4 个词时门槛为 2。"""
        self.assertEqual(
            memory_events._adaptive_threshold({"a", "b", "c"}, {"d", "e", "f"}), 2)

    def test_adaptive_threshold_large_sets(self):
        """各 ≥5 个词时门槛封顶为 3。"""
        big = {"a", "b", "c", "d", "e"}
        self.assertEqual(memory_events._adaptive_threshold(big, big), 3)

    def test_grams_include_single_and_double(self):
        """子串集合应同时含单字与双字。"""
        g = memory_events._grams("语音")
        self.assertIn("语", g)
        self.assertIn("音", g)
        self.assertIn("语音", g)


class TestUnionFind(unittest.TestCase):
    """并查集行为。"""

    def test_find_isolated(self):
        """未合并的节点，根是自己。"""
        uf = memory_events.UnionFind([1, 2, 3])
        self.assertEqual(uf.find(1), 1)

    def test_union_links_members(self):
        """合并后两节点根相同。"""
        uf = memory_events.UnionFind([1, 2, 3])
        uf.union(1, 2)
        self.assertEqual(uf.find(1), uf.find(2))

    def test_union_is_idempotent(self):
        """重复合并同一对不应出错，根保持一致。"""
        uf = memory_events.UnionFind([1, 2])
        uf.union(1, 2)
        uf.union(1, 2)
        self.assertEqual(uf.find(1), uf.find(2))


class TestClusterEvents(_DBBase):
    """事件聚类：跨会话同主题发言聚成一簇。"""

    def test_shared_keywords_cluster_together(self):
        """共享关键词达门槛的两个 user 节点，应聚成一个事件。"""
        a = _mk_user_node("u1", "网页版机器人语音播放", ["网页版机器人", "语音播放"])
        b = _mk_user_node("u2", "网页版机器人语音断连", ["网页版机器人", "语音播放"])
        events = memory_events.cluster_events(min_shared=2)
        members = [sorted(v) for v in events.values()]
        self.assertIn(sorted([a, b]), members)

    def test_single_node_not_an_event(self):
        """只有一个节点时不应产生事件（事件至少两节点）。"""
        _mk_user_node("u1", "孤立主题", ["孤立"])
        events = memory_events.cluster_events(min_shared=2)
        self.assertEqual(events, {})

    def test_unrelated_nodes_stay_separate(self):
        """关键词完全不相干时不应聚到一起。"""
        _mk_user_node("u1", "苹果种植", ["苹果", "种植"])
        _mk_user_node("u2", "香蕉运输", ["香蕉", "运输"])
        events = memory_events.cluster_events(min_shared=2)
        self.assertEqual(events, {})


class TestBuildSynapses(_DBBase):
    """突触建边：关键词交集达门槛时建关联边。"""

    def test_builds_edge_on_high_overlap(self):
        """交集充足且 Jaccard 达标时，应建出关联边。"""
        a = _mk_user_node("u1", "网页版机器人语音", ["网页版机器人", "语音", "自动播放"])
        b = _mk_user_node("u2", "网页版机器人语音续", ["网页版机器人", "语音", "自动播放"])
        count = memory_events.build_synapses(b)
        self.assertGreaterEqual(count, 1)
        neighbors = memory_edges_neighbors(a)
        self.assertIn(b, neighbors)

    def test_no_edge_without_keywords(self):
        """新节点无关键词时不应建边。"""
        nid = memory_nodes.upsert_node(
            {"msg_id": "u9", "conv_id": "c1", "site_key": "s1"},
            {"source": "user", "role": "user", "name": "u", "blocks": []},
        )
        self.assertEqual(memory_events.build_synapses(nid), 0)


def memory_edges_neighbors(node_id):
    """取节点的关联邻居 id 集合（测试辅助）。"""
    import memory_edges
    return {n["id"] if isinstance(n, dict) else n
            for n in memory_edges.get_neighbors(node_id, kind="associative")}


class TestGuardrails(_DBBase):
    """三条护栏：影子摘要、边界锚定、修订留痕与事件合并。"""

    def test_shadow_roundtrip(self):
        """写入影子摘要后应能取回；无影子返回 None。"""
        nid = _mk_user_node("u1", "原句", ["词"])
        self.assertIsNone(memory_events.get_shadow(nid))
        memory_events.set_shadow(nid, "这是摘要")
        self.assertEqual(memory_events.get_shadow(nid), "这是摘要")

    def test_anchor_boundary_logs_revision(self):
        """边界锚定应写一条修订日志，可在历史里查到。"""
        nid = _mk_user_node("u1", "原句", ["词"])
        memory_events.anchor_boundary(nid, "边界原句", "topic-change")
        hist = memory_events.event_history(nid)
        self.assertTrue(any(h["reason"].startswith("boundary:") for h in hist))

    def test_event_merge_and_tree(self):
        """合并事件后，事件树应含根与被并入成员。"""
        root = _mk_user_node("u1", "根事件", ["词"])
        m1 = _mk_user_node("u2", "成员一", ["词2"])
        merged = memory_events.event_merge(root, [m1], reason="manual")
        self.assertEqual(merged, 1)
        tree = memory_events.event_tree_get(root)
        self.assertIsNotNone(tree)
        member_ids = [m["id"] for m in tree["members"]]
        self.assertIn(m1, member_ids)

    def test_event_tree_missing_root(self):
        """根不存在时返回 None。"""
        self.assertIsNone(memory_events.event_tree_get(999999))


if __name__ == "__main__":
    unittest.main()
