"""AI 工具调用镜像插件 —— 记忆系统：规则程序化

职责（方案第九节）：把「可机械判定的规则」由程序强制，语义性规则仍交 AI 判断。
本模块只覆盖能机械判定的三类：

  1. 提交前必须回读文件 —— 检查工具调用序列里，写文件后是否有读回动作；
  2. 不得清空真实数据 —— 扫描破坏性操作是否指向真实路径（非临时/测试库）；
  3. 输出中出现禁用词 —— 对生成文本做禁用词扫描并告警。

设计原则：程序只做「检查 + 告警」，不替 AI 决策。所有检查函数返回结构化结论，
调用方（路由/前端）据此展示；误报由人复核，避免机械强制越界。

依赖：re（正则）
"""
import re


# ---------- 规则一：提交前必须回读 ----------

# 写操作工具名（会产生文件内容变更）
_WRITE_TOOLS = {"write_to_file", "replace_in_file", "delete_file"}
# 读操作工具名（能确认真值）
_READ_TOOLS = {"read_file", "search_content", "list_dir", "read_lints"}


def check_readback_after_write(tool_calls):
    """检查「写文件后必须回读」：每次写操作之后，是否出现至少一次读操作。

    @param tool_calls 有序工具调用列表，每项为 dict { tool, file }（file 可选）
    @return dict { ok, violations } —— violations 为未回读的写操作索引与工具名
    """
    violations = []
    pending = None      # 最近一次写操作，等待其后的回读
    for idx, call in enumerate(tool_calls or []):
        name = (call or {}).get("tool")
        if name in _WRITE_TOOLS:
            # 上一个写还没等到回读，又来了一个写：记为违规
            if pending is not None:
                violations.append(pending)
            pending = {"index": idx, "tool": name, "file": (call or {}).get("file", "")}
        elif name in _READ_TOOLS and pending is not None:
            # 出现读操作，视为对上一次写的回读，清空待查
            pending = None
    if pending is not None:
        violations.append(pending)
    return {"ok": not violations, "violations": violations}


# ---------- 规则二：不得清空真实数据 ----------

# 破坏性操作关键词
_DESTRUCTIVE = re.compile(
    r"(clear|delete|reset|remove|unlink|drop|truncate|rm\s|rmdir)", re.IGNORECASE
)
# 真实路径特征：data/ 真实库、memory/ 记忆目录、带盘符的绝对路径
_REAL_PATH_HINTS = re.compile(
    r"(memory[\\/]|data[\\/]|/var/|/home/|[A-Za-z]:[\\/])", re.IGNORECASE
)
# 白名单：临时/测试标记，出现这些则不算真实数据
_SAFE_MARKERS = re.compile(r"(temp|tmp|test|_test|临时|测试)", re.IGNORECASE)


def check_destructive_call(command, target=""):
    """扫描破坏性操作：是否指向真实数据（且非临时/测试目标）。

    @param command 待检查的命令或代码文本
    @param target 操作目标路径（可选）
    @return dict { risk, reason } —— risk 为 True 表示疑似触碰真实数据
    """
    blob = "%s %s" % (command or "", target or "")
    if not _DESTRUCTIVE.search(blob):
        return {"risk": False, "reason": "非破坏性操作"}
    if _SAFE_MARKERS.search(blob):
        return {"risk": False, "reason": "目标含临时/测试标记，判定安全"}
    if _REAL_PATH_HINTS.search(blob):
        return {"risk": True, "reason": "破坏性操作指向真实路径且无临时标记，需人工确认"}
    return {"risk": False, "reason": "破坏性操作但未命中真实路径特征"}


# ---------- 规则三：输出禁用词扫描 ----------

# 禁用词清单：取 ANTI-FLATTERY_PROTOCOL 的禁用语 + 元指令泄漏模式
_FORBIDDEN = [
    "你说得太对了", "你说得对", "这个问题提得非常好", "你的观察非常敏锐",
    "我完全同意", "好问题", "你问", "你说", "你要求", "你提到",
    "按照你的要求", "根据对话", "之前提到", "已移除", "已修改",
]


def check_forbidden_words(text):
    """扫描输出文本里的禁用词（奉承开场 / 元指令泄漏）。

    @param text 待检查文本
    @return dict { ok, hits } —— hits 为命中的禁用词列表（去重）
    """
    hits = []
    content = text or ""
    for w in _FORBIDDEN:
        if w in content and w not in hits:
            hits.append(w)
    return {"ok": not hits, "hits": hits}


def run_all(tool_calls=None, command=None, target="", text=None):
    """一次性跑全部检查，返回汇总结论。

    参数均可选，只检查传入了的部分。
    @return dict { readback, destructive, forbidden, all_ok }
    """
    result = {}
    if tool_calls is not None:
        result["readback"] = check_readback_after_write(tool_calls)
    if command is not None or target:
        result["destructive"] = check_destructive_call(command, target)
    if text is not None:
        result["forbidden"] = check_forbidden_words(text)
    result["all_ok"] = all(
        v.get("ok", True) if "ok" in v else not v.get("risk", False)
        for v in result.values() if isinstance(v, dict)
    )
    return result
