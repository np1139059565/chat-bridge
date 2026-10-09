# 上限与阈值一览

本文件汇总后端与前端的关键上限、超时、阈值常量，便于核对与调整。

> 说明：数值以代码为准。改动任一常量后，请同步本表。

## 一、缓存与容量上限（防内存 / 磁盘无限增长）

| 上限 | 值 | 位置 | 含义 |
|---|---|---|---|
| `MAX_CARDS` | 200 | `core/card_bus.py` | 卡片总线最多保留的卡片数，超限优先裁剪已确认展示的最旧卡片 |
| `MAX_MESSAGES` | 500 | `web_bridge/web_inbox.py` | 网页收件箱最多保留的消息条数，超限丢最旧 |
| `MAX_AUDIO_FILES` | 100 | `web_bridge/web_mirror.py` | 网页音频目录最多保留的文件数，合成后按修改时间回收更旧的 |
| `DEFAULT_QUEUE_MAX` | 10000 | `core/log_sink.py` | 异步日志队列容量，满时丢最旧 |
| `MAX_BATCH` | 100 | `web_bridge/web_clientlog.js` | 前端日志单批上限，超限立即冲刷 |
| `MAX_DOC_CHARS` | 200000 | `custom_tools/skill_docs.py` | 技能文档读取字符上限 |
| `MAX_PUSH_PER_REPORT` | 30 | `remote_bridge/message_router.py` | 单次上报最多推送的消息数 |
| `DEFAULT_MAX_JSON_CHARS` | 100000 | `tools/tool_helpers.py` | 工具结果 JSON 体积上限（可配置覆盖） |

## 二、超时（秒）

| 超时 | 值 | 位置 | 含义 |
|---|---|---|---|
| `RUN_COMMAND_TIMEOUT` | 45 | `tools/run_command_impl.py` | run_command 单次执行超时 |
| `BUILTIN_TOOL_TIMEOUT` | 60 | `routes/tools.py` | 内置工具执行的外层兜底超时 |
| `CUSTOM_TOOL_TIMEOUT` | 60 | `custom_tools/registry.py` | 自定义工具脚本单次执行超时 |
| `SYNTH_TIMEOUT` | 20 | `remote_bridge/voice_tts.py` | 语音合成单次超时 |
| `FORWARD_TIMEOUT` | 10.0 | `core/external_tools.py` | 外部工具调用等待提供方取走的保险丝 |
| 看门狗 dump 阈值 | 150 | `app.py` | 请求挂起超此值 dump 全部线程堆栈 |
| 看门狗 WARN 阈值 | 10 | `app.py` | 请求挂起超此值记 WARN |
| `_SLOW_MS` | 1000（毫秒） | `app.py` | 请求耗时超此值升级为 WARN |
| 前端轮询超时 | 6000（毫秒） | `web_bridge/web_page.js` | 单次拉消息请求超时，超时即中断 |

## 三、窗口与有效期

| 项 | 值 | 位置 | 含义 |
|---|---|---|---|
| `ONLINE_WINDOW` | 10.0 秒 | `core/external_tools.py` | 提供方在线判定窗口（仅指示灯，不参与执行） |
| `OPEN_WINDOW` | 15.0 秒 | `core/external_tools.py` | 「工具已打开」有效期 |
| `TARGET_HOLD` | 5.0 秒 | `core/external_tools.py` | 目标页独占命令的窗口 |
| `PENDING_TTL`（指令） | 60 秒 | `remote_bridge/command_dispatch.py` | 待回传指令的有效期 |
| `PENDING_TTL`（语音） | 600 秒 | `remote_bridge/voice_pending.py` | 待确认语音文字的有效期 |
| `WINDOW_SECONDS` | 3600 秒 | `remote_bridge/message_router.py` | 推送窗口记录时长 |
| `_sig` 签名缓存 | — | `core/memory_conversations.py` | 增量保存的内容签名（内存） |

## 四、并发与调度

| 项 | 值 | 位置 | 含义 |
|---|---|---|---|
| `_TOOL_POOL_MAX_WORKERS` | 64 | `routes/tools.py` | 执行内置工具的线程池容量 |
| `MAX_CONCURRENT_SYNTH` | 3 | `remote_bridge/voice_tts.py` | 语音合成最大并发数 |
| `DEFAULT_INTERVAL` | 1800 秒 | `core/memory_scheduler.py` | 后台维护（衰减/聚类/检查点）运行间隔 |
| `_COMMIT_BATCH` | 200 | `core/memory_decay.py` | 全量重算的分批提交粒度 |
| `maintenance_yield` | step=0.05 / max_wait=0.5 秒 | `core/ui_priority.py` | 后台维护给界面让路的等待步长与上限 |
| `SYNAPSE_MIN_INTERSECT` | 3 | `core/memory_events.py` | 建突触边的交集门槛 |
| `SYNAPSE_MIN_JACCARD` | 0.3 | `core/memory_events.py` | 建突触边的 Jaccard 门槛 |

## 五、前端轮询间隔（毫秒）

| 项 | 值 | 位置 |
|---|---|---|
| 网页拉消息轮询 | 2500 | `web_bridge/web_page.js` |
| 前端日志冲刷间隔 | 1000 | `web_bridge/web_clientlog.js` |
| 抽屉外部卡片轮询 | 5000 | `extend/dialog/parts/01_backend.js` |
| 抽屉桥接状态轮询 | 5000 | `extend/dialog/parts/01b_bridge.js` |

## 六、易混淆项（层级关系）

工具执行超时由内到外分三层，须保持「外层 > 内层」，否则正常慢命令会被外层误杀：

```
run_command 自身：45 秒（RUN_COMMAND_TIMEOUT）
  ↓ 须小于
内置工具兜底：60 秒（BUILTIN_TOOL_TIMEOUT）
  ↓ 须小于
看门狗 dump：150 秒（hang_seconds）
```
