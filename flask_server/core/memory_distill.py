"""AI 工具调用镜像插件 —— 记忆系统：蒸馏管道

职责：从记忆节点提取「精华 + 关键词」，写入节点的蒸馏层字段。
不覆盖原始 blocks，蒸馏可随时重跑。

并发模型（关键，务必遵守）：
- 单工作线程串行：所有蒸馏请求进入同一队列，由一个后台线程顺序处理。
  同一时刻只有一个蒸馏写者，从根上杜绝多线程并发写库相互争锁、
  把写锁长期占住导致接口请求死等。
- 短事务：逐节点提交，处理完一个节点即提交，持锁时间短，不长时间阻塞请求线程。

触发：消息入树上报后，由路由层投递到本队列。

提取规则（按来源）：
  - user：原句全文 → 保留原句（不摘要），关键词从原句提；
  - assistant：剔除寒暄与过程描述，留结论/进度；
  - tool：工具名 + 结果摘要。

依赖：memory_nodes、memory_keywords、memory_events、memory_db、threading、collections
"""
import collections
import json
import threading

import memory_nodes
import memory_keywords as kw
import memory_events
from memory_db import begin_batch, end_batch

# ---------- 串行蒸馏队列 ----------
# 待蒸馏节点（FIFO），元素为 (node_id, use_llm)；_pending_set 用于去重。
_pending = collections.deque()
_pending_set = set()
_queue_lock = threading.Lock()
_worker_running = False   # 工作线程是否在跑（避免重复启动多个工作线程）


def _tool_essence(text):
    """工具结果精华：优先解析 JSON 取「工具名 + 结果摘要」，失败退回文本截断。

    工具节点的 blocks 多为 bridge-chat-res 的 JSON 原文，直接截断会得到
    腰斩的 JSON 片段（无检索价值）。解析出 tool 与 result 才能得到
    「工具名 + 结果摘要」这一设计文档要求的形态。
    @param text blocks 抽出的纯文本
    @return 精华字符串（最长 200 字符）
    """
    raw = (text or "").strip()
    try:
        obj = json.loads(raw)
    except Exception:
        return raw.replace("\n", " ")[:200]
    if not isinstance(obj, dict):
        return raw.replace("\n", " ")[:200]
    tool = obj.get("tool") or ""
    result = obj.get("result")
    # 告警类结果（形如 {"issue":"...","message":"..."}）：直接用 message 当摘要。
    # 否则整段 JSON 会作为精华，机器味重且难检索。
    if isinstance(result, dict) and result.get("issue"):
        msg = str(result.get("message") or result.get("issue") or "").strip()
        head = ("%s：%s" % (tool, msg)).strip("：") if tool else msg
        return head.replace("\n", " ")[:200] or raw.replace("\n", " ")[:200]
    brief = json.dumps(result, ensure_ascii=False) if result is not None else ""
    head = ("%s：%s" % (tool, brief)).strip("：") if tool else brief
    return head.replace("\n", " ")[:200] or raw.replace("\n", " ")[:200]


def _essence_for(source, text, blocks):
    """按来源生成精华文本。

    @param source user / assistant / tool
    @param text blocks 抽出的纯文本
    @param blocks 原始内容块
    @return 精华字符串
    """
    if source == "user":
        # 用户发言：原句即精华，不摘要（保留原句是防语义漂移的底线）
        return text.strip()
    if source == "tool":
        # 工具结果：优先解析出「工具名 + 结果摘要」，解析失败再退回文本截断
        return _tool_essence(text)
    # assistant：剔除寒暄开头，取正文
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        greetings = ("好的", "没问题", "当然", "让我", "我来", "首先", "接下来")
        while lines and lines[0].startswith(greetings):
            lines.pop(0)
    body = "\n".join(lines)
    return body.strip()[:500] if body else text.strip()[:500]


def distill_node(node_id, use_llm=False):
    """同步蒸馏单个节点：提取精华与关键词，写入库。

    用单节点短事务包住本节点全部写操作，处理完立即提交；
    绝不跨节点持有写锁，避免长时间阻塞请求线程。
    @return dict { essence, keywords } 或 None（节点不存在）
    """
    node = memory_nodes.get_node(node_id)
    if not node:
        return None
    source = node.get("source") or "assistant"
    text = kw.extract_from_blocks(node.get("blocks"))
    essence = _essence_for(source, text, node.get("blocks"))
    keywords = kw.extract(text, top_k=8, use_llm=use_llm)
    # 跨计划去噪：剔除近期计划里高频出现的低区分度词
    keywords = kw.denoise_by_plans(keywords)
    # 生成文本向量，供检索第三路（向量语义近邻）使用
    vector = kw.text_to_vector(essence or text)
    conn = memory_nodes.get_conn()
    # 单节点短事务：只包住本节点的写入，处理完立即提交、释放写锁
    begin_batch()
    try:
        memory_nodes.set_essence(node_id, essence, keywords, vector)
        # 接入事件层：蒸馏完成即自动建突触、给用户发言挂影子
        try:
            memory_events.build_synapses(node_id)
            if source == "user":
                memory_events.set_shadow(node_id, essence)
        except Exception as e:
            # 事件层失败不影响蒸馏本身（蒸馏结果已落库）
            print("[memory] 事件层触发失败 node=%s: %s" % (node_id, e))
    finally:
        end_batch(conn)
    return {"essence": essence, "keywords": keywords}


def distill_async(node_ids, use_llm=False):
    """把一批节点投递到串行蒸馏队列（不阻塞调用方）。

    不再为每批新起线程，而是统一入队、由唯一工作线程顺序处理，
    避免多线程并发写库互抢写锁。
    @param node_ids 节点 id 列表
    @return 本次真正新增入队的节点数（已在队列中的不重复计）
    """
    added = 0
    with _queue_lock:
        for nid in node_ids:
            if nid not in _pending_set:
                _pending.append((nid, use_llm))
                _pending_set.add(nid)
                added += 1
    _ensure_worker()
    return added


def _ensure_worker():
    """确保串行工作线程在跑（幂等：重复调用只启动一个）。"""
    global _worker_running
    with _queue_lock:
        if _worker_running:
            return
        _worker_running = True
    threading.Thread(target=_worker, daemon=True).start()


def _worker():
    """串行工作线程：逐个节点蒸馏，处理完一个再取下一个。

    队列空时退出并复位标志，下次入队会再次拉起，不空转占资源。
    """
    global _worker_running
    while True:
        with _queue_lock:
            if not _pending:
                _worker_running = False
                return
            nid, use_llm = _pending.popleft()
            _pending_set.discard(nid)
        try:
            distill_node(nid, use_llm=use_llm)
        except Exception as e:
            # 单节点失败不中断整批
            print("[memory] 蒸馏失败 node=%s: %s" % (nid, e))
