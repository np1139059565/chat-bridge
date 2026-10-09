# 架构总览（chat-bridge）

本文档面向「下一个接手的人 / AI」，目标是不必逐个扫描源码即可理解工程结构、数据流与关键约定。

---

## 一、这是什么

一套本地「网页 AI ↔ 本地工具」的桥接系统，由三部分组成：

| 组成 | 位置 | 职责 |
|---|---|---|
| 本地工具服务 | `flask_server/` | 提供 HTTP 接口；执行本地工具；转发外部工具；承载卡片总线 |
| 镜像插件 | `extend/` | Chrome MV3 扩展；悬浮抽屉；镜像网页对话；渲染并执行工具卡片与外部卡片 |
| 技能 / 调试扩展 | `skills/` | 以标准 skill 形式扩展工具；`skills/debug_chrome/` 是页面调试扩展 |

---

## 二、目录职责

```
chat-bridge-main/
├── flask_server/            # 本地工具服务（Python / Flask）
│   ├── server.py            # 兼容入口：委托 app.create_app()，保留 python server.py 启动方式
│   ├── app.py               # 应用装配：create_app() / 蓝图注册 / CORS / 运行期初始化
│   ├── runtime.py           # 运行期全局状态中心：app / impl / TOOLS / DISPATCH / CONFIG
│   ├── config_store.py      # 配置读写与合并（definition.yaml + runtime.yaml）
│   ├── error_utils.py       # 错误分类与定位
│   ├── responses.py         # 错误响应辅助
│   ├── tool_helpers.py      # 工具通用辅助：参数校验、路径解析、体积控制
│   ├── tool_meta.py         # 内置工具元数据声明（描述 + 参数表）
│   ├── tools_impl.py        # 内置工具实现
│   ├── yaml_utils.py        # YAML 标量原语（合并原两套实现）
│   ├── routes/              # 各功能域蓝图
│   │   ├── tools.py         # /tools、/tool
│   │   ├── prompts.py       # /prompt_sections、/（首页）
│   │   ├── config_route.py  # /config
│   │   ├── custom_tools.py  # /custom_tools 系列
│   │   ├── rules.py         # /rules 系列
│   │   ├── cards.py         # /api/cards 系列（外部卡片）
│   │   └── ext.py           # /api/ext/<provider>（提供方通道）
│   ├── custom_tools/        # 标准 skill 的解析 / 注册 / 执行（包）
│   │   ├── paths.py         # 路径基准与常量
│   │   ├── loader.py        # custom_tools.yaml 与 tool.json 解析、命令拼装
│   │   ├── registry.py      # 注册表读写、安装/删除/更新、本地执行
│   │   ├── meta.py          # 对外视图（provider 分组、说明段落、元数据）
│   │   ├── scan.py          # 目录扫描
│   │   └── skill_docs.py    # 技能内文档（SKILL.md 等）的读取与写回
│   ├── external_tools.py    # 外部工具提供方注册表：队列、心跳、转发与等待
│   ├── card_bus.py          # 卡片总线：登记 / 投递 / 确认已展示
│   ├── rules.py             # 规则（rules/*.md）与优先级
│   ├── prompt_sections.py   # 技能说明与技能清单收集
│   ├── definition.yaml      # 全部定义，入库
│   └── runtime.yaml         # 全部运行时与密钥，不入库
├── extend/                  # 镜像插件（Chrome MV3）
│   ├── manifest.json
│   ├── background.js        # 工具栏图标切换抽屉显隐
│   ├── lib/                 # 公共前端模块
│   │   ├── vue.global.prod.js
│   │   └── dom-utils.js     # debounce / hashStr / textOf
│   ├── content/             # 内容脚本（按序号加载的分片）
│   │   ├── 00_state.js      # 命名空间 A、共享 state、站点规则 PROFILES、日志
│   │   ├── 01_panel.js      # 面板注入与外观、post 通道
│   │   ├── 02_blocks.js     # 代码块解析、消息构造、extractBlocks
│   │   ├── 03_bridge.js     # 会话/历史项识别、sendPage、粘贴发送
│   │   ├── 04_observer.js   # 观察器与生命周期
│   │   └── 05_index.js      # 入口：消息监听、巡检、初始化
│   └── dialog/              # 抽屉页面
│       ├── dialog.html
│       ├── app.js           # 装配入口（createApp + 组件装配）
│       ├── parts/           # 抽屉逻辑分片（00_data ~ 09_skills，含 07_render）
│       └── styles/          # 样式分片（00_tokens ~ 05_narrow）
├── skills/                  # 标准 skill（自定义工具来源）
│   └── debug_chrome/        # 页面调试扩展
│       ├── tool.json        # 工具声明（provider / prompt / tools）
│       ├── SKILL.md         # 技能说明（信封结构与处理规则）
│       ├── README.md
│       └── extension/       # 调试扩展代码
│           ├── manifest.json
│           ├── service_worker.js
│           ├── drawer.html
│           ├── content/     # 内容脚本（00_namespace ~ 08_injected_main）
│           ├── drawer/      # 抽屉脚本分片（00_config ~ 05_main）
│           ├── drawer-styles/  # 抽屉样式分片（00_tokens ~ 06_focus）
│           ├── shared/      # 共享模块（url-utils.js）
│           └── vendor/      # 前端依赖（vue.global.prod.js）
├── rules/                   # 用户规则（*.md）+ _meta.json（优先级）
└── docs/                    # 文档
```

