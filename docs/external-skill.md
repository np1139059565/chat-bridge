# 外部 skill 规范（chat-bridge）

> 适用对象：向宿主注册能力的外部工具包（`skills/<name>/`）。
> 本文规定 skill 的目录结构、声明文件写法与注册流程。

---

## 一、什么是 skill

skill 是「一组能力 + 说明」的封装。宿主扫描 `skills/` 目录，
把每个 skill 的工具、指令、说明纳入系统。

目前 skill 可提供：
- **工具**（`tool.json` 的 `tools`）
- **指令**（`tool.json` 的 `commands`，见外部指令规范，待实现）
- **说明**（`tool.json` 的 `prompt` + `SKILL.md`）

---

## 二、目录结构

```
skills/<name>/
├── tool.json      # 声明文件：provider、工具、指令、注入说明
├── SKILL.md       # 技能说明文档（供 AI 读取）
├── README.md      # 面向人的简介（可选）
└── extension/     # 扩展代码（若为浏览器扩展，可选）
```

---

## 三、声明文件 tool.json

```json
{
  "provider": "debug_chrome",
  "prompt": "本技能提供……（注入给 AI 的处理要求）",
  "tools": [ /* 见外部工具规范 */ ],
  "commands": [ /* 见外部指令规范 */ ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `provider` | 是 | 提供方标识，扩展轮询命令时用它认领 |
| `prompt` | 否 | 注入 System Prompt 的说明 |
| `tools` | 否 | 工具数组 |
| `commands` | 否 | 指令数组（外部指令规范，待实现） |

---

## 四、SKILL.md 写法

`SKILL.md` 是给 AI 读的说明书，按以下结构组织：

| 章节 | 内容 |
|---|---|
| 标题 + 一句话简介 | 这是什么 |
| 能力 | 提供哪些工具 / 指令，用表格列 |
| 交互方式 | 被调用、主动对话两条通道怎么走 |
| 外部卡片 | 信封结构与投递语义 |
| 处理要求 | AI 必须遵守的步骤与约束 |

要点：
- **处理要求里要写清「若本次会话尚未读过本说明，先用 `read_skill` 读取」**，避免 AI 凭记忆臆测。
- 需要读写本地文件时，声明「用镜像插件的本地工具，不臆造工具名」。
- 读取 skill 文档统一走 `read_skill`（参数 `skill` + `file` 相对路径），
  不要用 `read_file` 拼 `skills/xxx/SKILL.md`。

---

## 五、注册流程

1. 建 `skills/<name>/tool.json`（含 `provider`、`tools`；`prompt` 可选）。
2. 建 `SKILL.md`。
3. 设置页扫描 + 安装 + 上线。
4. 技能清单由后端扫描 `skills/` 生成，注入 System Prompt 的 SKILL 段。

---

## 六、约定速查

- 工具声明 → 外部工具规范。
- 指令声明 → 外部指令规范。
- 主动联系 AI → 外部卡片规范。
- 内容脚本不直接发网络请求，一律走 `proxyFetch`（见开发指南 3.6）。
