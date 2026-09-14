# AI 调试能力挂靠 chat-bridge 方案

---

## 术语表

| 名称 | 指代 |
|---|---|
| **工具服务** | `chat-bridge-main` 的 Flask 后端 |
| **镜像插件** | `chat-bridge-main` 的 Chrome 扩展（右侧抽屉、工具卡片、网页对话镜像） |
| **调试扩展** | `debug_chrome`，Chrome 扩展，提供页面点选、探查、截图、推送 |

---

## 一、目标

调试扩展的能力接入工具服务，由工具服务提供通用接口与「与网页 AI 对话」通道；调试扩展承担页面交互。

设计原则：

- 工具服务只承载公共能力，不含调试扩展专属逻辑。
- 调试扩展以自包含目录的形式落位于 `skills/debug_chrome/`，其内部隔离扩展代码与工具声明、文档。
- 技能可向 System Prompt 注入一段统一说明，用于交代其工具的使用时机与约定，注入区域独立于 System Prompt 正文。

---

## 二、总体架构

```
调试扩展抽屉 ──POST /api/cards(挂起)──▶ 工具服务 card_bus ──心跳──▶ 镜像插件
                                                                      │
                                                              右侧对话列表渲染外部卡片
                                                                      │
                                                              倒计时→自动发网页 AI→按 id 捕获结果
                                                                      │
工具服务 card_bus ◀──POST /api/cards/<id>/reply── 镜像插件 ──▶ 挂起的 POST 返回结果

网页 AI 工具调用 ──▶ 工具卡片 ──POST /tool(挂起)──▶ 工具服务外部工具队列
                                                        │
                                          调试扩展 ──/api/ext/<provider>(poll)──▶ 取走命令
                                                        │
                                          页面执行(定位/快照/推送)
                                                        │
                                          /api/ext/<provider>(result) ──▶ 放行 /tool ──▶ 卡片显示结果 ──自动回传网页 AI
```

---

## 三、目录规划

```
chat-bridge-main/
├── flask_server/
│   ├── card_bus.py           # 公共：卡片总线
│   ├── routes_cards.py       # 公共：POST /api/cards
│   ├── external_tools.py     # 公共：外部工具提供方注册与转发
│   ├── routes_ext.py         # 公共：POST /api/ext/<provider>
│   ├── custom_tools.py       # 公共：自定义工具加载
│   ├── prompt_sections.py    # 公共：技能说明段落收集
│   └── server.py             # 公共：服务入口
├── extend/
│   ├── content.js            # 公共：外部卡片渲染、信封检索
│   └── dialog/
│       ├── app.js            # 公共：卡片支持 source、按 id 回填、技能说明注入
│       └── style.css         # 公共：外部卡片样式
└── skills/
    └── debug_chrome/         # 调试扩展（自包含）
        ├── tool.json         # 工具声明（含 prompt 字段）
        ├── SKILL.md          # 技能说明（信封结构、处理规则）
        ├── README.md         # 使用说明
        └── extension/        # Chrome 扩展代码
            ├── manifest.json
            ├── service_worker.js
            ├── vendor/       # 前端依赖
            ├── content/      # 内容脚本
            └── drawer/       # 抽屉页面
```

`skills/debug_chrome/` 内部分层：

- 根目录：工具声明与文档。
- `extension/`：Chrome 扩展全部代码。

`flask_server/` 内只使用通用概念（卡片、提供方、外部工具、技能说明段落）。

---

## 四、工具服务（公共能力）

### 4.1 卡片总线

文件：`flask_server/card_bus.py`

**卡片模型**

| 字段 | 说明 |
|---|---|
| id | 卡片唯一标识，同时作为结果归属标识 |
| source | 来源，取 `tool` 或 `external` |
| type | 信封类型，外部卡片为 `debug-chrome-req` 一类标识 |
| title | 卡片标题 |
| content | 发送给网页 AI 的正文 |
| payload | 附加上下文 |
| status | `pending` / `counting` / `sending` / `waiting_reply` / `done` / `error` / `timeout` |
| created_at | 创建时刻，决定对话列表时序 |
| timeout_ms | 等待上限 |
| result / error | 最终结果 |