### 记忆系统（flask_server/core/memory_*.py）

结构化记忆系统，把「消息树 + 蒸馏精华 + 事件关联」落进单个 SQLite 文件，
启动加载进内存、经 HTTP 接口读写。详见 `docs/记忆机制改进方案.md`。

| 模块 | 职责 |
|---|---|
| `memory_db.py` | 连接管理、六张表、向量暴力余弦 |
| `memory_nodes.py` | 节点表读写（含蒸馏字段） |
| `memory_edges.py` | 边表读写（树边 / 分支边 / 突触边） |
| `memory_cards.py` | 卡片表读写（工具执行状态） |
| `memory_conversations.py` | 会话整体存取（前端走后端查询） |
| `memory_keywords.py` | 关键词提取（规则 + 可插拔 LLM 精筛） |
| `memory_distill.py` | 异步蒸馏（按来源提精华） |
| `memory_decay.py` | 强度计算、自动升降级、边衰减 |
| `memory_events.py` | 事件聚类、突触建边、三条护栏 |
| `memory_search.py` | 双接口防幻觉检索 |
| `memory_loader.py` | 启动加载进内存 |
| `routes/memory_graph.py` | 记忆系统 HTTP 接口（含 `/memory-graph` 图谱页） |

数据落 `flask_server/data/memory/memory.db`（不入库）；图谱页在 `flask_server/static/memory_graph.html`（入库）。


---

## 三、两类卡片（核心概念）

系统里所有「可执行 / 可投递」的东西都抽象成**卡片**，分两类：

### 1. 工具卡片（tool card）

- 来源：网页 AI 在回答里输出的 `bridge-chat-call` 代码块，被 `extend/content/02_blocks.js` 抓取、`extend/dialog/parts/` 解析。
- 执行：点击执行 → `POST /tool` → 工具服务执行内置/自定义/外部工具 → 结果回填 → 自动回传网页 AI。
- 存储：挂在消息树节点的 `node.cards`（按代码块 id 索引），由 `cardMap` computed 聚合查看；按会话隔离、可持久化。

### 2. 外部卡片（external card）

- 来源：外部提供方（如调试扩展抽屉）经 `POST /api/cards` 创建，被镜像插件轮询 `GET /api/cards/pending` 取走。
- 执行：镜像插件把卡片内容封装成信封，自动发送到网页 AI；**发送即结束**，不等 AI 回传结果。
- 存储：`conv.externalCards`（数组），按会话隔离、可持久化、可在「历史卡片管理」中查看。

