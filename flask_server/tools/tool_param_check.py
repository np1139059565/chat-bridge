"""AI 工具调用镜像插件 —— 参数声明读取辅助与参数名校验

职责：
1. 提供参数声明的双格式读取辅助（schema_param_names / schema_required_names）：
   标准格式（JSON Schema 对象）与历史数组格式都能取到参数名
2. 在工具真正执行之前，拦下「参数名未在声明里出现过」的调用

为什么需要这一层：工具实现按固定键名取值（如 p.get("glob")），
调用方把键名写成 include 时不会报错，该参数会被静默忽略、按默认值执行。
调用方以为过滤条件生效，实际拿到的是全量结果——这类静默失效比直接报错
更难发现，必须显式拦截并回传合法参数名。

从 routes/tools.py 拆出的原因：该文件需保持在仓库行数上限内，
而参数名校验与「路由分发」是两个独立关注点。

本模块不 import 任何工程内模块：它被 core / routes / custom_tools 各处引用
（tools/ 目录由 paths 引导加入 sys.path），零依赖可彻底避免导入顺序问题。
"""


# 工具实现接受、但不在声明里列出的参数名：视为合法，不作拦截。
# 这些是为兼容既有调用方保留的别名入口，不在 System Prompt 中暴露。
EXTRA_ALLOWED_PARAMS = {
    "get_tool_params": {"tool"},
}


def schema_param_names(parameters):
    """从参数声明取参数名列表（保持声明顺序），兼容标准 schema 与历史数组。

    标准格式 {"type": "object", "properties": {...}} 取 properties 的键；
    历史格式 [{"name": ...}, ...] 取各项的 name。
    其它形态（None / 空值 / 结构不符）一律返回空列表，不抛错。
    @param parameters 参数声明（schema 对象或历史数组）
    @returns 参数名列表
    """
    if isinstance(parameters, dict):
        props = parameters.get("properties")
        if isinstance(props, dict):
            return [k for k in props if k]
        return []
    return [p.get("name") for p in (parameters or [])
            if isinstance(p, dict) and p.get("name")]


def _array_required(parameters):
    """历史数组格式取必填参数名。"""
    return [p.get("name") for p in (parameters or [])
            if isinstance(p, dict) and p.get("required") and p.get("name")]


def schema_required_names(parameters):
    """取必填参数名，兼容标准 schema 与历史数组。"""
    if isinstance(parameters, dict):
        req = parameters.get("required")
        return [r for r in req if r] if isinstance(req, list) else []
    return _array_required(parameters)


def unknown_params(name, params, tools):
    """找出调用方传入、但该工具未声明的参数名。

    @param name   工具名
    @param params 调用方传入的参数（字典）
    @param tools  内置工具元数据表（runtime.TOOLS）
    @returns (未声明参数名列表, 该工具声明的参数名列表)
    """
    entry = tools.get(name) or {}
    # 声明的参数名：双格式读取，缺名/异常结构自然被过滤
    declared = schema_param_names(entry.get("parameters"))
    if not declared:
        # 无参数工具（如 list_rules）：不接受任何参数，避免误传被静默吞掉
        return (sorted(params.keys()) if params else []), declared
    allowed = set(declared) | EXTRA_ALLOWED_PARAMS.get(name, set())
    return [k for k in params if k not in allowed], declared
