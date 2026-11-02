"""AI 工具调用镜像插件 —— 工具参数名校验

职责：在工具真正执行之前，拦下「参数名未在声明里出现过」的调用。

为什么需要这一层：工具实现按固定键名取值（如 p.get("glob")），
调用方把键名写成 include 时不会报错，该参数会被静默忽略、按默认值执行。
调用方以为过滤条件生效，实际拿到的是全量结果——这类静默失效比直接报错
更难发现，必须显式拦截并回传合法参数名。

从 routes/tools.py 拆出的原因：该文件需保持在仓库行数上限内，
而参数名校验与「路由分发」是两个独立关注点。
"""


# 工具实现接受、但不在声明里列出的参数名：视为合法，不作拦截。
# 这些是为兼容既有调用方保留的别名入口，不在 System Prompt 中暴露。
EXTRA_ALLOWED_PARAMS = {
    "get_tool_params": {"tool"},
}


def unknown_params(name, params, tools):
    """找出调用方传入、但该工具未声明的参数名。

    @param name   工具名
    @param params 调用方传入的参数（字典）
    @param tools  内置工具元数据表（runtime.TOOLS）
    @returns (未声明参数名列表, 该工具声明的参数名列表)
    """
    entry = tools.get(name) or {}
    # 声明的参数名：元数据里缺 name 的条目跳过
    declared = [p.get("name") for p in (entry.get("parameters") or []) if p.get("name")]
    if not declared:
        # 无参数工具（如 list_rules）：不接受任何参数，避免误传被静默吞掉
        return (sorted(params.keys()) if params else []), declared
    allowed = set(declared) | EXTRA_ALLOWED_PARAMS.get(name, set())
    return [k for k in params if k not in allowed], declared
