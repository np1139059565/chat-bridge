# 测试覆盖追踪清单

> 用途：逐个模块追踪测试覆盖状态，防止「看起来有测试、实际没测到」的盲区。
> 维护：每补一个模块的测试，把对应行的 `[ ]` 改为 `[x]`，并在末尾记录提交号。
> 判定标准见本文「怎样才算覆盖」一节——**被测试文件 import 不等于被覆盖**。

---

## 一、怎样才算覆盖

一个模块算「已覆盖」，必须同时满足三条：

1. **被真实调用**：测试里直接调用被测函数，而不是整体替换掉它（`mock` 掉被测对象本身等于没测）；
2. **覆盖主路径**：至少一条成功路径走通，断言产出正确（返回值 / 文件 / 数据库状态）；
3. **覆盖失败路径**：至少一条异常或边界路径，断言错误被正确处理。

> 反例（本项目真实发生）：语音合成本有 13 个测试，但全部把 `_dispatch` 替换成假函数，只验证「选哪个引擎」，从未进入真实合成路径。结果一个返回值解包错误导致合成 100% 失败，测试全绿。

---

## 二、总体状况

盘点口径：`flask_server/` 下 124 个业务模块（不含 `__init__.py`），51 个测试文件。

统计命令：`cd flask_server && python -m pytest tests -q --cov --cov-report=term`，
口径由 `.coveragerc` 定义（只算业务源码，排除 `tests/` 自身与运行时产物，启用分支覆盖）。

| 目录 | 模块数 | 零覆盖 | 占比 | 未覆盖单元 | 优先级 |
|---|---|---|---|---|---|
| `remote_bridge/` | 40 | 5 | 13% | 3549 | **P0** |
| `routes/` | 16 | 9 | 56% | 1415 | P2 |
| `core/` | 39 | 0 | 0% | 1058 | P2 |
| `tools/` | 13 | 0 | 0% | 591 | P1 |
| `custom_tools/` | 8 | 0 | 0% | 530 | P1 |
| `web_bridge/` | 4 | 0 | 0% | 486 | P1 |
| 根目录 | 4 | 2 | 50% | 258 | P3 |
| **合计** | **124** | **16** | **13%** | **7887** | |

整体覆盖率 **43.3%**（含分支）。零覆盖模块数已从 44 降到 16，但
`remote_bridge/` 与 `routes/` 的未覆盖行数占全项目近三分之二——零覆盖模块减少不等于覆盖面扩大，
这两处仍是主要缺口。

`tools/command_tasks.py` 与 `tools/proc_runner.py` 未被任何代码导入，覆盖率工具统计不到；
两者按业务模块计入分母，实测时需留意这一差异。

优先级依据：出错影响面 × 代码复杂度 × 是否在关键链路上。

---

## 三、P0：`remote_bridge/`（40 个模块，5 个零覆盖）

远程桥接是 QQ ↔ 网页 AI 的通道，一旦出错用户直接收不到消息。且本目录代码行数最多、分支最密。

### 3.1 语音链路（本次事故所在）

- [x] `voice_pyttsx3_runner.py` — 父进程侧调度：写文本、拉起子进程、超时处理、产物校验
- [ ] `pyttsx3_worker.py` — 子进程：读文本、初始化引擎、设音色语速、合成
- [ ] `voice_tts.py` — 三引擎分发（现仅测策略层，未测执行层，需补执行层用例）
- [ ] `voice_voices.py` — 音色清单列举
- [x] `voice_cache.py` — 成品缓存复用
- [x] `voice_pending.py` — 待确认语音文字暂存
- [ ] `voice_asr.py` — SILK 解码与语音识别

### 3.2 消息链路

- [x] `message_parse.py` — 消息解析与块文本组装
- [x] `message_voice.py` — 从消息提取语音文本
- [x] `message_images.py` — 消息内图片推送
- [x] `outbound.py` — 出站正文组装

### 3.3 QQ 协议

