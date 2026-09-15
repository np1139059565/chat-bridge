# 开发指南（chat-bridge）

面向接手的开发者与 AI：如何运行、改动、排查，以及必须遵守的约定。

---

## 一、运行

### 本地工具服务

```bash
cd flask_server
pip install -r requirements.txt
python server.py
```
默认 `http://127.0.0.1:5000`。改端口：编辑 `config.yaml` 的 `flask.port` 并重启。

### 镜像插件

1. `chrome://extensions` → 开启开发者模式。
2. 「加载已解压的扩展程序」→ 选择 `extend/` 目录。
3. 点工具栏图标显示 / 隐藏抽屉。

### 调试扩展

1. 先在镜像插件设置页安装并上线 `skills/debug_chrome` 的三个工具。
2. 「加载已解压的扩展程序」→ 选择 `skills/debug_chrome/extension/`。

### 冒烟测试

```bash
python flask_server/_smoke_ct.py
```

---

## 二、改动前的定位

| 要改什么 | 去哪里 |
|---|---|
| 新增/修改内置工具 | `flask_server/tools_impl.py`（改完可热重载） |
| 工具上线开关、端口、体积上限 | `flask_server/config.yaml` 或 `POST /config` |
| 卡片总线行为 | `flask_server/card_bus.py` + `routes_cards.py` |
| 外部工具转发 | `flask_server/external_tools.py` + `routes_ext.py` |
| 网页对话抓取、站点规则 | `extend/content.js`（PROFILES 表） |
| 抽屉 UI、卡片渲染 | `extend/dialog/app.js`（Vue 渲染函数）+ `style.css` |
| 调试扩展行为 | `skills/debug_chrome/extension/**` |
| 技能说明注入 | `skills/debug_chrome/tool.json` 的 `prompt` 字段 |
| 规则 | `rules/*.md`（设置页可编辑） |

---

## 三、必须遵守的约定

### 3.1 工具实现（tools_impl.py）

- 参数不合法抛 `ToolParamError`（归类为 `parameter`）。
- 其它异常视为 `tool_internal`，AI 会据此触发自愈。
- 必填参数用 `_require(p, "参数名")` 校验，报错信息里点明正确参数名。
- 结果体积受 `limits.max_json_chars` 限制，超限**报错**而不是截断（避免喂不完整结果）。
- `read_file` 只接受**绝对路径**，不做「相对工程根」的隐式解析（避免耦合）。
- 读取 skill 目录内的文档统一走 `read_skill`（参数 `skill` + `file` 相对路径），
  不要用 `read_file` 拼 `skills/xxx/SKILL.md`。新增 skill 文档读取需求时也应遵循此约定。

### 3.2 错误分类不可破坏

`server.classify_error` 用 `param_error_cls()` 动态取当前模块的 `ToolParamError`，以兼容热重载。**不要**在 server 顶层 `from tools_impl import ToolParamError`——热重载后会失配，参数错误被误判为代码缺陷。

### 3.3 卡片

- 工具卡片存 `conv.cardMap`；外部卡片存 `conv.externalCards`。两者都按会话隔离并持久化。
- 外部卡片「发送即结束」：投递后立即置 `done` 并回填 `/api/cards/<id>/reply`，**不等待** AI 回复信封。
- 外部卡片与文字消息共用统一时间戳 `_ts`（毫秒，同一单调时间源），渲染时统一排序，不做类型特殊处理。

### 3.4 站点规则（content.js）

- 只用稳定类名 / 语义选择器，**不要**用 CSS-Module 哈希类（会随前端发版失效）。
- 一个消息可能被拆成多个容器（文字 + 代码块），抓取时必须全取，否则会漏掉工具调用代码块。

### 3.5 System Prompt

由 `extend/dialog/app.js` 的 `generateSystemPrompt()` 拼装，工具列表只给名称与描述，参数由 AI 调 `get_tool_params` 自取；技能说明来自后端 `/prompt_sections`，注入到最末尾。

---

## 四、常见任务

### 新增一个内置工具

1. 在 `tools_impl.py` 的 `TOOLS` 加参数声明，在 `DISPATCH` 注册实现函数。
2. 调 `POST /hot_fix` 或重启服务。
3. 在设置页上线（写 `config.yaml`）。

### 新增一个 skill

1. 建 `skills/<name>/tool.json`（含 `name`/`description`/`parameters`，可选 `provider`/`prompt`/`executor`）。
2. 设置页扫描 + 安装 + 上线。

### 排查「工具调用不生成卡片」

1. 网页控制台过滤 `[AI-Mirror]`，看 `extractBlocks` 抓到的消息数。
2. 确认代码块在 **assistant** 消息里，且 JSON 含 `"type": "bridge-chat-call"`。
3. 确认 `parseToolCall` 未因语言标记过滤而漏判（DeepSeek 无 lang 标记）。

### 排查「外部工具离线」

- 提供方在线判定为 3 秒内有 `poll`。调试扩展仅在**抽屉展开且页面活动**时轮询。
- 若需在抽屉折叠时仍可服务，需改 `content/03_heartbeat.js` 的轮询条件。

---

## 五、已知问题（待处理）

| 编号 | 位置 | 问题 |
|---|---|---|
| M1 | `extend/dialog/app.js` | （已修）外部卡片曾未按会话隔离 / 不持久化 |
| M2 | `extend/dialog/app.js` | （已修）关闭自动开关后外部卡片曾卡死 |
| M3 | `card_bus.py` | 卡片投递为全局 claim，多标签页可能串台 |
| D1 | `routes_ext.py` | 提供方通道未按 tab 定向，多标签页指令串台 |
| D2 | `content/03_heartbeat.js` | 抽屉折叠即停轮询 → 3 秒后判离线 |
| D3 | `05_tool-handlers.js` | `get_element_style` 默认不返回样式 |
| D4 | `00_namespace.js` | 后端地址端口硬编码 5000 |
| D5 | `content.js` | DeepSeek 输入框选择器含哈希类 |
| D6 | `tool.json` / `app.js` | 参数名与 silent 语义边角不一致 |

---

## 六、Git / 产物

- 知识图谱产物 `graphify-out/` 已在 `.gitignore`。
- `_verify_fixes.py` 用于验证修复。
