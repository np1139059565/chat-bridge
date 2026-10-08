"""记忆图谱 —— 图数据组装（纯函数）

从 routes/memory_graph.py 抽出，使路由层保持精简、文件不越行数上限。
本模块只做数据整形，不碰 Flask 请求对象，便于单独测试。

依赖：json、memory_nodes、memory_edges
"""
import json

import memory_nodes
import memory_edges


def collect_nodes_edges(conv_id, site_key):
    """按会话口径取节点与边（会话留空则取全库）。

    节点与边同口径：
      - 会话 id 留空：两边都返回全库；
      - 会话 id 非空：节点按会话过滤，边只保留两端都在该会话节点集合内的边。
    避免出现「0 节点却配全库边」的口径错位。
    @param conv_id  会话 id（空表示全库）
    @param site_key 站点标识
    @returns (节点列表, 边列表)
    """
    if conv_id:
        raw_nodes = memory_nodes.list_by_conv(conv_id, site_key)
        node_ids = [n["id"] for n in raw_nodes]
        edges = memory_edges.edges_within(node_ids)
    else:
        raw_nodes = memory_nodes.list_all()
        edges = memory_edges.all_edges()
    return raw_nodes, edges


def apply_since(raw_nodes, edges, since_id):
    """增量过滤：只留 id 大于 since_id 的节点，及至少一端是新节点的边。

    @param raw_nodes 原始节点列表
    @param edges     原始边列表
    @param since_id  只返回 id 大于它的内容；0 表示全量
    @returns (过滤后的节点, 过滤后的边)
    """
    if not since_id:
        return raw_nodes, edges
    raw_nodes = [n for n in raw_nodes if n["id"] > since_id]
    keep = set(n["id"] for n in raw_nodes)
    # 只保留「至少一端是新节点」的边，避免重复下发旧边
    edges = [e for e in edges if e.get("src_node") in keep or e.get("dst_node") in keep]
    return raw_nodes, edges


def shape_nodes(raw_nodes):
    """把节点行整形成前端需要的字段。

    @param raw_nodes 节点列表
    @returns 整形后的节点列表
    """
    nodes = []
    for n in raw_nodes:
        nodes.append({
            "id": n["id"], "source": n["source"], "tier": n.get("tier"),
            "strength": n.get("strength"), "essence": n.get("essence"),
            "keywords": n.get("keywords"),
            # created_at：时间轴视图按时间排布节点需要
            "created_at": n.get("created_at") or 0,
        })
    return nodes


def shape_edges(edges):
    """把边的 keywords 由 JSON 字符串转为数组，供前端直接使用。

    @param edges 边列表（就地修改）
    @returns 处理后的边列表
    """
    for e in edges:
        kw = e.get("keywords")
        if isinstance(kw, str) and kw:
            try:
                e["keywords"] = json.loads(kw)
            except Exception:
                e["keywords"] = []
        else:
            e["keywords"] = []
    return edges
