"""远程桥接 —— 指令分组与展示层

本模块只承载「指令怎么展示给用户」：把指令表整理成分组、快捷键列表、
面板注册条目。指令表本身与解析校验在 command_registry.py。

从 command_registry.py 抽出，使该文件保持在行数上限内。
两模块单向依赖：command_registry 末尾重新导出本模块的公开函数，
调用方仍按 command_registry.xxx 访问，无需改动。
"""
import json

from . import bridge_store, bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][command]", *args)


def _dedup_sort(items):
    """去重并按首字母排序（忽略开头的 /，不区分大小写）。

    @param items 快捷键字符串列表
    @returns 去重排序后的列表
    """
    seen = set()
    uniq = []
    for s in items:
        # 空串跳过，已出现过的跳过
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    # 排序键去掉开头的斜杠并转小写，让 /sd 与 /clear 按字母序混排
    return sorted(uniq, key=lambda s: s.lstrip("/").lower())


def builtin_groups():
    """返回内置指令的结构化分组，供前端渲染成可点击按钮。

    与 shortcut_groups 的区别：后者只给快捷键字符串（供网页指令面板）；
    本函数额外带描述与分组名，前端据此刻出「点一下就执行」的按钮，
    用户无需手打指令即可测试各条功能。
    @returns [{group, items: [{key, desc}]}]，按 BUILTIN 中首次出现的组序排列
    """
    # 延迟导入：本模块由 command_registry 末尾导入，此处再取 BUILTIN 可避免启动期循环
    from .command_registry import BUILTIN
    order = []          # 分组顺序：保持与 BUILTIN 定义一致
    buckets = {}
    for name, meta in BUILTIN.items():
        group = meta.get("group") or "其它"
        # 首次遇到的分组登记顺序
        if group not in buckets:
            buckets[group] = []
            order.append(group)
        # key 取快捷键（更短，便于点击）；无别名时用主命令名
        aliases = meta.get("aliases") or []
        key = aliases[0] if aliases else name
        buckets[group].append({
            "key": key,
            "name": name,
            "desc": meta.get("desc") or "",
        })
    # 按登记顺序输出，不产生空组
    return [{"group": g, "items": buckets[g]} for g in order]


def _external_commands():
    """取外部指令列表；读取失败按空处理。

    单独抽成函数是为了让测试能替换它，不必真的安装 skill。

    @returns 外部指令对象列表
    """
    try:
        import custom_tools.commands as ext_cmds
        return ext_cmds.list_external_commands()
    except Exception as e:
        log("读取外部指令失败：", e)
        return []


def _custom_commands():
    """取用户自定义指令列表；读取失败按空处理。

    @returns 自定义指令对象列表
    """
    try:
        return bridge_store.get_config().get("commands") or []
    except Exception as e:
        log("读取自定义指令失败：", e)
        return []


def help_groups():
    """返回全部指令的结构化分组，供设置页渲染成可点击按钮。

    内置指令在前，外部指令与自定义指令各单独成组，顺序与 /h 文本一致。
    某类指令为空时不产生空组——空组会在设置页留下一行没有按钮的标题。

    条目结构与内置指令保持一致 {key, name, desc}：
      key  —— 实际执行的指令名（有别名取别名，便于点击）
      name —— 主命令名
      desc —— 说明文本

    @returns [{group, items:[{key, name, desc}]}]
    """
    groups = builtin_groups()

    # 外部指令：来自各 skill 的 tool.json 声明，由外部扩展执行
    ext_items = []
    for c in _external_commands():
        name = c.get("name") or ""
        # 无名条目跳过
        if not name:
            continue
        alias = c.get("alias") or ""
        ext_items.append({
            "key": alias or name,
            "name": name,
            "desc": c.get("desc") or "",
        })
    # 非空才成组
    if ext_items:
        groups.append({"group": "外部指令", "items": ext_items})

    # 自定义指令：名称带 /，显示名是用户填的 label
    cus_items = []
    for c in _custom_commands():
        name = (c.get("name") or "").strip()
        # 无名条目跳过
        if not name:
            continue
        cus_items.append({
            "key": name,
            "name": name,
            "desc": c.get("label") or "",
        })
    # 非空才成组
    if cus_items:
        groups.append({"group": "自定义指令", "items": cus_items})

    return groups


def shortcut_groups():
    """返回分组的快捷键列表：内置区 / 自定义区，各按首字母排序。

    供网页版「指令展开面板」使用：面板分两个区域展示，便于寻找；
    每区只含快捷键本身，不含描述，各按首字母排序。
    - 内置区：内置指令 + 外部指令（skill 声明，非用户自定义，归入内置区）
    - 自定义区：用户在前端配置的自定义指令（含别名）
    @returns {"builtin": [...], "custom": [...]}
    """
    builtin = _builtin_shortcuts() + _external_shortcuts()
    custom = _custom_shortcuts()
    return {"builtin": _dedup_sort(builtin), "custom": _dedup_sort(custom)}


def _builtin_shortcuts():
    """内置指令的快捷键列表（有别名取首个别名，否则取命令名）。"""
    # 延迟导入，理由同 builtin_groups
    from .command_registry import BUILTIN
    out = []
    for name, info in BUILTIN.items():
        aliases = info.get("aliases") or []
        out.append(aliases[0] if aliases else name)
    return out


def _external_shortcuts():
    """外部指令（来自各 skill 的声明）的快捷键列表；非用户自定义，归入内置区。"""
    out = []
    try:
        import custom_tools.commands as ext_cmds
        for c in (ext_cmds.list_external_commands() or []):
            pick = c.get("alias") or c.get("name") or ""
            # 有可执行名才收录
            if pick:
                out.append(pick)
    except Exception as e:
        log("读取外部指令失败：", e)
    return out


def _custom_shortcuts():
    """用户配置的自定义指令的快捷键列表（含别名）。"""
    out = []
    for c in (bridge_store.get_config().get("commands") or []):
        aliases = c.get("aliases") or []
        pick = aliases[0] if aliases else (c.get("name") or "")
        # 有可执行名才收录
        if pick:
            out.append(pick)
    return out


def register_panel(qq_client):
    """把配置的指令注册到 QQ 指令面板 / 自定义菜单。

    目标接口：创建面板 POST /v2/panels（scope=c2c）、修改菜单 PUT /v2/menu。
    本函数在桥接启动时调用；失败仅记录，不影响消息收发。
    """
    # 延迟导入，理由同 builtin_groups
    from .command_registry import BUILTIN
    cfg = bridge_store.get_config()
    commands = []
    # 内置：只注册主命令，别名不重复占位
    for name, info in BUILTIN.items():
        commands.append({"name": name, "desc": info.get("desc", "")})
    # 自定义：组合与点击指令一并注册
    for c in (cfg.get("commands") or []):
        tag = "[组合] " if (c.get("steps") or []) else ""
        commands.append({"name": c.get("name", ""), "desc": tag + (c.get("label") or "")})
    # 无可注册内容直接返回
    if not commands:
        return
    # 注册接口：POST /v2/panels 创建面板、PUT /v2/menu 修改自定义菜单，
    # 需携带 access_token；当前仅打印待注册内容，接入时替换为真实 HTTP 调用
    log("待注册指令面板：", json.dumps(commands, ensure_ascii=False))
