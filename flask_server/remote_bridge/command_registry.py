"""远程桥接 —— 指令表、别名、校验与指令面板注册

本模块只承载「指令是什么」的静态知识，不涉及「指令怎么执行」：
- BUILTIN          内置指令表（完整命令名 → 说明 + 快捷键）
- resolve_cmd      别名 → 主命令名
- validate_command 自定义指令的合法性校验
- help_text        指令列表文本（/help 的回复内容）
- register_panel   把指令注册到 QQ 指令面板

指令的实际执行（下发抽屉命令、重启服务、组合指令）在 command_panel.py。
两模块单向依赖：command_panel 引用本模块，本模块不反向引用。

指令面板与自定义菜单的接口路径、请求体结构已对照 QQ 开放平台官方文档核对：
- 创建指令面板：POST /v2/panels，请求体含 scope（c2c/group）与 panel.items
- 修改指令面板：PUT /v2/panels/{panel_id}
- 自定义菜单：GET /v2/menu 查询、PUT /v2/menu 修改
面板元素 type 固定为 command，name 与 desc 需符合平台长度限制。
"""
import json

from . import bridge_store, bridge_log


def log(*args):
    """统一前缀日志：终端 + 按天落盘。"""
    bridge_log.write("[bridge][command]", *args)


# 内置指令表：完整命令名 → { desc 说明, aliases 快捷键列表 }
#
# 命名规则：主命令用完整英文名（如 /clear-sessions），快捷键作别名（如 /css）。
# 展示格式统一为「快捷键 — 描述（完整名）」，见 help_text。
BUILTIN = {
    # —— 抽屉外观 ——
    "/side": {"desc": "抽屉在左/右之间切换", "aliases": ["/sd"], "group": "抽屉外观"},
    "/settings": {"desc": "打开设置面板", "aliases": ["/st"], "group": "抽屉外观"},
    "/back": {"desc": "从设置返回对话镜像", "aliases": ["/bk"], "group": "抽屉外观"},
    # —— 会话管理 ——
    "/sessions": {"desc": "列出会话列表", "aliases": ["/ls"], "group": "会话管理"},
    "/switch-session": {"desc": "按序号切换会话（如 /ss 1）", "aliases": ["/ss"], "group": "会话管理"},
    "/clear-sessions": {"desc": "清空所有会话", "aliases": ["/css"], "group": "会话管理"},
    "/clear-messages": {"desc": "清空当前会话的消息列表", "aliases": ["/cms"], "group": "会话管理"},
    "/copy-json": {"desc": "复制当前会话 JSON", "aliases": ["/cj"], "group": "会话管理"},
    "/reparse": {"desc": "重新解析当前网页对话", "aliases": ["/rp"], "group": "会话管理"},
    # —— 卡片与结果 ——
    "/rerun": {"desc": "重新执行最新卡片并回传", "aliases": ["/rr"], "group": "卡片与结果"},
    "/copy": {"desc": "复制最新卡片结果并回传 AI", "aliases": ["/cp"], "group": "卡片与结果"},
    "/skip": {"desc": "跳过最新一张卡片", "aliases": ["/sk"], "group": "卡片与结果"},
    # —— 自动回传 ——
    "/switch-auto": {"desc": "自动回传开关（/sa on|off，不带则切换）", "aliases": ["/sa"], "group": "自动回传"},
    "/re-time": {"desc": "设置自动回传延迟（秒）", "aliases": ["/rt"], "group": "自动回传"},
    # —— 页面与服务 ——
    "/screenshot": {"desc": "截取浏览器屏幕", "aliases": ["/sp"], "group": "页面与服务"},
    "/refush": {"desc": "刷新浏览器并打开抽屉", "aliases": ["/rf"], "group": "页面与服务"},
    "/restart": {"desc": "重启服务端", "aliases": ["/rs"], "group": "页面与服务"},
    "/reconnect": {"desc": "重新连接后端", "aliases": ["/rc"], "group": "页面与服务"},
    # —— 内容采集 ——
    "/copy-system-prompt": {"desc": "复制 System Prompt 并发送给 AI", "aliases": ["/csp"], "group": "内容采集"},
    "/md": {"desc": "采集当前 AI 回复的 Markdown 原文", "aliases": ["/m"], "group": "内容采集"},
    # —— 语音 ——
    "/voice-ok": {"desc": "确认语音识别文字并转给 AI", "aliases": ["/vo"], "group": "语音"},
    # —— 工作记忆 ——
    "/memory": {"desc": "读取最新工作记忆文件并发送", "aliases": ["/mem"], "group": "工作记忆"},
    # —— 帮助 ——
    "/help": {"desc": "显示指令列表", "aliases": ["/h"], "group": "帮助"},
}

# 别名 → 主命令 的反查表：一次构建，之后直接查
_ALIAS_MAP = {}
for _main, _info in BUILTIN.items():
    for _a in _info.get("aliases") or []:
        _ALIAS_MAP[_a] = _main


def resolve_cmd(cmd):
    """把别名解析为主命令名；非别名原样返回。"""
    if cmd in BUILTIN:
        return cmd
    return _ALIAS_MAP.get(cmd, cmd)


def _custom_names(c):
    """取一条自定义指令的全部可用名（主名 + 别名），统一转小写并滤掉空值。

    用于重名比对与子指令存在性判定，两处口径必须一致，故集中在此。
    """
    names = [c.get("name") or ""] + (c.get("aliases") or [])
    return [str(n).lower() for n in names if n]


