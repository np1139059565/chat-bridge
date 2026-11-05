# 文档索引

本目录分两层：根目录放**当前有效**的规范与说明，`archive/` 放**过程记录**。

## 根目录：当前有效

按阅读顺序排列。改动代码前，先看与你相关的部分。

| 文档 | 性质 | 什么时候读 |
|---|---|---|
| `architecture.md` | 架构总览 | 第一次接触工程、想搞清整体结构时；其第二节说明定位与安全边界，做走查或评审前先读 |
| `development-guide.md` | 开发指南 | 上手开发、运行调试、提交前 |
| `api-reference.md` | 接口清单 | 调用或新增 HTTP 接口时 |
| `limits-reference.md` | 常量一览 | 调整上限、超时、阈值时 |
| `command-tool-isolation.md` | 强制规范 | 改动「指令 / 工具 / 卡片回传」相关代码前**必读** |
| `external-card.md` / `external-tool.md` / `external-skill.md` / `external-command.md` | 规范 | 涉及外部卡片、外部工具、技能、指令扩展时 |
| `remote-bridge-guide.md` | 使用说明 | 配置或使用 QQ 远程桥接时（面向使用者） |
| `remote-bridge-plan.md` | 设计方案 | 想了解远程桥接的设计取舍与实现路径时 |
| `wecom-protocol.md` | 协议记录 | 改动企业微信长连接收发时；含已确认与待真机验证的部分 |
| `channel-genericization.md` | 改造原则 | 新增通道、改动推送链路前；其第五节是各通道必须遵守的等价原则 |
| `dialog-parts-split-progress.md` | 分片清单 | 改动抽屉分片时；含当前分片职责表、行数与加载顺序 |
| `test-coverage-tracker.md` | 覆盖追踪 | 补测试前，查哪些模块仍无覆盖、哪些属假覆盖 |
| `pending-tasks.md` | 待办 | 想知道当前还有哪些未处理项、各自卡在哪。**结构质量与测试覆盖只在本文登记去向，详细数字见各自追踪文档** |
| `quality-debt-tracker.md` | 存量追踪 | 清理结构质量欠账时；**存量数字以本文为准**，基线文件 `scripts/quality_baseline.json` |
| `card-state-issue-tracker.md` | 故障追踪 | 卡片状态类问题复现时，查历史根因与验证方法 |

## archive/：过程记录

这些文档记录的是**某一轮工作当时**的清单、进度与计划。它们描述的是「当时做过什么」，不是「现在应该怎样」，因此不再随代码更新。

| 文档 | 记录内容 |
|---|---|
| `refactor-plan.md` | 一轮重构的执行计划与批次记录 |
| `前端测试补充进度.md` | 前端测试覆盖补充那一轮的清单与进度 |
| `debug_chrome改造进度.md` | 调试扩展改造那一轮的清单与进度 |
| `wecom-refactor-plan.md` | 企业微信通道重构那一轮的问题清单与改造步骤（核心原则已迁入 `channel-genericization.md`） |
| `code-review-report.md` | 代码走查那一轮的结论与修复记录（待办项已并入 `pending-tasks.md`） |
| `memory-system-review.md` | 记忆系统走查那一轮的问题清单与边界结论 |
| `让AI从“应声虫”变成敢于反驳你的思考伙伴.md` | 提示词模板合集，与工程代码无关；核心内容已落地为规则 `ANTI-FLATTERY_PROTOCOL` |

需要查「某个改动为什么这么做」时，归档文档是线索；判断「现在该怎么做」时，以根目录文档与代码为准。
