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
│   ├── server.py            # 入口：路由、工具表、热重载、配置读写、错误分类
│   ├── tools_impl.py        # 内置工具实现（可热重载）
│   ├── custom_tools.py      # 标准 skill 的 tool.json 解析 / 安装 / 子进程执行
│   ├── external_tools.py    # 外部工具提供方注册表：队列、心跳、转发与等待
│   ├── card_bus.py          # 卡片总线：登记 / 投递 / 回填 / 超时
│   ├── routes_cards.py      # /api/cards 系列（外部卡片）
│   ├── routes_ext.py        # /api/ext/<provider>（提供方通道）
│   ├── rules.py             # 规则（rules/*.md）与优先级
│   ├── prompt_sections.py   # 技能说明段落收集
│   ├── config.yaml          # 配置唯一来源
│   └── custom_tools.yaml    # 已安装自定义工具清单（自动维护）
├── extend/                  # 镜像插件（Chrome MV3）
│   ├── manifest.json
│   ├── background.js        # 工具栏图标切换抽屉显隐
│   ├── content.js           # 注入 iframe；抓取网页对话；站点规则；自动回传
│   ├── dialog/              # 抽屉页面
│   │   ├── dialog.html
│   │   ├── app.js           # 抽屉逻辑（Vue3 渲染函数）
│   │   └── style.css        # 抽屉样式
│   └── lib/vue.global.prod.js
├── skills/                  # 标准 skill（自定义工具来源）
│   └── debug_chrome/        # 页面调试扩展
│       ├── tool.json        # 工具声明（provider / prompt / tools）
│       ├── SKILL.md         # 技能说明（信封结构与处理规则）
│       ├── README.md
│       └── extension/       # 调试扩展代码（content/ + drawer/）
├── rules/                   # 用户规则（*.md）+ _meta.json（优先级）
└── docs/                    # 文档
```

---

## 三、两类卡片（核心概念）

系统里所有「可执行 / 可投递」的东西都抽象成**卡片**，分两类：

### 1. 工具卡片（tool card）

- 来源：网页 AI 在回答里输出的 `bridge-chat-call` 代码块，被 `extend/content.js` 抓取、`app.js` 解析。
- 执行：点击执行 → `POST /tool` → 工具服务执行内置/自定义/外部工具 → 结果回填 → 自动回传网页 AI。
- 存储：`conv.cardMap[id]`，按会话隔离、可持久化、可在「历史卡片管理」中查看。

### 2. 外部卡片（external card）

- 来源：外部提供方（如调试扩展抽屉）经 `POST /api/cards` 创建，被镜像插件轮询 `GET /api/cards/pending` 取走。
- 执行：镜像插件把卡片内容封装成信封，自动发送到网页 AI；**发送即结束**，不等 AI 回传结果。
- 存储：`conv.externalCards`（数组），按会话隔离、可持久化、可在「历史卡片管理」中查看。

> 两类卡片的差异清单见 `docs/external-card-vs-tool-card.md`。

---

## 四、数据流

### 4.1 工具调用（网页 AI → 本地工具）

```
网页 AI 输出 ```tool 代码块
  → content.js 抓取对话（含代码块）→ postMessage 给 iframe
  → app.js 解析为工具卡片（assistant 消息里的 bridge-chat-call）
  → 执行：POST /tool {tool, parameters}
      ├─ 内置工具：tools_impl.DISPATCH[name]
      ├─ 自定义工具 executor=script：custom_tools.run() 子进程
      └─ 自定义工具 executor=external：external_tools.hub.dispatch()
            → 命令入提供方队列 → 提供方 poll 取走 → 执行 → result 回传 → 放行
  → 结果回填卡片 → 自动回传网页 AI（auto_send）
```

### 4.2 外部卡片（调试扩展 → 网页 AI）

```
调试扩展抽屉 POST /api/cards（挂起）
  → card_bus 登记卡片
  → 镜像插件 GET /api/cards/pending 取走
  → 抽屉内渲染外部卡片（与文字消息共用统一时间戳 _ts，统一排序）
  → 倒计时后 auto_send 信封 {type,request} 到网页 AI（不携带 id）
  → 立即 POST /api/cards/<id>/reply 回确认（发送即结束）
  → 挂起的 POST /api/cards 立即返回
  → 后续进展由网页 AI 用 push_message 主动推送
```

### 4.3 网页对话镜像

```
content.js 按站点规则抓取消息 → sendPage() → postMessage('page_blocks')
  → app.js ingestMessages() → 渲染镜像 + 生成卡片
```

---

## 五、关键约定

- **配置唯一来源**：`flask_server/config.yaml`，插件不持久化配置到浏览器（除面板挂靠侧、会话存档）。
- **参数查询先行**：AI 调用工具前应先 `get_tool_params` 核对参数名（不同工具参数名不统一）。
- **路径约定**：`read_file` 只接受绝对路径（不做相对工程根的隐式解析）；skill 文档统一用 `read_skill`（`skill` + skill 内相对 `file`）读取。
- **单次一个工具块**：AI 每次回复只输出一个 ```tool 块。
- **错误分类**：工具失败返回 `origin`（parameter / environment / tool_internal）+ 完整堆栈，供 AI 判断改参数还是改代码。
- **自愈**：`read_tool_source` + `hot_reload_fix` 可改 `tools_impl.py` 并热重载，失败自动回滚。
- **规则按需读取**：`list_rules` / `read_rule`，优先级 always / on-demand / off。
- **站点隔离**：镜像插件数据按 hostname 前缀存储（`aiMirrorConv_<site>__<conv>`）。

---

## 六、相关文档

- `docs/api-reference.md`：HTTP 接口清单。
- `docs/development-guide.md`：运行、调试、常见任务、约定。
- `docs/external-card-vs-tool-card.md`：两类卡片差异对照。
- `docs/debug_chrome-plugin-plan.md`：调试能力挂靠方案（设计稿）。
