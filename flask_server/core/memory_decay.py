"""AI 工具调用镜像插件 —— 记忆系统：分级与衰减

职责：按方案 4.4 计算节点强度、执行自动升降级、驱动边衰减。

强度公式：
    node_decay_rate = base_decay / (1 + 0.1 * Σ(关联边权重))
    strength = tier_base * (1 + 0.3 * log2(1 + hit_count)) * 2^(-days_since_last_hit / node_decay_rate)
    tier_base：temp=0.3  mid=0.6  perm=1.0

升降级：
    temp→mid：hit_count>=3 且 strength>=0.6
    mid→perm：hit_count>=10 且 strength>=0.8
    perm 不降级。

依赖：memory_nodes、memory_edges、math、time
"""
import math
import time

import memory_nodes
import memory_edges

# 各分级的底子系数
TIER_BASE = {"temp": 0.3, "mid": 0.6, "perm": 1.0}
# 基础衰减率（天）
BASE_DECAY = 30.0


def compute_strength(node, edge_weight_sum):
    """按公式算一个节点的当前强度。

    @param node 节点 dict（含 tier / hit_count / last_hit_at）
    @param edge_weight_sum 该节点全部关联边权重之和
    @return 强度（0~1）
    """
    tier = node.get("tier") or "temp"
    base = TIER_BASE.get(tier, 0.3)
    hit = int(node.get("hit_count") or 0)
    last = node.get("last_hit_at") or node.get("created_at") or int(time.time())
    days = max(0.0, (time.time() - last) / 86400.0)
    # 衰减率受关联边权重影响：强边越多，衰减越慢
    decay_rate = BASE_DECAY / (1.0 + 0.1 * float(edge_weight_sum or 0.0))
    if decay_rate <= 0:
        decay_rate = BASE_DECAY
    hit_factor = 1.0 + 0.3 * math.log2(1.0 + hit)
    time_factor = 2.0 ** (-days / decay_rate)
    s = base * hit_factor * time_factor
    return max(0.0, min(1.0, s))


def recompute_all():
    """遍历全部节点，重算强度并写回；返回 (处理数, 升级数, 降级数)。"""
    conn = memory_nodes.get_conn()
    rows = conn.execute("SELECT id FROM nodes WHERE deleted=0").fetchall()
    upgraded = downgraded = 0
    for r in rows:
        nid = r["id"]
        node = memory_nodes.get_node(nid)
        if not node:
            continue
        wsum = memory_edges.associative_weight_sum(nid)
        strength = compute_strength(node, wsum)
        memory_nodes.set_strength(nid, strength)
        # 自动升降级
        new_tier = _next_tier(node, strength)
        if new_tier != node.get("tier"):
            memory_nodes.set_tier(nid, new_tier)
            if TIER_BASE.get(new_tier, 0) > TIER_BASE.get(node.get("tier"), 0):
                upgraded += 1
            else:
                downgraded += 1
    # 顺带驱动一次边衰减
    memory_edges.decay_edges()
    return len(rows), upgraded, downgraded


def _next_tier(node, strength):
    """根据命中次数与强度决定下一分级；返回 tier 字符串。"""
    tier = node.get("tier") or "temp"
    hit = int(node.get("hit_count") or 0)
    if tier == "temp" and hit >= 3 and strength >= 0.6:
        return "mid"
    if tier == "mid" and hit >= 10 and strength >= 0.8:
        return "perm"
    # perm 不降级；temp/mid 也不主动降（降级由衰减把强度压低后再评估）
    return tier
