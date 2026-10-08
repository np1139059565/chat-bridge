"""AI 工具调用镜像插件 —— 外部调用信封解析（共享）

职责：集中处理「external-call 信封」的解析，供两处共用：
- remote_bridge.message_parse：判断消息是否来自 QQ / web 桥接；
- core.memory_distill：蒸馏用户消息时取出信封里真正的用户话。

为什么单独成模块：
  信封可能是嵌套两层——抽屉把卡片内容放进信封的 request 字段再发出，
  于是结构变成 {type, nonce, request: "{...request: 真实内容...}"}。
  此前这段「穿透嵌套」的逻辑只在 remote_bridge 里实现，
  蒸馏模块（core）要用就会形成反向依赖，故上移到 core 作为公共件。

依赖：json（仅此一项，保持 core 的独立性）
"""
import json


# 信封类型标记：外部调用卡片用它标识自己
def envelope_type():
    """返回外部调用信封的 type 标记值。

    以函数形式给出，便于调用方按需引用，避免散落魔法字符串。
    @returns 固定字符串 'external-call'
    """
    return "external-call"


def merge_nested_envelope(obj):
    """把嵌套信封的内层字段并入外层（穿透一层）。

    obj 的 request 字段若是字符串且本身又是一段 JSON，说明这是两层结构；
    内层补 source / openid 等字段，外层字段优先（update 顺序即优先级）。
    穿透失败时原样返回 obj。
    @param obj 外层信封字典
    @returns 合并后的字典（或原样返回）
    """
    if not isinstance(obj, dict):                  # 非字典无信封可言
        return obj
    req = obj.get("request")                       # 取出可能的嵌套内容
    if not (isinstance(req, str) and req.strip().startswith("{")):
        return obj                                 # 不是嵌套 JSON，原样返回
    try:
        inner = json.loads(req)                    # 尝试解析内层
    except Exception:
        return obj                                 # 解析失败，原样返回
    if not isinstance(inner, dict):                # 内层不是对象
        return obj
    merged = dict(inner)                           # 以内层为基础
    merged.update(obj)                             # 外层字段优先覆盖
    merged["request"] = inner.get("request", req)  # 保留内层的真实 request
    return merged


def unwrap_user_text(text):
    """从一段文本里取出信封承载的「真正的用户话」。

    用户消息经桥接投递时，会被包成 external-call 信封（可能是两层嵌套），
    蒸馏时若直接照抄原句，精华就成了一段结构化 JSON、无法检索。
    本函数逐层剥掉信封，返回最内层的人类可读文本；
    不是信封、或解析失败时，原样返回入参，绝不吞掉内容。

    处理链：文本 → JSON 对象 → 若 type 为 external-call 则取 request →
    若 request 仍是 JSON 字符串则继续剥 → 直到得到非 JSON 的文本。
    @param text 待解包的文本（可能是一段信封 JSON，也可能是普通话）
    @returns 解包后的用户话；无法解包时返回原文
    """
    if not text:                                   # 空输入直接返回
        return text or ""
    current = text.strip()                         # 当前待处理文本
    for _ in range(5):                             # 最多剥 5 层，防异常数据死循环
        if not current.startswith("{"):            # 已不是 JSON，停止
            return current
        try:
            obj = json.loads(current)              # 尝试解析为对象
        except Exception:
            return current                         # 解析失败：按普通文本返回
        if not isinstance(obj, dict):              # 非对象，停止
            return current
        # 非信封 JSON：若是工具结果等其它结构化数据，也取出可读字段兜底
        if obj.get("type") != envelope_type():
            inner_req = obj.get("request")
            if isinstance(inner_req, str) and inner_req.strip():
                current = inner_req.strip()        # 有 request 就继续往下剥
                continue
            return current                         # 无 request：保留原文本
        # 是信封：穿透嵌套，取真正的 request
        merged = merge_nested_envelope(obj)
        inner_req = merged.get("request")
        if not isinstance(inner_req, str) or not inner_req.strip():
            return current                         # 取不出 request：保留原文本
        current = inner_req.strip()                # 继续下一轮剥离
    return current                                 # 层数用尽，返回当前结果