def _check_name_free(name, index, customs):
    """校验命令名未被占用：不与内置指令（含别名）或其它自定义指令冲突。

    @param index 修改时的下标（排除自身）；新增传 None
    @return 错误文本；合法返回空串
    """
    low = name.lower()
    # 与内置指令（含别名）冲突
    if resolve_cmd(low) in BUILTIN:
        return "命令名 %s 与内置指令冲突" % name
    # 与其它自定义指令（含别名）冲突
    for i, c in enumerate(customs):
        if i == index:
            continue
        if low in _custom_names(c):
            return "命令名 %s 已存在" % name
    return ""


def _available_subcommands(index, customs):
    """收集可用的子指令名集合：内置（含别名）+ 其它自定义指令（含别名）。"""
    available = set(BUILTIN.keys()) | set(_ALIAS_MAP.keys())
    for i, c in enumerate(customs):
        if i == index:
            continue
        available.update(_custom_names(c))
    return available


def _check_steps_exist(steps, index, customs):
    """校验组合指令的每条子指令都存在（内置或其它自定义指令）。

    @return 错误文本；全部存在返回空串
    """
    available = _available_subcommands(index, customs)
    for s in steps:
        sub = str(s).strip().split(None, 1)[0].lower()
        if not sub:
            continue
        if resolve_cmd(sub) not in BUILTIN and sub not in available:
            return "子指令 %s 不存在" % sub
    return ""


def validate_command(entry, index=None):
    """校验一条自定义指令能否保存。返回错误文本；合法返回空串。

    校验项：
      1. 命令名格式：以 / 开头
      2. 命令名重复：与内置指令、其它自定义指令（含别名）冲突
      3. 组合指令的子指令必须存在（内置或其它自定义指令）
    @param entry 待保存的指令对象
    @param index 修改时的下标（用于排除自身）；新增传 None
    """
    name = (entry.get("name") or "").strip()
    if not name.startswith("/"):
        return "命令名需以 / 开头"
    customs = bridge_store.get_config().get("commands") or []
    err = _check_name_free(name, index, customs)
    if err:
        return err
    steps = entry.get("steps") or []
    if steps:
        return _check_steps_exist(steps, index, customs)
    return ""


def _help_builtin_lines():
    """内置指令的展示行：按 group 分组，输出 Markdown。

    每组一个二级标题，组内每条一行：快捷键、描述、完整名。
    分组让相似指令靠在一起，Markdown 让 QQ 端渲染得友好。
    """
    lines = []
    groups = []
    for name, info in BUILTIN.items():
        g = info.get("group") or "其它"
        if g not in groups:
            groups.append(g)
    for g in groups:
        lines.append("")
        lines.append("**%s**" % g)
        for name, info in BUILTIN.items():
            if (info.get("group") or "其它") != g:
                continue
            al = info.get("aliases") or []
            short = al[0] if al else name
            if short != name:
                lines.append("- `%s` %s（%s）" % (short, info.get("desc", ""), name))
            else:
                lines.append("- `%s` %s" % (name, info.get("desc", "")))
    return lines


def _help_custom_lines(customs):
    """自定义指令的展示行：组合指令额外逐条展开子指令。

    展开子指令是为了让用户看清它到底按什么顺序做什么。
    """
    if not customs:
        return []
    lines = ["", "自定义指令："]
    for c in customs:
        tag = "[组合] " if c.get("steps") else ""
        lines.append("%s — %s%s" % (c.get("name", ""), tag, c.get("label", "")))
        for i, s in enumerate(c.get("steps") or []):
            lines.append("    %d. %s" % (i + 1, s))
    return lines


def _help_external_lines():
    """外部指令的展示行：来自各 skill 的 tool.json 声明（由外部扩展执行）。

    读取失败不应影响 /help 主体，故整体 try 兜底，失败时返回空。
    """
    try:
        import custom_tools.commands as ext_cmds
        cmds = ext_cmds.list_external_commands()
    except Exception as e:
        log("读取外部指令失败：", e)
        return []
    if not cmds:
        return []
    lines = ["", "**外部指令**"]
    for c in cmds:
        al = c.get("alias") or ""
        if al and al != c["name"]:
            lines.append("- `%s` %s（%s）" % (al, c.get("desc", ""), c["name"]))
        else:
            lines.append("- `%s` %s" % (c["name"], c.get("desc", "")))
    return lines


def help_text():
    """组装指令列表文本：先内置指令，再外部指令，最后自定义指令。"""
    lines = ["可用指令："] + _help_builtin_lines()
    lines += _help_external_lines()
    lines += _help_custom_lines(bridge_store.get_config().get("commands") or [])
    return "\n".join(lines)


def register_panel(qq_client):
    """把配置的指令注册到 QQ 指令面板 / 自定义菜单。

    目标接口：创建面板 POST /v2/panels（scope=c2c）、修改菜单 PUT /v2/menu。
    本函数在桥接启动时调用；失败仅记录，不影响消息收发。
    """
    cfg = bridge_store.get_config()
    commands = []
    # 内置：只注册主命令，别名不重复占位
    for name, info in BUILTIN.items():
        commands.append({"name": name, "desc": info.get("desc", "")})
    # 自定义：组合与点击指令一并注册
    for c in (cfg.get("commands") or []):
        tag = "[组合] " if (c.get("steps") or []) else ""
        commands.append({"name": c.get("name", ""), "desc": tag + (c.get("label") or "")})
    if not commands:
        return
    # 注册接口：POST /v2/panels 创建面板、PUT /v2/menu 修改自定义菜单，
    # 需携带 access_token；当前仅打印待注册内容，接入时替换为真实 HTTP 调用
    log("待注册指令面板：", json.dumps(commands, ensure_ascii=False))
