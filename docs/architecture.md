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
chat-bridge/
├── flask_server/                 # 本地工具服务（Python / Flask）
│   ├── server.py                 # 兼容入口：委托 app.create_app()，保留 python server.py 启动方式
│   ├── app.py                    # 应用装配：create_app() / 蓝图注册 / CORS / 运行期初始化
│   ├── runtime.py                # 运行期全局状态中心：app / impl / TOOLS / DISPATCH / CONFIG
│   ├── paths.py                  # 路径基准与常量
│   ├── config/                   # 配置文件目录
│   │   ├── definition.yaml       # 全部定义，入库
│   │   └── runtime.yaml          # 全部运行时与密钥，不入库
│   ├── core/                     # 核心支撑（37 个模块，见下表）
│   ├── routes/                   # 各功能域蓝图（13 个，见下表）
│   ├── remote_bridge/            # 远程桥接（QQ ↔ 网页 AI，25 个模块，见下表）
│   ├── web_bridge/               # 网页版机器人（5 个模块，见下表）
│   ├── custom_tools/             # 标准 skill 的解析 / 注册 / 执行（包）
│   ├── tools/                    # 内置工具实现与元数据
│   ├── static/                   # 静态资源（记忆图谱页、anatomy 导出等）
│   ├── tests/                    # 后端测试
│   └── data/                     # 运行期数据（不入库）
├── extend/                       # 镜像插件（Chrome MV3）
│   ├── manifest.json
│   ├── background.js             # 工具栏图标切换抽屉显隐
│   ├── lib/                      # 公共前端模块（vue.global.prod.js / dom-utils.js）
│   ├── content/                  # 内容脚本（按序号加载）
│   │   ├── 00_state.js           # 命名空间、共享 state、站点规则 PROFILES、日志
│   │   ├── 01_panel.js           # 面板注入与外观、post 通道
│   │   ├── 02_blocks.js          # 代码块解析、消息构造、extractBlocks
│   │   ├── 03_bridge.js          # 会话/历史项识别、sendPage、粘贴发送
│   │   ├── 04_observer.js        # 观察器与生命周期
│   │   ├── 05_index.js           # 入口：消息监听、巡检、初始化
│   │   ├── 06_picker.js          # 元素选择器
│   │   └── injected_clipboard.js # 主世界剪贴板注入
│   └── dialog/                   # 抽屉页面
│       ├── dialog.html
│       ├── app.js                # 装配入口（createApp + 组件装配）
│       ├── parts/                # 抽屉逻辑分片（00_data ~ 09_skills）
│       └── styles/               # 样式分片（00_tokens ~ 05_narrow）
├── skills/                       # 标准 skill：anatomy / debug_chrome / json_tool
├── rules/                        # 用户规则（*.md）+ _meta.json（优先级）
├── scripts/                      # 质量与卫生检查脚本、Git 钩子
└── docs/                         # 文档
```

### 服务端子模块明细

**core/（核心支撑）**

| 文件 | 职责 |
|---|---|
| `config_store.py` / `config_file.py` | 主配置读写、分区合并 |
| `card_bus.py` | 卡片总线：统一登记外部卡片并投递给镜像插件 |
| `external_tools.py` | 外部工具提供方注册与转发（队列、心跳、等待） |
| `envelope.py` | 外部调用信封解析（共享） |
| `rules.py` / `rule_enforce.py` | 规则文件管理与可机械判定的程序化校验 |
| `prompt_sections.py` | 供 System Prompt 注入的技能说明段落与技能清单 |
| `memory_*.py` | 记忆系统，见下方「记忆系统」小节 |
| `app_log.py` / `log_sink.py` | 全局日志与落盘（按天分文件、异步写入） |
| `serial_worker.py` | 串行工作队列（共享） |
| `service_control.py` | 服务进程控制：重启与滚动重启 |
| `ui_priority.py` | 界面请求优先级（后台维护主动让路） |
| `screenshot_store.py` | 截图存盘统一入口 |
| `graph_data.py` | 记忆图谱图数据组装（纯函数） |
| `json_utils.py` / `yaml_utils.py` | JSON 安全反序列化 / YAML 标量原语 |
| `error_utils.py` / `responses.py` | 错误分类与定位 / 错误响应辅助 |
| `app_limits.py` | 数量上限的唯一来源 |

**routes/（功能域蓝图）**

| 文件 | 职责 |
|---|---|
| `tools.py` / `prompts.py` / `config_route.py` | `/tools`、`/tool`、`/prompt_sections`、`/`（首页）、`/config` |
| `custom_tools.py` / `rules.py` | `/custom_tools` 系列、`/rules` 系列 |
| `cards.py` / `ext.py` | `/api/cards` 系列（外部卡片）、`/api/ext/<provider>`（提供方通道） |
| `bridge.py` | 远程桥接上报接口 |
| `web.py` / `web_clientlog.py` | 网页版资源与前端日志 |
| `memory_graph.py` / `memory_graph_page.py` | 记忆图谱 HTTP 接口与图谱页面 |

**remote_bridge/（远程桥接：QQ ↔ 网页 AI）**

| 分组 | 文件 | 职责 |
|---|---|---|
| QQ 协议 | `qq_gateway.py` / `qq_client.py` / `qq_event_parse.py` / `qq_media.py` | 事件分发、机器人协议层、事件解析与下载、富媒体发送 |
| 消息 | `message_router.py` / `message_flow.py` / `message_parse.py` / `outbound.py` | 分流与推送、上报推送流程、解析与块文本组装、出站正文组装 |
| 语音 | `voice_tts.py` / `voice_voices.py` / `voice_cache.py` / `voice_mp3.py` | 多引擎合成、音色清单、成品缓存、WAV 转 MP3 |
| 语音（其他） | `pyttsx3_worker.py` / `voice_sapi_runner.py` / `voice_asr.py` / `voice_pending.py` / `message_voice.py` | 合成子进程与父进程调度、语音识别、待确认文字暂存、出向语音提取与推送 |
| 指令 | `command_registry.py` / `command_dispatch.py` / `command_external.py` / `command_panel.py` | 指令表与校验、抽屉命令下发、外部指令、QQ 指令执行 |
| 存储与日志 | `bridge_store.py` / `bridge_log.py` / `json_scan.py` | 配置与去重记账、异步日志、文本内 JSON 扫描 |
| 图片 | `message_images.py` | 网页消息内图片的推送 |

**web_bridge/（网页版机器人）**

| 文件 | 职责 |
|---|---|
| `web_inbox.py` / `web_inbox_store.py` | 对话收件箱存储层与持久化层 |
| `web_mirror.py` | 出站镜像 |
| `audio_prune.py` | 网页音频目录回收 |

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
| `memory_notes.py` | 笔记层（每日记忆 journal / 错题本 notebook） |
| `memory_db_diag.py` | 数据库诊断层（连接耗时、表容量、异常归因） |
| `memory_scheduler.py` | 后台调度（衰减与事件聚类的周期任务） |
| `memory_solidify.py` | 固化层（升为规则文件 / 写入错题本） |
| `memory_wal.py` | 记忆库 WAL 维护 |
| `memory_text.py` | 消息块文本抽取（共享） |
| `routes/memory_graph.py` / `memory_graph_page.py` | 记忆系统 HTTP 接口与图谱页面 |

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

### 4.4 语音链路

语音是网页对话镜像与 QQ 推送共用的一条出向通道，位于 `flask_server/remote_bridge/`。

### 合成：多引擎、子进程隔离

| 环节 | 模块 | 说明 |
|---|---|---|
| 引擎选择与调度 | `voice_tts.py` | 按配置的 fallback 顺序选引擎；`pyttsx3` / `piper` / `sapi` / `edge_tts` 四选一，统一输出 MP3 |
| pyttsx3 隔离 | `pyttsx3_worker.py` | 独立子进程运行，不随主进程生命周期退出。Windows 的 SAPI 是单例资源，放主进程会占死，故隔离 |
| sapi 引擎 | `voice_sapi_runner.py` | 用 PowerShell 调 Windows 自带 System.Speech 合成 WAV，再转 MP3。不依赖任何第三方包，网络受限时仍是可用引擎 |
| 音色清单 | `voice_voices.py` | 三类引擎音色来源不同：pyttsx3 读系统语音、piper 读本地模型文件、edge_tts 取内置清单 |
| 编码 | `voice_mp3.py` | WAV 转 MP3 |
| 成品缓存 | `voice_cache.py` | 按文本哈希复用，避免同一句话重复合成 |

### 出向：从消息到推送

```
上报消息到达
  → message_voice.py 从消息中提取语音文本（优先取语音朗读块，缺省回退正文）
  → voice_cache 命中则直接复用，未命中走 voice_tts 合成（受 MAX_CONCURRENT_SYNTH 并发闸门约束）
  → message_flow.postsynth_and_push_voice() 推送成品
```

关键限制见 `docs/limits-reference.md`：`SYNTH_TIMEOUT`（单次合成超时）、`MAX_CONCURRENT_SYNTH`（最大并发合成数）。

### 入向：QQ 语音识别

`voice_asr.py` 负责 SILK 解码与 vosk 转文字；识别结果经 `voice_pending.py` 暂存为待确认文本，由用户在设置页确认后再进入正常对话流。

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
- `docs/limits-reference.md`：各项数量上限与超时常量的出处。
- `docs/memory-system-review.md`：记忆系统走查结论。
- `docs/archive/refactor-plan.md`：代码走查与重构执行计划（含目录规划与批次记录），已完成归档。
- `docs/remote-bridge-plan.md`：远程桥接方案（QQ ↔ 网页 AI），含架构选型、消息分流、推送通道与落地顺序。
- `docs/remote-bridge-guide.md`：远程桥接使用说明（面向使用者），含配置步骤、指令、常见问题与当前限制。
