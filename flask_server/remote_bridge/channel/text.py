"""远程桥接 —— 正文组装公共层

职责：把一条消息的内容块拼成适合手机阅读的正文。

为什么要有公共层：
    企业微信与微信两份实现逐字相同，连注释都近似，
    改一处必须记得改另一处，漏一处就是行为不一致。
    这类「与通道无关」的逻辑收拢到一处，通道只声明自己的标识。

与通道有关的只有两处，通过参数传入：
    - 通道名（用于判断「这条是不是我自己发出去的」，避免复读）
    - 是否合并（由适配器自己决定，不在本模块）
"""
from .. import message_parse as mp

# 单条消息最多发送的字符数
MAX_TEXT_CHARS = 3500

# 各类消息的展示前缀
PREFIX = {"user": "👤 用户", "tool": "🛠 工具", "ai": "🤖 AI"}


def truncate(text, limit=None):
    """按上限截断文本，保留首尾。

    开头通常是结论、结尾通常是收尾说明，中间细节对手机阅读价值较低。

    @param text  原文本
    @param limit 字符上限；缺省用模块常量
    @returns 截断后的文本
    """
    cap = limit or MAX_TEXT_CHARS
    if len(text) <= cap:
        return text
    head = cap * 2 // 3
    tail = cap - head - 20
    return text[:head] + "\n\n…（中间省略）…\n\n" + text[-tail:]


def is_own_source(m, channel):
    """判断消息是否由指定通道自己投递。

    自己发出去的外部卡片会以 external-call 信封落回消息树，
    若不识别出来，用户会看到自己刚发的话被机器人复读一遍。

    @param m       消息对象
    @param channel 通道名（qq / weixin / wecom）
    @returns 来自该通道返回 True
    """
    obj = mp._parse_envelope(m)
    return bool(obj and obj.get("source") == channel)


def extract_text(m, push, use_md=False):
    """提取正文：保留自然语言与普通代码，剔除工具调用痕迹。

    工具调用的 JSON 参数在手机上是一屏花括号，属噪音，故剔除；
    真代码块保留——用户可能确实要看代码。

    @param m       消息对象
    @param push    推送开关
    @param use_md  是否优先采用采集到的 Markdown 原文。
                   支持 Markdown 的通道（QQ / 企微）传 True，能保住标题、
                   粗体、列表等格式；不支持的通道（微信）传 False，避免
                   用户看到裸的井号与星号。
    @returns 正文文本；无可用内容返回空串
    """
    # Markdown 原文由前端「复制」按钮采集，格式最完整；
    # 缺失时退回按块拼纯文本，保证内容不丢。
    if use_md:
        raw = str(m.get("md") or "").strip()
        if raw:
            return raw
    parts = []
    for b in (m.get("blocks") or []):
        if not b:
            continue
        btype = b.get("type")
        if btype == "code":
            obj = mp._load_json_block(b)
            # 工具调用 / 工具结果 / 语音块都不进正文
            if obj and obj.get("type") in (
                    "bridge-chat-call", "bridge-chat-res", "bridge-voice"):
                continue
            code = str(b.get("code") or "").strip()
            if code:
                parts.append("```\n" + code + "\n```")
            continue
        fn = mp._BLOCK_HANDLERS.get(btype)
        if not fn:
            continue
        text = fn(b, bool(push.get("thinking")))
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def body_of(m, push, channel, check_own=True, use_md=False):
    """取一条消息的待推正文（含类型前缀）；不可推返回空串。

    @param m         消息对象
    @param push      推送开关
    @param channel   通道名，用于判断是否自己发的
    @param check_own 是否在此处检查「自己发的」。
                     走合并批次的通道（微信）由管线在上游过滤过，
                     此处传 False 避免重复判断。
    @param use_md    是否优先采用 Markdown 原文（见 extract_text）
    @returns 正文
    """
    if check_own and is_own_source(m, channel):
        return ""
    text = extract_text(m, push, use_md)
    if not text:
        return ""
    kind = mp._classify(m)
    return "%s\n%s" % (PREFIX.get(kind, kind), text)
