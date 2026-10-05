"""AI 工具调用镜像插件 —— 记忆系统：启动加载层

职责：服务启动时把规则与记忆一次性读进内存，供接口快速读取，
避免每次请求都读盘。这是「启动时加载到内存」这一改造方向的落点。

加载内容：
  - 规则：rules/ 下的规则文件，按优先级解析；
  - 记忆摘要：节点的精华与关键词，构建内存索引。

依赖：paths、memory_nodes、threading
"""
import threading

import paths
import memory_nodes

# 内存缓存：启动时填充，接口读取优先走这里
_CACHE = {
    "rules": {},       # { 规则名: 内容 }
    "nodes": {},       # { node_id: 摘要 }
    "loaded": False,
}
_LOCK = threading.Lock()


def load_rules():
    """读 rules/ 下全部 .md 规则文件进内存。"""
    out = {}
    rules_dir = paths.RULES_DIR
    if rules_dir.is_dir():
        for f in sorted(rules_dir.glob("*.md")):
            try:
                out[f.stem] = f.read_text(encoding="utf-8")
            except Exception as e:
                print("[memory] 规则读取失败 %s: %s" % (f, e))
    return out


def load_all():
    """启动加载：规则 + 记忆摘要，一次性填入内存缓存。

    记忆摘要只放轻量字段（精华、关键词、分级、强度），不含 blocks 与向量，
    避免内存膨胀。需要完整节点时再按 id 回库取。
    """
    with _LOCK:
        _CACHE["rules"] = load_rules()
        conn = memory_nodes.get_conn()
        rows = conn.execute(
            "SELECT id, source, essence, keywords, tier, strength FROM nodes WHERE deleted=0"
        ).fetchall()
        nodes = {}
        for r in rows:
            nodes[r["id"]] = {
                "id": r["id"], "source": r["source"],
                "essence": r["essence"], "keywords": r["keywords"],
                "tier": r["tier"], "strength": r["strength"],
            }
        _CACHE["nodes"] = nodes
        _CACHE["loaded"] = True
    return {"rules": len(_CACHE["rules"]), "nodes": len(_CACHE["nodes"])}


def get_rules():
    """取内存中的规则字典。"""
    return _CACHE.get("rules") or {}


def get_node_summary(node_id):
    """从内存取节点摘要；未命中返回 None。"""
    return (_CACHE.get("nodes") or {}).get(node_id)


def is_loaded():
    """是否已完成启动加载。"""
    return bool(_CACHE.get("loaded"))


def invalidate():
    """使缓存失效（写入记忆后调用，下次读取重载）。"""
    with _LOCK:
        _CACHE["loaded"] = False
