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


def main():
    args = sys.argv[1:]
    text, indent, sort_keys = "", 2, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--text":
            text = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        elif a == "--indent":
            try:
                indent = int(args[i + 1])
            except (ValueError, IndexError):
                indent = 2
            i += 2
        elif a == "--sort_keys":
            sort_keys = True
            i += 1
        else:
            i += 1

    try:
        data = json.loads(text)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "JSON 解析失败：" + str(e)}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=sort_keys))


if __name__ == "__main__":
    main()
