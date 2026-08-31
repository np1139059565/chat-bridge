# json_tool · 自定义工具约定（补充）

`SKILL.md` 是本技能符合**标准 skill 规范**的基础（必含 `name`/`description` 的 YAML 前置元数据 + 使用说明），由 CodeBuddy/用户按标准方式识别与加载。本文件只补充「AI 工具调用镜像插件」特有的自定义工具约定——即如何在标准 skill 之上，用 `tool.json` 把一个可执行脚本挂载为网页 AI 可调用的工具。

## 两层结构（一个能被插件识别的 skill）
1. **标准 skill 基础**：根目录 `SKILL.md`（必含 `name`/`description` 前置元数据 + 正文）。
2. **自定义工具扩展**：根目录 `tool.json`（见下方规范），声明要暴露给网页 AI 的工具。

插件扫描时只认 `tool.json`，但 `SKILL.md` 是 skill 符合标准结构的前提；二者共同构成一个“标准 skill + 自定义工具”的可安装单元，缺一不可。

## tool.json 最小结构
```json
{
  "tools": [
    {
      "name": "你的工具名",
      "description": "给 AI 看的功能说明",
      "script": "scripts/your.py",
      "interpreter": "python",
      "arg_style": "flag",
      "parameters": [
        { "name": "x", "type": "string", "required": true, "description": "参数说明" }
      ]
    }
  ]
}
```

## 脚本约定（关键）
- 用 `--名 值` 读取参数（`arg_style=flag` 时）；`boolean` 为真时只传 `--名`。
- 标准输出若是合法 JSON，原样返回给 AI；否则会被包成 `{"stdout": "..."}`。
- 出错时**以非 0 退出码结束**，并往标准错误打印信息（会触发 AI 自愈链路）。
- 务必输出 UTF-8（调用处已强制 `PYTHONIOENCODING=utf-8`，Windows 下中文不乱码）。

## 本 skill 的实例
- `scripts/json_validate.py` + `tool.json` 中的 `json_validate` 是上述规范的最小可运行示例，可直接安装，也可复制改写后成为你自己的工具。