**核心能力**：创建并挂起、按 `id` 回填唤醒、超时置 `timeout` 并唤醒。

### 4.2 公共卡片接口

文件：`flask_server/routes_cards.py`

`POST /api/cards`

- 请求：`{ type, title, content, payload, timeout_ms }`
- 行为：创建卡片 → 推给镜像插件 → 阻塞等待至结果回填或超时
- 成功返回：`{ success: true, id, result }`
- 超时返回：`{ success: false, id, error: "TIMEOUT" }`

### 4.3 外部工具与提供方

文件：`flask_server/external_tools.py`

维护「提供方」注册表。提供方来自技能声明（`tool.json` 中的 `provider`），工具定义来自同一 `tool.json`。

- 工具在设置页上线后即并入 `/tools` 与 System Prompt，与提供方是否在线无关。
- 调用 `POST /tool` 且工具属于某提供方时，若提供方在线则请求挂起，命令入该提供方队列，等 `/api/ext/<provider>` 的 `result` 到达后放行；若提供方离线则返回离线错误。

### 4.4 提供方通道

文件：`flask_server/routes_ext.py`

`POST /api/ext/<provider>`

| action | 作用 |
|---|---|
| `poll` | 兼作心跳，返回待执行命令列表 |
| `result` | 携带 `request_id` 与结果，唤醒挂起的 `POST /tool` |

`<provider>` 由技能声明。

### 4.5 卡片投递与回填接口

| 接口 | 调用方 | 作用 |
|---|---|---|
| `GET /api/cards/pending` | 镜像插件 | 取走尚未投递的卡片 |
| `POST /api/cards/<id>/reply` | 镜像插件 | 携带结果回填卡片，唤醒挂起的 `POST /api/cards` |

### 4.6 自定义工具加载

文件：`flask_server/custom_tools.py`

`tool.json` 解析支持字段：

- `provider`：工具所属提供方名。
- `prompt`：技能统一说明，供 System Prompt 注入。
- `executor`：`script`（子进程执行）或 `external`（转发给提供方）。

`executor=external` 的工具不执行脚本，交由 `external_tools.py` 转发。

### 4.7 技能说明段落

文件：`flask_server/prompt_sections.py`

收集各技能在 `tool.json` 中声明的 `prompt` 内容，供镜像插件注入 System Prompt。

- 生效条件：该技能下有至少一个工具处于上线状态。
- 段落内容按技能分组，附技能名。

`GET /prompt_sections`

- 返回：`{ success: true, sections: [ { skill, text } ] }`

### 4.8 服务入口

文件：`flask_server/server.py`

- 启动时开启多线程。
- 注册卡片路由、提供方通道路由、技能说明段路由。
- 启动时加载外部工具提供方。

### 4.9 镜像插件端

| 文件 | 职责 |
|---|---|
| `extend/dialog/app.js` | 卡片渲染支持 `source`；按 `id` 检索信封结构并回填；拉取技能说明段落并注入 System Prompt 末尾 |
| `extend/content.js` | 外部卡片渲染驱动 |
| `extend/dialog/style.css` | 外部卡片样式，与工具卡片视觉一致，以徽标区分来源 |

**System Prompt 注入**

技能说明段落注入到整个 System Prompt 的最末尾，区域标题为【技能说明】，按技能分小标题排列：

```
……（原有内容）

【技能说明】
### debug_chrome
<该技能的 prompt 内容>
```

无段落时整块省略。

### 4.10 信封与结果归属

外部卡片通过信封结构与网页 AI 往返，信封以 `type` 区分方向、以 `id` 配对。

**输入信封**（发往网页 AI）

```
{
  "type": "debug-chrome-req",
  "id": "<card_id>",
  "request": ...
}
```

**输出信封**（网页 AI 回复）

```
{
  "type": "debug-chrome-res",
  "id": "<card_id>",
  "result": ...
}
```

**镜像插件处理**

