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
import serial_worker
from memory_db import begin_batch, end_batch

# ---------- 串行蒸馏队列 ----------
# 待蒸馏节点（FIFO），元素为 (node_id, use_llm)；同一 node 去重（保留首次）。
# 并发骨架统一走共享模块 serial_worker。


def _handle_distill(item):
    """处理一个待蒸馏节点：调用 distill_node；单节点失败只记日志，不中断队列。

    @param item 二元组 (node_id, use_llm)
    """
    nid, use_llm = item                          # 拆出节点 id 与是否用 LLM
    try:
        distill_node(nid, use_llm=use_llm)       # 执行蒸馏
    except Exception as e:                       # 单节点失败不中断整批
        print("[memory] 蒸馏失败 node=%s: %s" % (nid, e))


# 蒸馏队列：keep_first=True 对应「同一节点只保留首次入队」的去重语义
_distill_worker = serial_worker.SerialWorker(
    _handle_distill, keep_first=True, thread_name="mem-distill")


# 各工具结果的专属摘要器注册表：工具名 -> 函数(result, limit) -> str。
# 未登记的工具回退到通用摘要 _generic_brief，绝不整体 json.dumps。
_BRIEFERS = {}


def _register_brief(name):
    """装饰器：把函数登记为某工具的 result 摘要器。

    @param name 工具名（对应 bridge-chat-res 里的 tool 字段）
    """
    def deco(fn):
        _BRIEFERS[name] = fn
        return fn
    return deco


def _generic_brief(result, limit):
    """通用结果摘要：优先取标量字段与数组计数，再取首个字符串叶子。

    绝不把整个 result 序列化成 JSON——那会产出腰斩的机器串，无检索价值。
    @param result 工具结果的 result 字段（任意 JSON 类型）
    @param limit 返回字符串长度上限
    @return 一句人话摘要
    """
    if result is None:
        return ""
    if isinstance(result, str):
        return result.replace("\n", " ").strip()[:limit]
    if isinstance(result, (int, float, bool)):
        return str(result)
    if isinstance(result, list):
        return _brief_list(result, limit)
    if isinstance(result, dict):
        return _brief_dict(result, limit)
    return str(result).replace("\n", " ")[:limit]


