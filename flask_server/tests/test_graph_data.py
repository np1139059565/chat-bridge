"""记忆图谱数据组装：增量过滤与整形的测试。

背景：
    graph_data 把记忆节点与边整形成前端图谱需要的字段，含增量过滤
    （只下发新节点与相关边）。此前无任何测试。

验证目标：
    1. apply_since：since_id 为 0 时全量返回；非 0 时只留新节点；
       边只保留「至少一端是新节点」的；
    2. shape_nodes：只保留前端需要的字段，created_at 缺省补 0；
    3. shape_edges：keywords 由 JSON 字符串转数组，非法串转空数组。

运行方式（在 flask_server/ 目录下）：
    python -m unittest tests.test_graph_data -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paths  # noqa: F401  触发路径引导
import graph_data


class TestApplySince(unittest.TestCase):
    """增量过滤。"""

    def test_zero_since_returns_all(self):
        """since_id 为 0 时全量返回。"""
        nodes = [{"id": 1}, {"id": 2}]
        edges = [{"src_node": 1, "dst_node": 2}]
        n, e = graph_data.apply_since(nodes, edges, 0)
        self.assertEqual(len(n), 2)
        self.assertEqual(len(e), 1)

    def test_filters_old_nodes(self):
        """只保留 id 大于 since_id 的节点。"""
        nodes = [{"id": 1}, {"id": 5}, {"id": 9}]
        n, _ = graph_data.apply_since(nodes, [], 4)
        self.assertEqual([x["id"] for x in n], [5, 9])

    def test_keeps_edges_touching_new_nodes(self):
        """只保留至少一端是新节点的边。"""
        nodes = [{"id": 10}]
        edges = [{"src_node": 1, "dst_node": 2},   # 两端都旧，应丢弃
                 {"src_node": 1, "dst_node": 10},  # 一端新，应保留
                 {"src_node": 10, "dst_node": 3}]  # 一端新，应保留
        _, e = graph_data.apply_since(nodes, edges, 5)
        self.assertEqual(len(e), 2)
        for edge in e:
            self.assertTrue(edge["src_node"] == 10 or edge["dst_node"] == 10)


class TestShapeNodes(unittest.TestCase):
    """节点整形。"""

    def test_keeps_expected_fields(self):
        """应保留前端需要的字段。"""
        raw = [{"id": 1, "source": "user", "tier": "perm", "strength": 0.9,
                "essence": "e", "keywords": ["k"], "created_at": 123,
                "blocks": ["不应出现"]}]
        out = graph_data.shape_nodes(raw)
        self.assertEqual(out[0]["id"], 1)
        self.assertEqual(out[0]["created_at"], 123)
        self.assertNotIn("blocks", out[0])

    def test_created_at_defaults_zero(self):
        """created_at 缺失时补 0。"""
        out = graph_data.shape_nodes([{"id": 1, "source": "user"}])
        self.assertEqual(out[0]["created_at"], 0)


class TestShapeEdges(unittest.TestCase):
    """边整形。"""

    def test_json_keywords_to_list(self):
        """keywords 为 JSON 字符串时应转成数组。"""
        edges = [{"keywords": '["a", "b"]'}]
        out = graph_data.shape_edges(edges)
        self.assertEqual(out[0]["keywords"], ["a", "b"])

    def test_invalid_json_becomes_empty(self):
        """非法 JSON 的 keywords 应转成空数组。"""
        edges = [{"keywords": "{bad"}]
        out = graph_data.shape_edges(edges)
        self.assertEqual(out[0]["keywords"], [])

    def test_empty_keywords_becomes_empty(self):
        """空 keywords 应转成空数组。"""
        edges = [{"keywords": ""}]
        out = graph_data.shape_edges(edges)
        self.assertEqual(out[0]["keywords"], [])


if __name__ == "__main__":
    unittest.main()
