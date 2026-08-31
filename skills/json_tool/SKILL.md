---
name: json_tool
description: 校验并格式化 JSON 文本的技能。当用户需要判断 JSON 是否合法、美化输出或按 key 排序时使用；同时作为「AI 工具调用镜像插件」的自定义工具参考实现，通过 tool.json 暴露 json_validate 工具。
---

# json_tool

校验并格式化 JSON 文本的技能。

## 何时使用
- 判断一段 JSON 是否合法，并定位具体错误原因。
- 将紧凑 JSON 美化输出（带缩进），或按 key 排序以便比对。
- 作为「AI 工具调用镜像插件」自定义工具的参考实现，演示如何在一个标准技能之上挂载可执行工具、供网页 AI 调用。

## 资源
- `scripts/json_validate.py`：接收 `--text <json>`、`--indent <数字>`、`--sort_keys` 三个参数，向标准输出打印美化后的 JSON；遇到非法 JSON 时以非 0 退出码结束并打印错误说明。

## 自定义工具（镜像插件）
本技能在符合标准结构（即本 SKILL.md）的基础上，另于根目录提供 `tool.json`，按插件规范声明自定义工具 `json_validate`。自定义工具约定的写法、字段与脚本规则见同目录 `README.md`；插件全局规范见 `说明文档.md` §7。