- 发送时按输入信封封装，卡片自身记录其 `type`。
- 镜像到助手消息后，从任意块（代码块或文本块）提取顶层 JSON 对象，匹配 `type` 为该卡片对应的输出信封类型、且 `id` 相同者；命中则经 `POST /api/cards/<id>/reply` 回填工具服务，唤醒挂起的 `POST /api/cards` 请求。
- 输出信封类型由输入信封类型推导（`-req` 对应 `-res`）。
- 未命中任何待回填卡片的信封按普通内容处理。

---

## 五、skills/debug_chrome/（调试扩展）

### 5.1 tool.json

```
{
  "provider": "debug_chrome",
  "prompt": "本技能提供页面探查能力，相关工具通过「外部调试卡片」与调试扩展交互。当收到 type=debug-chrome-req 的消息时，属于外部调试卡片任务。处理要求：若本次会话尚未阅读过本技能说明，请先读取 skills/debug_chrome/SKILL.md，再按其规定处理；同一会话内只需读取一次；完成后按 SKILL.md 规定的结构回复。",
  "tools": [
    {
      "name": "get_element_style",
      "description": "按选择器采集元素样式与 DOM 信息",
      "executor": "external",
      "parameters": [
        { "name": "selector", "type": "string", "required": true, "description": "CSS 选择器" }
      ]
    },
    {
      "name": "get_page_snapshot",
      "description": "采集页面快照",
      "executor": "external",
      "parameters": [
        { "name": "snapshot_type", "type": "string", "required": true, "description": "dom 或 screenshot" }
      ]
    },
    {
      "name": "push_message",
      "description": "向调试扩展抽屉推送一条文字信息",
      "executor": "external",
      "parameters": [
        { "name": "text", "type": "string", "required": true, "description": "推送内容" },
        { "name": "title", "type": "string", "required": false, "description": "可选标题" }
      ]
    }
  ]
}
```

### 5.2 生效方式

- 技能需经设置页扫描安装，安装后三个工具出现在自定义工具列表。
- 工具上线后即并入 `/tools` 与 System Prompt；同时其 `prompt` 内容进入【技能说明】段落。
- 调试扩展离线时，工具仍在列表中，仅调用时返回离线错误。

### 5.3 SKILL.md

技能说明文件，约定信封结构与处理规则。

**输入信封**

```
{
  "type": "debug-chrome-req",
  "id": "<card_id>",
  "request": ...
}
```

**输出信封**

```
{
  "type": "debug-chrome-res",
  "id": "<card_id>",
  "result": ...
}
```

处理规则：按 `request` 完成页面调试任务，可调用本技能提供的页面探查工具；完成后以输出信封回复，`id` 原样保留。

---

## 六、调试扩展

### 6.1 定位

调试扩展承担：抽屉对话 UI、元素点选、页面探查、截图、命令执行。扩展代码位于 `skills/debug_chrome/extension/`。

### 6.2 配置与清单

- `backend_url` 指向工具服务。
- `manifest.json` 的 host_permissions 指向工具服务端口。

### 6.3 页面探查与消息推送

1. 调试扩展上线后，每 1 秒调用 `POST /api/ext/debug_chrome`（`action: "poll"`）取走命令。
2. 取到命令后在页面执行（选择器定位、快照采集），或在抽屉内展示推送文字。
3. 经 `POST /api/ext/debug_chrome`（`action: "result"`）回传结果。
4. 下线即停止轮询。

### 6.4 抽屉对话

1. 用户输入需求并附带已选元素（html、style、元素信息）。
2. 组装为 `POST /api/cards` 请求，携带信封类型 `debug-chrome-req`，挂起等待。
3. 工具服务完成卡片渲染、倒计时、自动发网页 AI，并按卡片 `id` 捕获输出信封结果。
4. 请求返回后，结果作为回复展示在抽屉对话区。

---

## 七、执行链路

### 7.1 外部卡片

