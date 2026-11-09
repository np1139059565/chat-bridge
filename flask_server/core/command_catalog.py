"""
指令清单汇总 —— 把三个来源的指令定义合并为统一视图

职责：
1. 从内置指令表、外部 skill 声明、客户端注册信息三处读取指令定义；
2. 统一字段为 name / source / desc，客户端项额外带 site_key；
3. 生成按来源分组的帮助文本。

设计边界：
- 只读汇总，不改执行通道，指令回执不进入 AI 对话流；
- 单一来源读取失败时按空来源处理，不让一条坏数据拖垮整张清单；
- 取数口全部延迟导入，避免模块加载期形成循环依赖；
- C-1 注册表只读取、不修改：枚举复用其整表读取原语，不改动该文件。
"""
# 来源枚举：清单与帮助文本共用的固定取值。
BUILTIN = "builtin"
CUSTOM = "custom"
CLIENT = "client"
# 分组顺序：内置 → 自定义 → 客户端，与既有帮助文本的顺序一致。
SOURCE_ORDER = (BUILTIN, CUSTOM, CLIENT)
# 分组标题：帮助文本按此渲染二级标题。
SOURCE_TITLES = {
    BUILTIN: "内置指令",
    CUSTOM: "自定义指令",
    CLIENT: "客户端指令",
}


def _builtin_items():
    """读取内置指令表 BUILTIN，转为统一字段的清单项。"""
    # 延迟导入：避免模块加载期触发桥接包初始化。
    from remote_bridge import command_registry as cr
    out = []
    # 表为空是合法状态，循环自然不执行，返回空列表即可。
    for name, meta in (cr.BUILTIN or {}).items():
        # 表项固定为字典；结构异常时按空元信息处理，字段仍齐全。
        info = meta if isinstance(meta, dict) else {}
        out.append({"name": name, "source": BUILTIN,
                    "desc": info.get("desc") or ""})
    return out


def _custom_items():
    """读取已上线 skill 声明的指令，转为统一字段的清单项。"""
    # 复用既有扫描实现，不另写一套 tool.json 解析逻辑。
    import custom_tools.commands as ext_cmds
    out = []
    for c in ext_cmds.list_external_commands() or []:
        # 单条声明结构异常时跳过，不影响其余条目。
        if not isinstance(c, dict):
            continue
        out.append({"name": c.get("name") or "", "source": CUSTOM,
                    "desc": c.get("desc") or ""})
    return out


def _all_clients():
    """只读枚举全部注册条目，返回 {site_key: entry}。

    C-1 未提供公开枚举函数，且本任务不改动该文件；
    此处只读复用其整表读取原语，拿到与 lookup 同一份落盘数据。
    """
    import client_registry as registry
    return registry._read_store() or {}


def _client_items():
    """读取各客户端声明的指令，按 site_key 归属标注。"""
    out = []
    # 逐个客户端展开：同名指令各自成条，不去重。
    for site_key, entry in _all_clients().items():
        # 注册条目结构异常时跳过该客户端，保留其余来源。
        cmds = (entry.get("commands") or []) if isinstance(entry, dict) else []
        for c in cmds:
            # 声明项非字典时跳过，避免字段访问抛异常。
            if not isinstance(c, dict):
                continue
            out.append({
                "name": c.get("name") or "",
                "source": CLIENT,
                "desc": c.get("desc") or "",
                "site_key": site_key,
            })
    return out


def _safe_collect(fn):
    """调用单个来源的取数函数；异常时按空来源处理。"""
    try:
        return fn()
    except Exception as e:
        # 记录原因便于排查，但本来源缺席不应让整个查询失败。
        import app_log
        app_log.warn("[command_catalog]", "读取指令来源失败：%s" % e)
        return []


def list_commands():
    """合并三个来源，返回统一字段的指令清单。"""
    items = []
    # 按固定来源顺序拼接，保证输出稳定可预期。
    for fn in (_builtin_items, _custom_items, _client_items):
        # 每个来源独立兜底，互不牵连。
        items += _safe_collect(fn)
    return items


def _render_group(source, entries):
    """渲染单个来源的帮助文本段落；该来源无条目时返回空列表。"""
    # 先筛出属于当前来源的条目，保持清单中的原有顺序。
    group = [e for e in entries if e.get("source") == source]
    # 空来源不产生空标题，避免帮助文本里出现没有内容的分段。
    if not group:
        return []
    lines = ["", "**%s**" % SOURCE_TITLES[source]]
    for e in group:
        # 客户端项追加归属标注，同名指令靠 site_key 区分。
        tail = ""
        if source == CLIENT and e.get("site_key"):
            tail = "（客户端：%s）" % e["site_key"]
        # 对齐既有 /help 的「- `指令` 说明」格式。
        lines.append("- `%s` %s%s" % (e.get("name", ""), e.get("desc", ""), tail))
    return lines


def help_text(entries=None):
    """按来源分组生成帮助文本；未传清单时现场读取全部来源。"""
    # 允许调用方传入同一份清单，保证帮助文本与清单内容一致。
    items = list_commands() if entries is None else entries
    lines = ["可用指令："]
    for source in SOURCE_ORDER:
        # 逐来源渲染，段落之间自带空行。
        lines += _render_group(source, items)
    return "\n".join(lines)
