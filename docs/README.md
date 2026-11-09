# 文档索引

本目录分两层：根目录放**当前有效**的规范与说明，`archive/` 放**过程记录**。

## 根目录：当前有效

按阅读顺序排列。改动代码前，先看与你相关的部分。

### 架构与开发

| 文档 | 性质 | 什么时候读 |
|---|---|---|
| `architecture.md` | 架构总览 | 第一次接触工程、想搞清整体结构时；其第二节说明定位与安全边界，做走查或评审前先读 |
| `development-guide.md` | 开发指南 | 上手开发、运行调试、提交前 |
| `api-reference.md` | 接口清单 | 调用或新增 HTTP 接口时 |
| `limits-reference.md` | 常量一览 | 调整上限、超时、阈值时 |
| `dialog-parts.md` | 分片职责表 | 改动抽屉分片时；含当前分片职责表、加载顺序与方法挂载约定 |

### 强制规范

| 文档 | 性质 | 什么时候读 |
|---|---|---|
| `command-tool-isolation.md` | 强制规范 | 改动「指令 / 工具 / 卡片回传」相关代码前**必读** |
| `external-card.md` / `external-tool.md` / `external-skill.md` / `external-command.md` | 规范 | 涉及外部卡片、外部工具、技能、指令扩展时 |
| `channel-genericization.md` | 改造原则 | 新增通道、改动推送链路前；其第五节是各通道必须遵守的等价原则 |

### 当前进行中的工程

| 文档 | 性质 | 什么时候读 |
|---|---|---|
| `split-mirror-and-tools-service.md` | **拆分规格（唯一真源）** | 翻译员与工具服务拆分期间，一切取舍以此为准 |
| `tool-schema-migration.md` | 迁移进度 | 改工具参数声明时；逐项勾选，全部完成才算阶段结束 |
| `config-isolation-and-cache-design.md` | 设计方案 | 配置按站点隔离与缓存的 v3 方案，实施前读 |
| `multi-site-isolation.md` | 机制说明 | 多网页 AI 并存时的页面绑定与站点隔离 |

### 待办与追踪

| 文档 | 性质 | 什么时候读 |
|---|---|---|
| `pending-tasks.md` | 待办 | 尚未开工的问题与工作项 |
| `pending-verify.md` | 待验证 | 代码已改完、只缺真机跑一遍的条目 |
| `pending-blueprint.md` | 施工蓝图 | 批次级实施蓝图，含具体锚点与步骤 |
| `test-coverage-tracker.md` | 覆盖追踪 | 补测试前，查哪些模块仍无覆盖、哪些属假覆盖 |
| `quality-debt-tracker.md` | 存量追踪 | 清理结构质量欠账时；**存量数字以本文为准** |

### 协作与分工

| 文档 | 性质 | 什么时候读 |
|---|---|---|
| `work-board.md` | 总调度看板 | 查看三个执行方的实时状态、依赖关系与审核队列 |
| `work-dispatcher.md` | 分发方职责 | 接手需求分发角色时；含审核清单与交接说明 |
| `work-ai-a.md` / `work-ai-b.md` / `work-ai-c.md` | 执行方任务卡 | 各执行方开工前读自己的那份 |

### 通道与协议

| 文档 | 性质 | 什么时候读 |
|---|---|---|
| `remote-bridge-guide.md` | 使用说明 | 配置或使用 QQ 远程桥接时（面向使用者） |
| `wecom-protocol.md` | 协议记录 | 改动企业微信长连接收发时 |

## archive/：过程记录

这些文档记录的是**某一轮工作当时**的清单、进度与计划。它们描述的是「当时做过什么」，不是「现在应该怎样」，因此不再随代码更新。

| 文档 | 记录内容 |
|---|---|
| `PROGRESS.md` | 千问页面输入适配器那一轮的调试进度与结论 |
| `card-state-issue-tracker.md` | 卡片状态类故障的追踪与结案记录 |
| `incident-2026-11-08-glm-paste-guard.md` | 一次粘贴守卫相关事故的现场记录与结论 |
| `服务不可用.html` | 风控形态排查时抓取的页面快照 |
| `pending-tasks-closed.md` | 已结案待办条目存档 |
| `dialog-parts-split-history.md` | 抽屉分片拆分过程与期间故障记录 |

需要查「某个改动为什么这么做」时，归档文档是线索；判断「现在该怎么做」时，以根目录文档与代码为准。
