"""AI 工具调用镜像插件 —— 工具清单工具

职责：让 AI 能主动询问「现在有哪些工具可以调用」。

为什么需要：System Prompt 只含身份、规则、技能与「调用前先查参数」通则，
不含工具清单；而 get_tool_params 只能按名查询，名字从哪来无处可问。
没有本工具时，AI 只能靠「故意传错 id 触发 available 列表」这种旁门，
既不可靠也不该作为正规途径。

口径：与 HTTP 的 /tools 目录一致 —— 内置（仅已上线）+ 自定义（skill 提供，
仅已上线）+ 外部提供方工具，按名称去重。只返回名称、说明与有无参数，
具体 schema 由 get_tool_params 按需查询，避免一次返回全部参数撑爆上下文。

对外接口：
- t_list_tools(p)  清单入口
"""


def _has_params(entry):
    """判断工具是否带参数：schema 看 properties 非空，历史数组看非空。

    为什么不直接 bool(parameters)：迁移到 JSON Schema 后，无参工具的
    parameters 是空 properties 的 object schema，schema 本身非空会把
    无参工具误报成有参（Q-7），诱导 AI 多做一次 get_tool_params 查询；
    历史数组格式没有 properties 可看，维持「非空即有参」。

    @param entry 工具声明字典（内置/自定义/外部提供方同构）
    @returns True 表示带参数，值得再查一次 get_tool_params
    """
    params = entry.get("parameters")
    if isinstance(params, dict):
        return bool(params.get("properties"))
    return bool(params)


def t_list_tools(p):
    """列出当前可调用的全部工具。

    只给名称与说明，具体参数由 get_tool_params 查询：
    一次返回全部 schema 会占掉大量上下文，而多数调用只需其中一两个。

    @param p 参数字典（本工具无参数，保留形参以统一派发签名）
    @returns { count, tools: [ { name, description, has_params } ] }
    """
    # 延迟导入：runtime 在模块级反向依赖工具实现，顶层导入会形成循环
    import runtime
    import custom_tools as ct
    import external_tools
    # 内置工具声明在 tool_meta，此处只读不改
    from tool_meta import TOOLS

    out = []
    # 内置工具：逐个判断上线状态，下线的不进目录（AI 调用它必失败）
    for name, entry in TOOLS.items():
        if not runtime.is_tool_enabled(name):
            continue
        out.append({
            "name": name,
            "description": entry.get("description", ""),
            # 有无参数，便于 AI 判断值不值得再查一次 get_tool_params
            "has_params": _has_params(entry),
        })

    # 自定义工具：all_meta 已按 enabled 与 kind=tool 过滤，指令执行端不会混入
    custom = ct.all_meta()
    for t in custom:
        out.append({
            "name": t.get("name"),
            "description": t.get("description", ""),
            "has_params": _has_params(t),
        })

    # 外部提供方工具：与 /tools 一致，已由自定义视图列出的不重复计入
    runtime.refresh_external_providers()
    seen = {t.get("name") for t in custom}
    for t in external_tools.hub.provider_tools():
        if t.get("name") in seen:
            continue
        out.append({
            "name": t.get("name"),
            "description": t.get("description", ""),
            "has_params": _has_params(t),
        })

    # 按名称排序，结果稳定，便于阅读与比对
    out.sort(key=lambda x: x.get("name") or "")
    return {"count": len(out), "tools": out}
