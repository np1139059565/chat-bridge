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

1. 先在镜像插件设置页安装并上线 `skills/debug_chrome` 的工具（元素样式、截图、console / network 记录、执行 JS、消息推送）。
2. 「加载已解压的扩展程序」→ 选择 `skills/debug_chrome/extension/`。

### 冒烟测试

```bash
python flask_server/_smoke_ct.py
```

---

## 二、改动前的定位

| 要改什么 | 去哪里 |
|---|---|
| 新增/修改内置工具 | `flask_server/tools_impl.py`（改完需重启服务）；辅助在 `tool_helpers.py`，元数据在 `tool_meta.py` |
| 工具上线开关、端口、体积上限 | `flask_server/config.yaml` 或 `POST /config` |
| 卡片总线行为 | `flask_server/card_bus.py` + `routes/cards.py` |
| 外部工具转发 | `flask_server/external_tools.py` + `routes/ext.py` |
| 运行期全局状态（工具表 / 配置） | `flask_server/runtime.py` |
| 网页对话抓取、站点规则 | `extend/content/00_state.js`（PROFILES 表）+ `extend/content/02_blocks.js` |
| 抽屉 UI、卡片渲染 | `extend/dialog/parts/`（Vue 渲染函数）+ `extend/dialog/styles/` |
| 调试扩展行为 | `skills/debug_chrome/extension/**` |
| 技能说明注入 | `skills/<name>/tool.json` 的 `prompt` 字段；技能清单由后端扫描 `skills/` 生成 |
| 规则 | `rules/*.md`（设置页可编辑） |

---

## 三、必须遵守的约定

### 3.1 工具实现（tools_impl.py）

- 参数不合法抛 `ToolParamError`（归类为 `parameter`）。
- 其它异常视为 `tool_internal`，提示 AI 改参数无效、需检查工具实现。
- 必填参数用 `tool_helpers.require(p, "参数名")` 校验，报错信息里点明正确参数名。
- 结果体积受 `limits.max_json_chars` 限制（`tool_helpers.enforce_size_limit`），超限**报错**而不是截断（避免喂不完整结果）。
- 文件类工具路径口径统一：绝对路径原样使用，相对路径以工程根为基准解析（`tool_helpers.abspath`）。
- 读取 skill 目录内的文档统一走 `list_skills` / `read_skill`（`read_skill` 参数 `skill` + `file` 相对路径），
  不要用 `read_file` 拼 `skills/xxx/SKILL.md`。新增 skill 文档读取需求时也应遵循此约定。

### 3.2 错误分类不可破坏

`error_utils.classify_error` 用 `param_error_cls()` 动态取当前模块（`runtime.impl`）的 `ToolParamError`，以兼容实现模块被替换的场景。**不要**在模块顶层 `from tools_impl import ToolParamError`——实现模块被替换后类对象会失配，参数错误被误判为代码缺陷。

### 3.3 卡片

- 工具卡片挂在消息树节点的 `node.cards` 上（按代码块 id 索引）；`cardMap` 是由全部节点卡片聚合出的 computed 视图。外部卡片存 `conv.externalCards`。两者都按会话隔离并持久化。
- 外部卡片「发送即结束」：登记即返回，卡片入列即 `POST /api/cards/<id>/delivered` 确认已展示，此后不再投递；任务进展由网页 AI 用 `push_message` 主动推送。
- 外部卡片带 `anchorKey`（消息树 key）：渲染时按锚点插入到对应消息之后；锚点不在当前列表时放到末尾。镜像区会跳过已处理且无消息本体的卡片，避免与消息本体重复显示。

### 3.4 站点规则（extend/content/00_state.js）

- 只用稳定类名 / 语义选择器，**不要**用 CSS-Module 哈希类（会随前端发版失效）。
- 一个消息可能被拆成多个容器（文字 + 代码块），抓取时必须全取，否则会漏掉工具调用代码块。

### 3.5 System Prompt

由 `extend/dialog/parts/05_messages.js` 的 `generateSystemPrompt()` 拼装，按 tool / rule / skill 三类组织，每类两段：
- TOOL：调用说明（格式与约束，含参数由 AI 调 `get_tool_params` 自取）、工具列表。
- RULE：读取说明、规则列表（含优先级与摘要）。
- SKILL：读取说明、技能列表（含摘要、所含工具与已上线技能的统一说明）。

技能数据来自后端 `/prompt_sections`（同时返回 `sections` 与 `skills`）。

### 3.6 扩展的网络请求：一律走后台代发

**约定**：Chrome 扩展的内容脚本（content script）**只做 DOM 操作，不直接发网络请求**；
所有后端请求统一交给 service worker 代发。

**为什么**：内容脚本运行在页面源下。Chrome 的 Private Network Access 会拦截
「公网页面 → 本机回环地址（127.0.0.1）」的请求：

```
Access ... blocked by CORS policy: Permission was denied for this request
  to access the `loopback` address space.
```

表现为扩展「一直显示未连接」。service worker 是扩展源，不受此限制。

**做法**（debug_chrome 扩展）：
- 内容脚本调用 `A.proxyFetch(url, {method, body, timeoutMs})`（定义在 `content/01_config.js`），
  它经 `chrome.runtime.sendMessage({type:'proxy-fetch'})` 转给 service worker。
- service worker 里 `proxy-fetch` 分支代发请求并回传结果。
- **不要**在内容脚本里直接写 `fetch(...)`。新增请求时改走 `proxyFetch`。