def _brief_list(result, limit):
    """列表摘要：报条数，并附首项摘要（首项更有代表性）。"""
    if not result:
        return "空列表"
    head = _generic_brief(result[0], limit // 2)
    return ("共 %d 项，首项：%s" % (len(result), head)) if head else "共 %d 项" % len(result)


def _brief_dict(result, limit):
    """字典摘要：关键标量字段 + 首个字符串正文 + 首个数组长度，均按需截断。"""
    parts = []
    # 1) 关键标量字段优先（ok / count / total_lines / exitCode 等），一眼可判成败与规模
    for k in ("ok", "success", "count", "total", "total_lines", "exitCode"):
        if k in result and isinstance(result[k], (int, float, bool)):
            parts.append("%s=%s" % (k, result[k]))
    # 2) 取第一个非空字符串字段作为语义正文
    for v in result.values():
        if isinstance(v, str) and v.strip():
            parts.append(v.replace("\n", " ").strip()[: limit // 2])
            break
    # 3) 数组字段只报长度，不展开（展开会撑爆精华）
    for k, v in result.items():
        if isinstance(v, list):
            parts.append("%s %d 项" % (k, len(v)))
            break
    return "，".join(parts)[:limit] if parts else ""


@_register_brief("read_file")
def _brief_read_file(r, limit):
    """read_file 摘要：报路径、总行数与正文开头。"""
    seg = "读文件"
    if r.get("path"):
        seg += " " + str(r["path"])
    if r.get("total_lines") is not None:
        seg += "（共 %s 行）" % r["total_lines"]
    head = (r.get("content") or "").replace("\n", " ").strip()[: limit // 2]
    return (seg + "：" + head) if head else seg


@_register_brief("search_content")
def _brief_search_content(r, limit):
    """search_content 摘要：报命中数与首条文件位置。"""
    seg = "内容搜索"
    if r.get("count") is not None:
        seg += "命中 %s 处" % r["count"]
    matches = r.get("matches") or []
    if matches:
        first = matches[0]
        seg += "，首条 %s" % (first.get("file") or "?")
        if first.get("line") is not None:
            seg += ":%s" % first["line"]
    return seg


@_register_brief("search_file")
def _brief_search_file(r, limit):
    """search_file 摘要：报命中文件数与首个文件名。"""
    files = r.get("files") or r.get("matches") or []
    seg = "文件搜索命中 %s 个" % (r.get("count", len(files)))
    if files:
        first = files[0]
        name = first.get("file") if isinstance(first, dict) else first
        if name:
            seg += "，首条 %s" % name
    return seg


@_register_brief("list_dir")
def _brief_list_dir(r, limit):
    """list_dir 摘要：报目录与条目数。"""
    return "列目录 %s：%d 项" % (r.get("directory") or "?", len(r.get("items") or []))


@_register_brief("run_command")
def _brief_run_command(r, limit):
    """run_command 摘要：报退出码与标准输出/错误的开头。"""
    seg = "执行命令"
    if r.get("exitCode") is not None:
        seg += "（退出码 %s）" % r["exitCode"]
    out = (r.get("stdout") or "").replace("\n", " ").strip()[: limit // 2]
    err = (r.get("stderr") or "").replace("\n", " ").strip()[: limit // 3]
    if out:
        seg += "：" + out
    elif err:
        seg += "：错误 " + err
    return seg


@_register_brief("memory_search")
def _brief_memory_search(r, limit):
    """memory_search 摘要：报命中记忆条数。"""
    return "检索记忆：命中 %s 条" % r.get("count", len(r.get("hits") or []))


def _brief_for(tool, result, limit):
    """按工具名分派 result 摘要器；未登记的工具走通用摘要。

    @param tool 工具名
    @param result 工具结果的 result 字段
    @param limit 摘要长度上限
    @return 摘要字符串
    """
    fn = _BRIEFERS.get(tool)
    if fn is not None:
        try:
            text = fn(result, limit)
            if text:
                return text
        except Exception:
            # 专属摘要器异常时降级到通用摘要，不让蒸馏中断
            pass
    return _generic_brief(result, limit)


def _tool_essence(text):
    """工具结果精华：解析 JSON 取「工具名 + 结果摘要」，失败退回文本截断。

    工具节点的 blocks 多为 bridge-chat-res 的 JSON 原文，直接截断会得到
    腰斩的 JSON 片段（无检索价值）。解析出 tool 与 result，再按工具名
    分派专属摘要器，才能得到设计文档要求的「工具名 + 结果摘要」形态。
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
    if isinstance(result, dict) and result.get("issue"):
        return _tool_issue_essence(tool, result, raw)
    # 普通工具结果：按工具名分派摘要器，绝不整体 json.dumps（那会产出腰斩 JSON）。
    brief = _brief_for(tool, result, 200) if result is not None else ""
    return _join_tool_brief(tool, brief, raw)


def _tool_issue_essence(tool, result, raw):
    """告警类工具结果的精华：直接取 message 或 issue。

    @param tool   工具名
    @param result 结果字典（含 issue 字段）
    @param raw    原始文本（兜底用）
    @returns 精华字符串
    """
    msg = str(result.get("message") or result.get("issue") or "").strip()
    head = ("%s：%s" % (tool, msg)).strip("：") if tool else msg
    return head.replace("\n", " ")[:200] or raw.replace("\n", " ")[:200]


def _join_tool_brief(tool, brief, raw):
    """把「工具名 + 结果摘要」拼成精华；为空则退回原文截断。

    @param tool  工具名
    @param brief 结果摘要
    @param raw   原始文本（兜底用）
    @returns 精华字符串
    """
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
    # 工具节点从「精华」提关键词，而非原始 JSON 全文。
    # 原始 blocks 是 bridge-chat-res 的 JSON，全文提词会把 bridge/chat/type/true、
    # 路径片段、nonce 等噪声当作关键词；精华已是「工具名 + 结果摘要」，提词更干净。
    kw_source = essence if (source == "tool" and essence) else text
    keywords = kw.extract(kw_source, top_k=8, use_llm=use_llm)
    # 跨计划去噪：剔除近期计划里高频出现的低区分度词
    keywords = kw.denoise_by_plans(keywords)
    # 生成文本向量，供检索第三路（向量语义近邻）使用
    vector = kw.text_to_vector(essence or text)
    conn = memory_nodes.get_conn()
    # 第一步·短事务：只写本节点的精华/关键词/向量，写完立即提交、释放写锁。
    # 建突触等重活必须留到事务外：否则会在持写锁的同时做全表扫描 + 两两匹配，
    # 既占写锁又占解释器锁，把其它请求一并拖住（见 build_synapses 说明）。
    begin_batch()
    try:
        memory_nodes.set_essence(node_id, essence, keywords, vector)
    finally:
        end_batch(conn)
    # 第二步·事务外：接入事件层（建突触、给用户发言挂影子）。
    # 这些是只读扫描 + 内存计算 + 逐条短事务写边，不再长时间持有写锁。
    try:
        memory_events.build_synapses(node_id)
        if source == "user":
            memory_events.set_shadow(node_id, essence)
    except Exception as e:
        # 事件层失败不影响蒸馏本身（蒸馏结果已落库）
        print("[memory] 事件层触发失败 node=%s: %s" % (node_id, e))
    return {"essence": essence, "keywords": keywords}


def distill_async(node_ids, use_llm=False):
    """把一批节点投递到串行蒸馏队列（不阻塞调用方）。

    不再为每批新起线程，而是统一入队、由唯一工作线程顺序处理，
    避免多线程并发写库互抢写锁。
    @param node_ids 节点 id 列表
    @return 本次真正新增入队的节点数（已在队列中的不重复计）
    """
    added = 0
    for nid in node_ids:
        if _distill_worker.submit(nid, (nid, use_llm)):
            added += 1                          # 仅统计真正新增入队的节点
    return added
