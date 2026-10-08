"""AI 工具调用镜像插件 —— 记忆系统：启动加载层

职责：服务启动时把规则与记忆一次性读进内存，供接口快速读取，
避免每次请求都读盘。这是「启动时加载到内存」这一改造方向的落点。

加载内容：
  - 规则：rules/ 下的规则文件，按优先级解析；
  - 记忆摘要：节点的精华与关键词，构建内存索引。

依赖：paths、memory_nodes、threading
"""
import json
import threading

import paths
import memory_nodes

# 内存缓存：启动时填充，接口读取优先走这里
_CACHE = {
    "rules": {},       # { 规则名: 内容 }
    "nodes": {},       # { node_id: 摘要 }
    "kw_index": {},    # { 关键词: set(node_id) } 倒排索引，供检索快速预筛
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
        kw_index = {}
        for r in rows:
            nodes[r["id"]] = {
                "id": r["id"], "source": r["source"],
                "essence": r["essence"], "keywords": r["keywords"],
                "tier": r["tier"], "strength": r["strength"],
            }
            # 构建关键词倒排索引：{ 关键词: {node_id, ...} }，供内存预筛。
            # 关键词字段存的是 JSON 数组字符串，逐条解析；解析失败跳过该节点。
            try:
                kws = json.loads(r["keywords"] or "[]")
            except Exception:
                kws = []
            for k in kws:
                if k:
                    kw_index.setdefault(str(k), set()).add(r["id"])
        _CACHE["nodes"] = nodes
        _CACHE["kw_index"] = kw_index
        _CACHE["loaded"] = True
    return {"rules": len(_CACHE["rules"]), "nodes": len(_CACHE["nodes"]),
            "keywords": len(_CACHE["kw_index"])}


def _ensure_loaded():
    """缓存未加载时惰性重载一次。

    使 invalidate() 真正生效：调用 invalidate() 后 loaded 置假，
    下次读取经此触发一次全量重载，从而看到最新的规则与节点，
    不再出现「写后内存仍旧值、直到重启才刷新」的问题。
    """
    if _CACHE.get("loaded"):
        return
    load_all()


def get_rules():
    """取内存中的规则字典；缓存失效时先重载。"""
    _ensure_loaded()
    return _CACHE.get("rules") or {}


def get_node_summary(node_id):
    """从内存取节点摘要；未命中返回 None；缓存失效时先重载。"""
    _ensure_loaded()
    return (_CACHE.get("nodes") or {}).get(node_id)


def keyword_prefilter(keywords, limit=None):
    """基于内存倒排索引做关键词预筛：返回按命中关键词数降序的 node_id 列表。

    这是「接口读取优先走内存」的落点：检索先在此拿到候选，避免每次都全库 LIKE。
    未加载或索引为空时返回 None，调用方据此回退到数据库查询。
    @param keywords 关键词列表
    @param limit 返回上限；None 表示不限
    @return [(node_id, hit_count)] 或 None（缓存不可用时）
    """
    if not _CACHE.get("loaded"):
        return None
    index = _CACHE.get("kw_index") or {}
    if not index:
        return None
    scores = {}
    for kw in (keywords or []):
        if not kw:
            continue
        # 子串命中：内存索引按精确关键词建，此处做包含式匹配以兼容中文短语。
        for key, ids in index.items():
            if kw in key or key in kw:
                for nid in ids:
                    scores[nid] = scores.get(nid, 0) + 1
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ordered[:limit] if limit else ordered


def is_loaded():
    """是否已完成启动加载。"""
    return bool(_CACHE.get("loaded"))


def invalidate():
    """使缓存失效（写入记忆后调用，下次读取重载）。"""
    with _LOCK:
        _CACHE["loaded"] = False
