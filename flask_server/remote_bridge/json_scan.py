"""远程桥接 —— 文本内 JSON 对象扫描（共享）

背景：工具调用、工具结果、外部信封、语音等「带 type 的 JSON 载荷」，
标准形态是带围栏的代码块，但生成侧可能漂移成「裸 JSON」（无围栏），
此时它只存在于正文文本里，需从文本中扫描切出。

message_voice 与 message_parse 各自实现过一份大括号配平扫描，
本模块集中此逻辑，供两处共用，避免重复维护。
"""
import json


def scan_json_object(text, start):
    """从 text[start] 起做大括号配平扫描，返回完整 JSON 对象的结束下标。

    尊重字符串与转义：字符串内的 { } " 不参与配平。
    @param text  待扫描文本
    @param start 起始下标（应为 '{'）
    @returns 结束下标（不含）；未配平返回 -1
    """
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def parse_json_object(text, start):
    """从 text[start] 起扫出并解析一个 JSON 对象；失败返回 None。

    @param text  待扫描文本
    @param start 起始下标（应为 '{'）
    @returns 解析出的 dict；非对象或解析失败返回 None
    """
    end = scan_json_object(text, start)
    if end <= 0:
        return None
    try:
        obj = json.loads(text[start:end])
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def find_json_by_type(text, want_type):
    """在文本里找第一个 type 等于 want_type 的 JSON 对象。

    为避免误判（正文恰好讨论该标记），要求 JSON 以 { 起头、大括号配平，
    且解析出的 type 必须确为 want_type。
    @param text      待扫描文本
    @param want_type 目标 type 值
    @returns 匹配的 dict；无则 None
    """
    if not text:
        return None
    i = text.find("{")
    while i >= 0:
        obj = parse_json_object(text, i)
        if obj is not None and obj.get("type") == want_type:
            return obj
        # 未命中则从下一个 { 继续尝试
        i = text.find("{", i + 1)
    return None
