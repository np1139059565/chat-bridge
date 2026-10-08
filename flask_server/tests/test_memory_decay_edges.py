"""分级/衰减与突触强化：测试。

背景：
    1. 突触边重复激活时，强化增量应随交集关键词数缩放（此前固定 +0.2，
       与交集数无关，是设计断层）。
    2. 图遍历取邻居时应带权重并按其排序（此前只判连通、不看权重）。
    3. 分级 _next_tier 应有升级与保守降级路径，perm 不降。

验证目标：
    1. add_edge 的 reinforce_delta 生效：增量越大，权重涨得越多；
    2. neighbors_with_weight 按权重降序返回；
    3. _next_tier 升级 / 降级 / perm 不降。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_memory_decay_edges -v
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
import memory_edges
import memory_decay


class TestDecayEdges(unittest.TestCase):
    """验证突触强化缩放、带权邻居排序、分级升降。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="memdecay_test_")
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")

    def tearDown(self):
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _edge_weight(self, src, dst):
        conn = memory_db.get_conn()
        row = conn.execute(
            "SELECT weight FROM edges WHERE src_node=? AND dst_node=? AND kind='associative'",
            (src, dst)).fetchone()
        return float(row["weight"]) if row else None

    def test_reinforce_delta_scales(self):
        """强化增量越大，重复激活后权重越高——增量随交集数缩放。"""
        # 边 A：小增量；边 B：大增量。从同一初值出发，各强化一次。
        memory_edges.add_edge(1, 2, "associative", weight=0.5)
        memory_edges.add_edge(3, 4, "associative", weight=0.5)
        memory_edges.reinforce_edge(1, 2, "associative", delta=0.04)
        memory_edges.reinforce_edge(3, 4, "associative", delta=0.2)
        w_small = self._edge_weight(1, 2)
        w_large = self._edge_weight(3, 4)
        self.assertAlmostEqual(w_small, 0.5 + 0.04 * 0.5, places=4)
        self.assertAlmostEqual(w_large, 0.5 + 0.2 * 0.5, places=4)
        self.assertGreater(w_large, w_small)

    def test_neighbors_with_weight_sorted(self):
        """neighbors_with_weight 应按权重降序返回邻居。"""
        memory_edges.add_edge(10, 1, "associative", weight=0.3)
        memory_edges.add_edge(10, 2, "associative", weight=0.9)
        memory_edges.add_edge(10, 3, "associative", weight=0.6)
        nbrs = memory_edges.neighbors_with_weight(10, "associative")
        weights = [w for _nid, w in nbrs]
        self.assertEqual(weights, sorted(weights, reverse=True))
        self.assertGreaterEqual(weights[0], weights[-1])

    def test_next_tier_upgrade_temp_to_mid(self):
        """temp→mid：命中≥3 且强度≥0.6。"""
        node = {"tier": "temp", "hit_count": 3}
        self.assertEqual(memory_decay._next_tier(node, 0.7), "mid")

    def test_next_tier_upgrade_mid_to_perm(self):
        """mid→perm：命中≥10 且强度≥0.8。"""
        node = {"tier": "mid", "hit_count": 10}
        self.assertEqual(memory_decay._next_tier(node, 0.85), "perm")

    def test_next_tier_downgrade_mid_to_temp(self):
        """mid→temp：强度<0.3 且命中<3 时保守降级。"""
        node = {"tier": "mid", "hit_count": 2}
        self.assertEqual(memory_decay._next_tier(node, 0.25), "temp")

    def test_next_tier_mid_stays_when_hit_enough(self):
        """mid 命中足够时即使强度低也不降级。"""
        node = {"tier": "mid", "hit_count": 5}
        self.assertEqual(memory_decay._next_tier(node, 0.25), "mid")

    def test_next_tier_perm_never_downgrades(self):
        """perm 永不自动降级（文档规定）。"""
        node = {"tier": "perm", "hit_count": 0}
        self.assertEqual(memory_decay._next_tier(node, 0.1), "perm")

    def test_compute_strength_in_range(self):
        """强度计算应落在 0~1 区间。"""
        node = {"tier": "temp", "hit_count": 0, "created_at": 1}
        s = memory_decay.compute_strength(node, 0.0)
        self.assertGreaterEqual(s, 0.0)
        self.assertLessEqual(s, 1.0)


if __name__ == "__main__":
    unittest.main()