| 步骤 | 动作 |
|---|---|
| 1 | 调试扩展抽屉发出 `POST /api/cards`，请求挂起 |
| 2 | 工具服务创建卡片（生成 `id`、记录信封类型），经心跳推给镜像插件 |
| 3 | 镜像插件在右侧对话列表按时序渲染外部卡片 |
| 4 | 倒计时结束，卡片内容按输入信封封装（`type`、`id`、`request`）自动发送到网页 AI |
| 5 | 网页 AI 首次处理时读取 SKILL.md，按需调用元素探查、文件读写等工具，逐步完成需求 |
| 6 | 网页 AI 输出带该 `id` 的输出信封结构 |
| 7 | 镜像插件检索到该结构，经 `POST /api/cards/<id>/reply` 回填工具服务 |
| 8 | 挂起的 `POST /api/cards` 返回最终结果给调试扩展抽屉 |

超时未回填：工具服务置 `timeout`，请求返回超时错误。

### 7.2 元素探查与消息推送

| 步骤 | 动作 |
|---|---|
| 1 | 网页 AI 输出 `get_element_style` / `get_page_snapshot` / `push_message` 调用代码块 |
| 2 | 镜像插件渲染为工具卡片 |
| 3 | 卡片执行调用 `POST /tool`，工具服务识别为外部工具，请求挂起 |
| 4 | 调试扩展轮询 `POST /api/ext/debug_chrome`（`action: "poll"`）取走命令 |
| 5 | 调试扩展在页面执行，经 `POST /api/ext/debug_chrome`（`action: "result"`）回传结果 |
| 6 | 工具服务放行 `POST /tool`，返回结果给卡片 |
| 7 | 卡片显示结果并自动回传给网页 AI |

---

## 八、文件清单

**工具服务**

- `flask_server/card_bus.py`
- `flask_server/routes_cards.py`
- `flask_server/external_tools.py`
- `flask_server/routes_ext.py`
- `flask_server/custom_tools.py`
- `flask_server/prompt_sections.py`
- `flask_server/server.py`
- `extend/content.js`
- `extend/dialog/app.js`
- `extend/dialog/style.css`

**调试扩展**

- `skills/debug_chrome/tool.json`
- `skills/debug_chrome/SKILL.md`
- `skills/debug_chrome/README.md`
- `skills/debug_chrome/extension/manifest.json`
- `skills/debug_chrome/extension/service_worker.js`
- `skills/debug_chrome/extension/vendor/`
- `skills/debug_chrome/extension/content/`
- `skills/debug_chrome/extension/drawer/`

---

## 九、实施阶段

1. 卡片总线与 `POST /api/cards`，服务入口开启多线程。
2. 外部工具与提供方机制，自定义工具加载支持 `provider`、`prompt`、`executor`。
3. 技能说明段落收集与 `GET /prompt_sections`。
4. 镜像插件外部卡片渲染、信封封装与按 `id` 捕获回填、技能说明注入。
5. `skills/debug_chrome/` 落位，调试扩展接入工具服务、轮询执行、抽屉对接。
6. 联调、超时与并发边界、文档。

---

## 十、参数约定

| 项 | 取值 |
|---|---|
| 外部卡片等待上限 | 120 秒 |
| 调试扩展轮询节奏 | 1 秒一次，上线即启、下线即停 |
| 提供方在线判定 | 3 秒内有 `poll` |
| 信封类型 | 输入 `debug-chrome-req`，输出 `debug-chrome-res` |
| 结果归属标识 | 卡片 `id` |
| 技能说明注入位置 | System Prompt 最末尾 |
| 技能说明生效条件 | 该技能下有工具上线 |
| 卡片视觉 | 外部卡片与工具卡片共用渲染与状态机，以 `source` 区分来源 |

---

## 十一、边界

1. 卡片结果以带卡片 `id` 的输出信封为准，并发卡片按 `id` 配对。
2. 每个挂起请求占用一个服务线程，设定并发上限。
3. 调试扩展命令执行异常由工具服务捕获并回传错误。
4. 超时统一返回 `TIMEOUT`，卡片状态置 `timeout`。
5. 信封可从代码块或普通文本块中提取，两者同等对待。
