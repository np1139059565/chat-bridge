"""AI 工具调用镜像插件 —— 记忆系统：蒸馏管道

职责：异步从记忆节点提取「精华 + 关键词」，写入节点的蒸馏层字段。
不覆盖原始 blocks，蒸馏可随时重跑。

触发：消息入树上报后，由路由层丢到后台线程调用 distill_async。

提取规则（按来源）：
  - user：原句全文 → 保留原句（不摘要），关键词从原句提；
  - assistant：剔除寒暄与过程描述，留结论/进度；
  - tool：工具名 + 结果摘要。

依赖：memory_nodes、memory_keywords、threading
"""
import threading

import memory_nodes
import memory_keywords as kw


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
        # 工具结果：取工具名 + 前若干字符摘要
        head = text.strip().replace("\n", " ")
        return head[:200]
    # assistant：剔除寒暄开头，取正文
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        # 去掉常见寒暄/过渡句开头
        greetings = ("好的", "没问题", "当然", "让我", "我来", "首先", "接下来")
        while lines and lines[0].startswith(greetings):
            lines.pop(0)
    body = "\n".join(lines)
    return body.strip()[:500] if body else text.strip()[:500]


def distill_node(node_id, use_llm=False):
    """同步蒸馏单个节点：提取精华与关键词，写入库。

    @return dict { essence, keywords } 或 None（节点不存在）
    """
    node = memory_nodes.get_node(node_id)
    if not node:
        return None
    source = node.get("source") or "assistant"
    text = kw.extract_from_blocks(node.get("blocks"))
    essence = _essence_for(source, text, node.get("blocks"))
    keywords = kw.extract(text, top_k=8, use_llm=use_llm)
    memory_nodes.set_essence(node_id, essence, keywords)
    return {"essence": essence, "keywords": keywords}


def distill_async(node_ids, use_llm=False):
    """异步蒸馏一批节点：丢后台线程，不阻塞调用方。

    @param node_ids 节点 id 列表
    @return 线程对象
    """
    def _run():
        for nid in node_ids:
            try:
                distill_node(nid, use_llm=use_llm)
            except Exception as e:
                # 单节点失败不中断整批
                print("[memory] 蒸馏失败 node=%s: %s" % (nid, e))
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
