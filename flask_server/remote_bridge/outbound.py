"""远程桥接 —— 出站正文组装（QQ 与网页共用）

职责：按同一套规则，把一条消息组装成待发送的正文文本。

为什么要独立成模块：
- 网页版是 QQ 版的变体，出站规则（正文优先级、思考折叠、工具结果围栏）
  必须两边完全一致，否则会出现「QQ 有思考、网页没有」这类改造不彻底的问题；
- 本模块是这条规则的唯一来源，QQ 的 message_router 与网页的 web_mirror
  都调用它，任何规则调整只需改这一处。

不包含：角色前缀（QQ 加「🤖 AI」，网页靠气泡区分）、语音合成（QQ 推 QQ、
网页落网页音频）、QQ 特有的「不回推自己发的消息」过滤。
"""
from .message_parse import (
    _classify, _blocks_to_text, _thinking_text_of, _tool_result_of,
)


def build_body(m, push):
    """组装一条消息的出站正文（不含角色前缀）。

    @param m    消息对象
    @param push 推送开关字典（读取 thinking 控制思考是否随正文发出）
    @returns dict：{
        "kind":          消息类别 user / tool / ai,
        "text":          正文文本（已含思考折叠块，若开关开）,
        "markdown":      是否按 Markdown 发送,
        "is_tool_result": 是否工具结果（语音等附加能力据此跳过）,
        "skip":          是否无可发内容,
    }
    """
    kind = _classify(m)
    # 工具结果：本体是一段 JSON，包 json 围栏，按 Markdown 发送。
    tr = _tool_result_of(m)
    if tr is not None:
        return _tool_result_body(kind, tr)
    # 正文：优先 md 原文（保格式），退回块拼纯文本（不含思考）
    raw_md = str(m.get("md") or "").strip()
    body_text = raw_md or _blocks_to_text(m, False)
    # 思考：md 是复制按钮产物、不含思考，故从 blocks 独立提取；
    # 仅在「思考」开关打开时随正文发出。
    think = _thinking_text_of(m) if push.get("thinking", False) else ""
    if think:
        return _thinking_body(kind, think, body_text)
    return {
        "kind": kind, "text": body_text, "markdown": bool(raw_md),
        "is_tool_result": False, "skip": not body_text,
    }


def _tool_result_body(kind, tr):
    """工具结果的出站正文：用 json 围栏包住反序列化后的对象。

    直接用解析出的对象反序列化，不经块拼：后者会给代码块再包一层围栏，
    形成嵌套围栏、Markdown 渲染破损。
    @param kind 消息类别
    @param tr   工具结果对象
    @returns 正文结构字典
    """
    import json
    text = json.dumps(tr, ensure_ascii=False, indent=2)
    return {
        "kind": kind,
        "text": "```json\n" + text + "\n```",
        "markdown": True,
        "is_tool_result": True,
        "skip": False,
    }


def _thinking_body(kind, think, body_text):
    """带思考折叠块的出站正文：思考在前（json 围栏）、正文在后。

    代码块在前、正文在后，读者先看到回答、再按需查看思考。
    @param kind      消息类别
    @param think     思考文本
    @param body_text 正文文本
    @returns 正文结构字典
    """
    # 思考含三反引号时改用四反引号，避免提前闭合
    tick = "````" if "```" in think else "```"
    text = tick + "json\n" + think + "\n" + tick
    if body_text:
        text = text + "\n\n" + body_text
    return {
        "kind": kind, "text": text, "markdown": True,
        "is_tool_result": False, "skip": False,
    }