**抽屉 iframe 例外**：抽屉挂在 `chrome-extension://` 源下，不受此限制，可直接 fetch。
chat-bridge 扩展的所有请求都在抽屉 iframe 里，故无需改造。

**内容脚本里的消息收发注意**：用 `chrome.runtime.sendMessage(msg, callback)` 接收后台的
`sendResponse`——响应只进这个回调，**不会**作为独立消息触发 `chrome.runtime.onMessage`。
早先截图超时就是踩了这个坑。

### 3.7 配置文件的密钥分离

**约定**：含密钥的配置与不含密钥的配置**必须分文件存放**，前者 gitignore，后者入库。

**为什么**：远程桥接曾把 QQ 凭证（`app_id`/`app_secret`）与自定义指令（`commands`）
混在 `remote_bridge.yaml` 一个文件里，而该文件因含密钥被 gitignore 排除——
结果换机器时指令跟着凭证一起丢失。

**现状**（`flask_server/` 下）：

| 文件 | 内容 | 是否入库 |
|---|---|---|
| `remote_bridge.yaml` | 仅 QQ 凭证 | 否（gitignore） |
| `remote_bridge_settings.yaml` | 开关、指令、选择器等 | 是 |
| `remote_bridge_state.json` | 已推送去重记账 | 否（运行时产物） |

`bridge_store.py` 的 `_read_merged()` 负责合并读取，并在读到旧格式
（密钥文件里混有非密钥字段）时**自动迁移**：把非密钥字段搬到设置文件。

**新增配置项时**：先判断它含不含密钥，决定写入哪个文件。
`SECRET_KEYS` 列出只进密钥文件的字段。

---

## 四、常见任务

### 新增一个内置工具

1. 在 `tool_meta.py` 的元数据表加参数声明，在 `tools_impl.py` 的 `DISPATCH` 注册实现函数。
2. 重启服务。
3. 在设置页上线（写 `config.yaml`）。

### 新增一个 skill

1. 建 `skills/<name>/tool.json`（含 `name`/`description`/`parameters`，可选 `provider`/`prompt`/`executor`）。
2. 设置页扫描 + 安装 + 上线。

### 排查「工具调用不生成卡片」

1. 网页控制台过滤 `[AI-Mirror]`，看 `extractBlocks` 抓到的消息数。
2. 确认代码块在 **assistant** 消息里，且 JSON 含 `"type": "bridge-chat-call"`。
3. 确认 `parseToolCall` 未因语言标记过滤而漏判（DeepSeek 无 lang 标记）。

### 排查「外部工具离线」

- 提供方在线判定为 10 秒内有 `poll`（`external_tools.ONLINE_WINDOW`）。在线状态仅用于界面指示灯，不参与执行判断。
- 命令路由依据「目标页面的工具（抽屉）是否打开」：扩展每次轮询上报 `is_open`，目标页面工具未打开时命令立即逸散到其他页面代收，不再依赖时间窗猜测。
- 命令等待上限为 10 秒（`external_tools.FORWARD_TIMEOUT`），超时返回 `ForwardTimeout`（origin=environment）。

---

## 五、已知问题（待处理）

| 编号 | 位置 | 问题 |
|---|---|---|
| M1 | `extend/dialog/parts/00_data.js` / `04_sessions.js` | （已修）外部卡片曾未按会话隔离 / 不持久化 |
| M2 | `extend/dialog/parts/06_execute.js` | （已修）关闭自动开关后外部卡片曾卡死 |
| M3 | `flask_server/card_bus.py` | 卡片投递为全局 claim，多标签页可能串台 |
| D1 | `flask_server/routes/ext.py` | （已修）提供方通道按 `page_url` / `is_open` 定向，目标页面工具未开即逸散 |
| D2 | `skills/debug_chrome/extension/content/03_heartbeat.js` | 抽屉折叠即停轮询 → 10 秒后判离线（仅影响指示灯） |
| D3 | `skills/debug_chrome/extension/content/05_tool-handlers.js` | （已修）`get_element_style` 强制采集样式，默认返回常用属性集 |
| D4 | `skills/debug_chrome/extension/content/00_namespace.js` | 后端地址端口硬编码 5000 |
| D5 | `extend/content/00_state.js` | DeepSeek 输入框选择器含哈希类 |
| D6 | `skills/debug_chrome/tool.json` / `extend/dialog/parts/` | （已修）参数名与 silent 语义边角不一致 |

---

## 六、验证脚本

> 代码走查结论与待办清单见 `docs/code-review-report.md`。

- `flask_server/_smoke_ct.py`：自定义工具子系统冒烟测试（解析 → 安装 → 落盘 → 回读 → 上线 → 执行 → 缺参报错 → 扫描 → 删除）。
- `scripts/check_quality.py`：行数 / 圈复杂度 / 重复块质量扫描。

### pre-commit 钩子

`.pre-commit-config.yaml` 以本地钩子（`repo: local`）挂载两项检查，提交时自动运行：

- `scripts/hooks/check_syntax.py`：校验本次改动文件的语法（py / js / json / yaml）。
  PyYAML 或 node 缺失时跳过，不把环境缺失误判为代码错误。
- `scripts/hooks/check_hygiene.py`：拦截临时备份文件（`*.bak`、`*~` 等）与超过 450 行的源码。
  第三方库（`vendor/`）、压缩产物与锁文件豁免行数检查。

安装一次即可：`pre-commit install`；手动全量运行：`pre-commit run --all-files`。