- [x] `qq_gateway.py` — 事件分发
- [ ] `qq_client.py` — 机器人协议层
- [x] `qq_event_parse.py` — 事件解析与下载
- [ ] `qq_media.py` — 富媒体发送

### 3.4 指令

- [x] `command_registry.py` — 指令表、别名、校验
- [x] `command_dispatch.py` — 抽屉命令下发
- [x] `command_external.py` — 外部指令处理
- [x] `command_panel.py` — QQ 指令执行

### 3.5 存储与工具

- [x] `bridge_store.py` — 配置分区读写与去重记账
- [x] `bridge_log.py` — 异步日志落盘
- [x] `json_scan.py` — 文本内 JSON 扫描

---

## 四、P1：`custom_tools/` / `tools/` / `web_bridge/`

### 4.1 `custom_tools/`（8 个模块，0 个零覆盖）

- [x] `loader.py` — 技能解析、命令拼装
- [x] `registry.py` — 注册表读写、安装删除
- [x] `meta.py` — 对外视图组装
- [x] `scan.py` — 目录扫描
- [x] `skill_docs.py` — 技能文档读写
- [x] `commands.py` — 外部指令视图

### 4.2 `tools/`（11 个模块，0 个零覆盖）

- [ ] `proc_runner.py` — 子进程执行与超时保护
- [ ] `command_tasks.py` — 异步任务管理
- [ ] `memory_search_impl.py` — 记忆检索工具实现
- [ ] `memory_quality_impl.py` — 蒸馏质量管理工具
- [ ] `tool_meta.py` — 内置工具元数据

### 4.3 `web_bridge/`（5 个模块，0 个零覆盖）

- [x] `web_inbox.py` — 对话收件箱存储层
- [x] `web_inbox_store.py` — 收件箱持久化层
- [x] `audio_prune.py` — 音频目录回收

---

## 五、P2 / P3：`routes/` 与其余

### 5.1 `routes/`（17 个模块，9 个零覆盖）

- [ ] `bridge.py` — 远程桥接上报接口
- [ ] `config_route.py` — 配置读写接口
- [ ] `ext.py` — 提供方通道
- [ ] `memory_graph.py` — 记忆图谱接口
- [ ] `memory_graph_page.py` — 图谱页面
- [ ] `web.py` — 网页版资源接口

### 5.2 其余

- [ ] `core/memory_db_diag.py` — 数据库诊断层
- [ ] `app.py` — 应用装配
- [ ] `server.py` — 兼容入口

---

## 六、已覆盖但需加固

以下模块已有测试文件，但测试停留在策略层或纯函数层，**执行路径未验证**。这类最危险——统计上算「有覆盖」，实际挡不住故障。

- [ ] `voice_tts.py` — 现有 13 个用例全部替换 `_dispatch`，需补真实执行层用例
- [ ] `message_router.py` — 现有用例聚焦窗口与锁，未覆盖推送失败重试链路
- [ ] `message_flow.py` — 仅在缓存测试中被间接引用，推送主流程无用例
- [ ] `wecom_media_collect.py` — 覆盖率 17.5%：收集与聚合分支基本未执行，需补媒体收集链路用例

---

## 七、提交闸门

单元测试已纳入 pre-commit 钩子（`pytest` 可用时运行 `flask_server/tests`，不可用时降级为 `unittest`）。任何测试失败都会阻止提交。

覆盖率也纳入同一钩子：装了 `pytest-cov` 时按 `flask_server/.coveragerc` 统计并校验 `fail_under`，
低于下限即判提交失败；未装插件则只跑测试。下限当前为 43，是只升不降的基线，
每补一批测试后上调到新的水位。

> 校验方式：`pre-commit run --all-files`

---

## 八、进度记录

| 日期 | 完成项 | 提交 |
|---|---|---|
| — | 建立清单、接入测试钩子 | — |
| 2026-10-30 | 补 `sniff_extension` 与来件入口（文件名净化 / 类型 / 体积）用例；接入覆盖率闸门并集中口径；刷新本表数字 | `6b2c494` `b40a856` `23bfee8` |
