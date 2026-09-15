#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""json_validate —— 自定义工具参考实现（规范见插件 说明文档.md §7）。

参数（arg_style=flag）：--text 文本 / --indent 数字 / --sort_keys（开关）。
- 标准输出为合法 JSON 时，原样返回给 AI；
- 非法 JSON 时以非 0 退出码结束，并输出 {"ok":false,"error":...}（触发 AI 自愈链路）。
调用方已强制 PYTHONIOENCODING=utf-8，Windows 下中文不乱码。
"""
import sys
import json


def _arg_value(args, i, default):
    """取 --x 后面紧跟的值；越界时返回默认值。"""
    return args[i + 1] if i + 1 < len(args) else default


def _parse_args(args):
    """解析命令行参数，返回 (text, indent, sort_keys)。

    支持 --text 文本 / --indent 数字 / --sort_keys 开关，未知参数忽略。
    """
    text, indent, sort_keys = "", 2, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--text":
            text = _arg_value(args, i, "")
            i += 2
        elif a == "--indent":
            try:
                indent = int(_arg_value(args, i, 2))
            except (ValueError, TypeError):
                indent = 2
            i += 2
        elif a == "--sort_keys":
            sort_keys = True
            i += 1
        else:
            i += 1
    return text, indent, sort_keys


def main():
    """入口：解析参数并校验 JSON，非法时以非 0 退出码结束（触发 AI 自愈链路）。"""
    text, indent, sort_keys = _parse_args(sys.argv[1:])
    try:
        data = json.loads(text)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "JSON 解析失败：" + str(e)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=sort_keys))


if __name__ == "__main__":
    main()
