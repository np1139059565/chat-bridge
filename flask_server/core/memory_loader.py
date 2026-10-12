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
import app_log

# 内存缓存：启动时填充，接口读取优先走这里
_CACHE = {
    "rules": {},        # { 规则名: 内容 }
    "nodes": {},        # { node_id: 摘要 }
    "gram_index": {},   # { 字片段: set(node_id) } 倒排桶，供检索快速缩候选
    "node_kw": {},      # { node_id: [关键词] } 候选精判用
    "loaded": False,
}
_LOCK = threading.Lock()


def _grams(word):
    """取一个词的 1~2 字连续片段，用于建桶与查桶（含单字以兼容单字关键词）。

    @param word 关键词字符串
    @return 片段集合
    """
    s = str(word or "")
    out = set()
    n = len(s)
    for i in range(n):
        out.add(s[i])               # 单字
        if i + 2 <= n:
            out.add(s[i:i + 2])     # 双字
    return out


def load_rules():
    """读 rules/ 下全部 .md 规则文件进内存。"""
    out = {}
    rules_dir = paths.RULES_DIR
    if rules_dir.is_dir():
        for f in sorted(rules_dir.glob("*.md")):
            try:
                out[f.stem] = f.read_text(encoding="utf-8")
            except Exception as e:
                app_log.warn("[memory]", "规则读取失败 %s: %s" % (f, e))
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
        gram_index = {}      # { gram: {node_id} } —— gram 倒排桶，供快速缩候选
        node_kw = {}         # { node_id: [关键词] } —— 候选精判用
        for r in rows:
            nodes[r["id"]] = {
                "id": r["id"], "source": r["source"],
                "essence": r["essence"], "keywords": r["keywords"],
                "tier": r["tier"], "strength": r["strength"],
            }
            # 为每个关键词的 1~2 字片段建倒排桶：预筛时用查询词的字片段
            # 直接命中桶、缩出候选，不再遍历全部关键词。
            # 关键词字段存的是 JSON 数组字符串，逐条解析；解析失败跳过该节点。
            try:
                kws = json.loads(r["keywords"] or "[]")
            except Exception:
                kws = []
            kws = [str(k) for k in kws if k]
            node_kw[r["id"]] = kws
            for k in kws:
                for g in _grams(k):
                    gram_index.setdefault(g, set()).add(r["id"])
        _CACHE["nodes"] = nodes
        _CACHE["gram_index"] = gram_index
        _CACHE["node_kw"] = node_kw
        _CACHE["loaded"] = True
    return {"rules": len(_CACHE["rules"]), "nodes": len(_CACHE["nodes"]),
            "keywords": len(_CACHE["gram_index"])}


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
    """基于内存倒排桶做关键词预筛：返回按命中关键词数降序的 node_id 列表。

    这是「接口读取优先走内存」的落点：用查询词的字片段直接命中倒排桶，
    只对缩出的少量候选做包含式精判，不再遍历全部关键词。
    未加载或索引为空时返回 None，调用方据此回退到数据库查询。
    @param keywords 关键词列表
    @param limit 返回上限；None 表示不限
    @return [(node_id, hit_count)] 或 None（缓存不可用时）
    """
    if not _CACHE.get("loaded"):
        return None
    gram_index = _CACHE.get("gram_index") or {}
    node_kw = _CACHE.get("node_kw") or {}
    if not gram_index:
        return None
    kws = [str(k) for k in (keywords or []) if k]
    if not kws:
        return None
    # 第一步：用查询词的全部片段去桶里取候选并集，快速缩小范围。
    # 只对「与查询词共享片段」的节点做后续精判，避免全量遍历。
    candidates = set()
    for kw in kws:
        for g in _grams(kw):
            ids = gram_index.get(g)
            if ids:
                candidates |= ids
    if not candidates:
        return []
    # 第二步：只对候选做包含式精判，累计命中关键词数。
    scores = {}
    for nid in candidates:
        nkset = node_kw.get(nid) or []
        for kw in kws:
            for nk in nkset:
                if kw in nk or nk in kw:
                    scores[nid] = scores.get(nid, 0) + 1
                    break
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ordered[:limit] if limit else ordered


def index_node(node_id, source, essence, keywords, tier, strength):
    """增量把单个节点补进内存索引（蒸馏出新节点后调用）。

    相比 invalidate() 的全量失效重载，增量更新只动这一条，
    避免写入频繁时反复触发整库重载。缓存未加载时什么都不做
    （下次读取会全量加载，自然包含该节点）。
    @param keywords 关键词列表（非 JSON 字符串）
    """
    if not _CACHE.get("loaded"):
        return
    with _LOCK:
        _CACHE["nodes"][node_id] = {
            "id": node_id, "source": source, "essence": essence,
            "keywords": json.dumps(keywords or [], ensure_ascii=False),
            "tier": tier, "strength": strength,
        }
        kws = [str(k) for k in (keywords or []) if k]
        _CACHE["node_kw"][node_id] = kws
        for k in kws:
            for g in _grams(k):
                _CACHE["gram_index"].setdefault(g, set()).add(node_id)


def is_loaded():
    """是否已完成启动加载。"""
    return bool(_CACHE.get("loaded"))


def invalidate():
    """使缓存失效（写入记忆后调用，下次读取重载）。"""
    with _LOCK:
        _CACHE["loaded"] = False
