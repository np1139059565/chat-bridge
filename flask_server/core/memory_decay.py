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
from memory_db import begin_batch, end_batch

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


# 分批提交的批大小：每处理这么多节点提交一次。
# 取值权衡：太小则提交次数多、慢（逐节点提交曾使全量重算耗时 8.5 秒）；
# 太大则单次持写锁时间长、阻塞前台。200 是二者的折中。
_COMMIT_BATCH = 200


def recompute_all():
    """遍历全部节点，重算强度并写回；返回 (处理数, 升级数, 降级数)。

    分批提交：每 _COMMIT_BATCH 个节点提交一次，而非逐个提交。
    逐节点提交会让 4000+ 节点产生 4000+ 次磁盘同步，是全量重算耗时的主要来源；
    分批后提交次数降到约 1/200，同时每批结束即释放写锁，不长时间独占。
    """
    conn = memory_nodes.get_conn()
    # 一次性取出重算所需的全部字段（不含庞大的 blocks，避免无谓读放大）：
    # 逐节点 get_node 会产生 N 次查询并读入 blocks，是全量重算的另一耗时来源。
    rows = conn.execute(
        "SELECT id, tier, hit_count, last_hit_at, created_at FROM nodes WHERE deleted=0"
    ).fetchall()
    upgraded = downgraded = 0
    # 一次性预取全部节点的关联边权重和：把「每节点查一次边表」的 N 次查询
    # 降为 2 次聚合查询，这是全量重算的主要提速点。
    weight_sums = memory_edges.associative_weight_sums()
    begin_batch()                       # 进入批量模式：写操作暂不逐条提交
    pending = []                        # 待批量写入的 (id, strength, tier)
    try:
        for r in rows:
            nid = r["id"]
            node = {
                "tier": r["tier"], "hit_count": r["hit_count"],
                "last_hit_at": r["last_hit_at"], "created_at": r["created_at"],
            }
            wsum = weight_sums.get(nid, 0.0)
            strength = compute_strength(node, wsum)
            # 自动升降级
            new_tier = _next_tier(node, strength)
            if new_tier != node.get("tier"):
                if TIER_BASE.get(new_tier, 0) > TIER_BASE.get(node.get("tier"), 0):
                    upgraded += 1
                else:
                    downgraded += 1
            pending.append((nid, strength, new_tier))
            # 每满一批：批量写入并提交、释放写锁，随后重开批量模式继续
            if len(pending) >= _COMMIT_BATCH:
                memory_nodes.bulk_set_strength_tier(pending)
                pending = []
                end_batch(conn)
                begin_batch()
        # 收尾：写入剩余不足一批的改动
        if pending:
            memory_nodes.bulk_set_strength_tier(pending)
    finally:
        end_batch(conn)                 # 提交最后不足一批的改动
    # 边衰减单独做（其内部逐边短事务更新）
    memory_edges.decay_edges()
    return len(rows), upgraded, downgraded


def _next_tier(node, strength):
    """根据命中次数与强度决定下一分级；返回 tier 字符串。

    升级：temp→mid（hit≥3 且 strength≥0.6）、mid→perm（hit≥10 且 strength≥0.8）。
    降级：mid 长期不命中、强度跌破 0.3 且命中不足 3 次时降回 temp，
          避免「一次偶然升到 mid 就永远占位」。perm 不降级（文档规定，除非用户显式删除）。
    """
    tier = node.get("tier") or "temp"
    hit = int(node.get("hit_count") or 0)
    if tier == "temp" and hit >= 3 and strength >= 0.6:
        return "mid"
    if tier == "mid" and hit >= 10 and strength >= 0.8:
        return "perm"
    # 降级路径：仅对 mid 生效，perm 永不自动降级。
    if tier == "mid" and strength < 0.3 and hit < 3:
        return "temp"
    return tier
