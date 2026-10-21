"""工具配置声明与读写

设计目标：配置跟着工具走，抽屉只做通用渲染。

本模块的做法：
    1. 每个工具在 CONFIG_SCHEMA 里声明自己有哪些可调项（键、标签、类型、默认值、取值范围）；
    2. 运行时值统一存 runtime.CONFIG["tool_config"][工具][键]，取不到时回退声明里的默认值；
    3. 抽屉经统一接口拿到「声明 + 当前值」，按类型通用渲染，不写任何工具专属代码。

新增可调项：只需在 CONFIG_SCHEMA 对应工具下加一行，抽屉自动出现该控件。
"""
import runtime


# 各工具的配置声明。每个配置项字段：
#   key      —— 存储键（存在 runtime.CONFIG["tool_config"][工具名][key]）
#   label    —— 设置页展示名
#   type     —— integer / boolean / string / multiselect
#   default  —— 默认值（未配置时使用）
#   hint     —— 补充说明（可选）
#   min/max  —— integer 的取值范围（可选，越界会被钳到边界）
#   options  —— multiselect 的可选项（必填）
#   restart  —— 改动后是否需要重启后端才生效（默认 False）
CONFIG_SCHEMA = {
    "read_file": [
        {
            "key": "max_batch_files",
            "label": "批量读取上限（个）",
            "type": "integer",
            "default": 20,
            "min": 1,
            "max": 200,
            "hint": "一次 file_paths 最多读多少个文件，超出会拒绝。",
        },
    ],
    "read_image": [
        {
            "key": "max_bytes",
            "label": "图片大小上限（字节）",
            "type": "integer",
            "default": 10 * 1024 * 1024,
            "min": 1024,
            "max": 200 * 1024 * 1024,
            "hint": "超过此体积的图片会被拒绝读取，请先压缩。",
        },
    ],
    "run_command": [
        {
            "key": "timeout",
            "label": "默认超时（秒）",
            "type": "integer",
            "default": 45,
            "min": 1,
            "max": 600,
            "hint": "单次命令超过该时长即返回超时结果。需小于外层兜底超时。",
        },
        {
            "key": "languages",
            "label": "允许的语言",
            "type": "multiselect",
            "default": ["cmd", "powershell", "shell", "git", "python"],
            "options": ["cmd", "powershell", "shell", "git", "python"],
            "hint": "勾选后 AI 才能使用对应语言执行命令。",
        },
    ],
    "search_content": [
        {
            "key": "max_results",
            "label": "最大返回条数",
            "type": "integer",
            "default": 200,
            "min": 1,
            "max": 2000,
            "hint": "结果过多时截断，避免一次返回撑爆上下文。",
        },
    ],
    "memory_search": [
        {
            "key": "default_top_k",
            "label": "默认返回条数",
            "type": "integer",
            "default": 10,
            "min": 1,
            "max": 100,
        },
    ],
    # 系统级资源上限：不属于某个工具，归入统一分组便于集中调整。
    # 均为「目录/队列保留多少个文件或条目」，超出按最旧优先回收。
    "system": [
        {
            "key": "max_screenshot_files",
            "label": "截图目录保留数",
            "type": "integer",
            "default": 200,
            "min": 10,
            "max": 5000,
            "hint": "工具截图与指令截图共用此目录，超出后按修改时间回收最旧的。",
        },
        {
            "key": "max_web_image_files",
            "label": "网页图片保留数",
            "type": "integer",
            "default": 500,
            "min": 10,
            "max": 5000,
            "hint": "用户在网页发送的图片，随消息长期展示。",
        },
        {
            "key": "max_qq_image_files",
            "label": "QQ 图片保留数",
            "type": "integer",
            "default": 200,
            "min": 10,
            "max": 5000,
            "hint": "从 QQ 收到的图片，供镜像取用。",
        },
        {
            "key": "max_voice_files",
            "label": "语音临时文件保留数",
            "type": "integer",
            "default": 200,
            "min": 10,
            "max": 5000,
            "hint": "语音合成与解码的中间产物，用后即删，此项为兜底回收上限。",
        },
        {
            "key": "max_segment_files",
            "label": "分段读取文件保留数",
            "type": "integer",
            "default": 500,
            "min": 10,
            "max": 5000,
            "hint": "分段读取落盘的正文，供旧消息「重新粘贴」按路径取回。",
        },
        {
            "key": "max_push_per_report",
            "label": "单次推送消息数",
            "type": "integer",
            "default": 10,
            "min": 1,
            "max": 100,
            "hint": "一次上报最多处理多少条，超出只取最新的。",
        },
    ],
}


def get_value(tool, key):
    """取某工具某个配置项的当前值；未配置时回退声明里的默认值。

    @param tool 工具名
    @param key  配置键
    @returns 当前值；该工具或键未声明时返回 None
    """
    for item in CONFIG_SCHEMA.get(tool, []):
        if item.get("key") != key:
            continue
        stored = ((runtime.CONFIG.get("tool_config") or {}).get(tool) or {}).get(key)
        return stored if stored is not None else item.get("default")
    return None


def coerce(item, raw):
    """把前端传来的原始值按声明类型转换并校验。

    @param item 配置声明项
    @param raw  原始值
    @returns 规范化后的值
    @raises ValueError 值不合法时抛出，调用方据此返回 400
    """
    t = item.get("type")
    if t == "integer":
        try:
            v = int(raw)
        except (TypeError, ValueError):
            raise ValueError("%s 必须是整数" % item.get("label"))
        # 钳到声明范围，避免越界值让工具行为异常
        lo, hi = item.get("min"), item.get("max")
        if lo is not None and v < lo:
            v = lo
        if hi is not None and v > hi:
            v = hi
        return v
    if t == "boolean":
        return bool(raw)
    if t == "multiselect":
        if not isinstance(raw, list):
            raise ValueError("%s 必须是数组" % item.get("label"))
        allowed = set(item.get("options") or [])
        # 只保留声明里列出的选项，防止塞入未知值
        return [str(x) for x in raw if str(x) in allowed]
    # string 及其它：转字符串
    return str(raw)


def all_specs():
    """返回全部工具的配置声明与当前值，供设置页通用渲染。

    @returns {工具名: [{key, label, type, value, hint, min, max, options, restart}]}
    """
    out = {}
    for tool, items in CONFIG_SCHEMA.items():
        rows = []
        for item in items:
            row = dict(item)
            row["value"] = get_value(tool, item["key"])
            rows.append(row)
        out[tool] = rows
    return out