> 两类卡片的核心差异：工具卡片由网页 AI 触发、需回传结果；外部卡片由外部提供方登记、发送即结束。

---

## 四、数据流

### 4.1 工具调用（网页 AI → 本地工具）

```
网页 AI 输出工具调用 JSON 代码块
  → content/02_blocks.js 抓取对话（含代码块）→ postMessage 给 iframe
  → dialog/parts/05_messages.js 解析为工具卡片（assistant 消息里的 bridge-chat-call）
  → 执行：POST /tool {tool, parameters}
      ├─ 内置工具：tools_impl.DISPATCH[name]
      ├─ 自定义工具 executor=script：custom_tools.run() 子进程
      └─ 自定义工具 executor=external：external_tools.hub.dispatch()
            → 命令一律入提供方队列（不看在线状态）→ 提供方 poll 取走 → 执行 → result 回传 → 放行
  → 结果回填卡片 → 自动回传网页 AI（auto_send）
```

### 4.2 外部卡片（调试扩展 → 网页 AI）

```
调试扩展抽屉 POST /api/cards（挂起）
  → card_bus 登记卡片
  → 镜像插件 GET /api/cards/pending 取走
  → 抽屉内渲染外部卡片（按 anchorKey 锚点插入到对应消息之后）
  → 倒计时后 auto_send 信封 {type,request} 到网页 AI（不携带 id）
  → 卡片入列即 POST /api/cards/<id>/delivered 确认已展示（发送即结束）
  → 挂起的 POST /api/cards 立即返回
  → 后续进展由网页 AI 用 push_message 主动推送
```

### 4.3 网页对话镜像

```
content/04_observer.js 触发抓取、content/03_bridge.js sendPage() → postMessage('page_blocks')
  → dialog/parts/05_messages.js ingestMessages() → 渲染镜像 + 生成卡片
```

---

## 五、关键约定

- **配置来源**：`flask_server/config/definition.yaml`（定义，入库）与 `runtime.yaml`（运行时与密钥，不入库）；插件不持久化配置到浏览器（除面板挂靠侧、会话存档）。
- **参数查询先行**：AI 调用工具前应先 `get_tool_params` 核对参数名（不同工具参数名不统一）。
- **路径约定**：文件类工具口径统一——绝对路径原样使用，相对路径以工程根为基准解析；skill 文档统一用 `list_skills` / `read_skill`（`skill` + skill 内相对 `file`）读取。
- **单次一个工具块**：AI 每次回复只输出一个 JSON 代码块。
- **错误分类**：工具失败返回 `origin`（parameter / environment / tool_internal）+ 完整堆栈，供 AI 判断是改参数、改路径，还是反馈工具实现问题。
- **外部工具不因离线被拒**：在线状态只用于界面指示灯；调用一律入队等待提供方取走执行，等待上限内未取走才报超时。
- **规则按需读取**：`list_rules` / `read_rule`，优先级 always / on-demand / off。
- **技能按需读取**：`list_skills` / `read_skill`，先列可用技能再读取其文档。
- **站点隔离**：镜像插件数据按 hostname 前缀存储（`aiMirrorConv_<site>__<conv>`）。

---

## 六、相关文档

- `docs/api-reference.md`：HTTP 接口清单。
- `docs/development-guide.md`：运行、调试、常见任务、约定。
- `docs/refactor-plan.md`：代码走查与重构执行计划（含目录规划与批次记录）。
- `docs/remote-bridge-plan.md`：远程桥接方案（QQ ↔ 网页 AI），含架构选型、消息分流、推送通道与落地顺序。
- `docs/remote-bridge-guide.md`：远程桥接使用说明（面向使用者），含配置步骤、指令、常见问题与当前限制。
