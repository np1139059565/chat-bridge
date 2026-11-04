# 待办清单

> 本文件记录已确认但尚未排期处理的问题与工作项。
> 每条必须写明：现象、根因或取证方向、影响面、优先级。
> 处理完成后移出本文件，结论记入对应专题文档。

## 一、待验证

### 抽屉指令 `/dc` 与 `/do` 无响应

**状态**：代码已修复，待实机验证。

**现象**：执行 `/dc`、`/do` 后，界面回「指令 /dbg-open 未在时限内执行（扩展未打开或未在目标页）」，
抽屉无变化。同期内置指令（如 `/sd`）正常执行。

**根因**：扩展执行完命令后回传结果时漏传通道参数。

`05_tool-handlers.js` 的 `postResult(requestId, result, channelPath)` 在缺省
`channelPath` 时回落到 `/api/ext/<provider>`（AI 工具通道）。但 `handleTask`
调用时只传了两个参数，导致**所有命令的结果都发回 AI 工具通道**。
用户指令入的是 `command_hub`，其等待方在 `/api/command-ext/<provider>` 上等，
永远等不到结果，`FORWARD_TIMEOUT`（10 秒）后报「未在时限内执行」。

内置指令不受影响：它们走卡片总线（`drawer-command`）由镜像抽屉直接执行，
回执走 `/api/bridge/result`，不经过这条通道。

**修复**：

1. `handleTask(task, channelPath)` 增加通道参数并透传给 `postResult`；
2. `03_heartbeat.js` 的指令循环传入 `/api/command-ext/<provider>`；
   AI 工具循环保持省略，继续走默认 `/api/ext/<provider>`。

**验证方法**：重载调试扩展 → 抽屉设置页点 `/do`，抽屉应打开；
点 `/dc`，抽屉应关闭；两条均不再出现「未在时限内执行」。

**影响面**：外部指令回执链路；AI 工具通道不受影响。

**优先级**：P1。

### 提交钩子：结构质量剩余三项未清

**状态**：已处理，钩子放行。

三项超标项已按职责拆分，`hygiene` 与 `quality` 两个钩子均通过：

| 项 | 位置 | 处理方式 | 拆分后 |
|---|---|---|---|
| 超大文件 | `extend/dialog/parts/05g_cards.js` | 签名存取四个函数迁入 `05j_card_sig.js` | 335 行 |
| 超大文件 | `flask_server/remote_bridge/command_registry.py` | 分组与展示层迁入 `command_groups.py` | 294 行 |
| JS 函数体过长 | `extend/dialog/parts/04_sessions.js` `loadConversation` | 抽出 `_scheduleConvRetry` 与 `_mergeSavedConv` | 低于 80 行 |

拆分只移动职责位置，方法挂载点与调用方式不变。`help_groups()` 的输出结构由
`test_command_groups.py` 五条用例覆盖，拆分后全部通过；测试的补丁目标同步改到
`command_groups`，避免打在已迁走的旧位置而落空。

**同批已完成（供核对）**：

- `memory_cards.upsert_card` 参数由 10 个改为「定位键 + 字段字典」（`CARD_FIELDS`）；
- `push_pipeline._push_merged` 改为上下文对象，与 `_push_locked` 同约定；
- `memory_conversations.py` 读取侧拆出 `memory_conversation_read.py`，462 → 368 行；
- `check_doc_sync.py` 补 `flask_server/remote_bridge` 解析基准，
  并把 `channel-genericization.md` 列入历史文档豁免。

## 二、下一阶段重点

### 合并对话框 JS 测试与文件工具的重复块

**位置**：`flask_server/tests/js/test_dialog_boot.test.js` 与 `test_dialog_contracts.test.js`；
`flask_server/tools/file_image_impl.py` 与 `file_read_impl.py`。

**处理方向**：先按用例语义归并，再抽公共夹具与公共函数，各调用点改为引用。
合并后用例总数与行为覆盖不应减少，只减少重复实现；抽函数前先补两条路径的行为测试。

**优先级**：P1。

## 三、待排期

### 旧推送链路代码清理

**状态**：待排期。推送链路已全量切到 `channel/push_pipeline`，
`bridge.use_pipeline` 开关与旧 router 的残留路径构成双轨，需清理为单轨。
不再保留回退通路。

**处理方向**：

1. 删除 `bridge.use_pipeline` 配置读取与全部分支判断；
2. 逐个确认旧 router 中的函数是否仍被新链路调用。
   保留 QQ 被动回复窗口、`next_seq` 序号分配、`note_incoming` 续期补推与发送原语，
   其余删除；
3. 删除后跑全量单元测试，并做一次实机推送验证。

**影响面**：`flask_server/remote_bridge/` 的推送路径与配置读取。

**优先级**：P1。

## 四、暂缓

### 高复杂度函数与重复块清理

**现状**：`scripts/check_quality.py` 报大量高复杂度函数与跨文件重复块，
具体数字以脚本实时输出为准；三份文档中的历史快照互不一致，不可作为现状引用。

**决定**：暂缓批量清理。

**理由**：存量过大，逐个人工拆分不现实；脚本没有基线时永远返回 1，
红着的闸门等于没有闸门，也看不出新增项是否真的在减少。

**处理方向**：先为脚本增加基线文件，把存量登记为已知项，使新增超标能被单独识别。
基线建立与批量拆解统一排期，不与其他故障修复并行。

### 测试覆盖补充

**现状**：整体覆盖率 43.3%，零覆盖模块 16 个，P0 缺口集中在 `remote_bridge/`。

**决定**：暂缓，待故障清理告一段落后统一排期。

**重点**：`voice_tts` 现有用例全部替换 `_dispatch`，执行路径未验证，属假覆盖，
补充时优先做真实执行层用例。详见 `docs/test-coverage-tracker.md`。

### 私服请求中继技能

**状态**：调研完成，未开发。

**决定**：工作量较大，排在其他故障清理之后。

**硬前提**：阶段零须先探明网页会话 id 是否在 DOM 上暴露、能否按 id 切换；
该步不成立则方案需重新设计。详见 `docs/private-relay-progress.md`。

## 五、已关闭

| 问题 | 结论 | 依据 |
|---|---|---|
| S3 幽灵卡片：执行时被判不在镜像中而拒绝 | 已解决 | 镜像判定改用工具名与参数组成的执行签名（`cardMatchesBySig`），不依赖随重渲染变化的代码块 id |
| 提交钩子：三项结构质量超标 | 已解决 | 三个文件按职责拆分，`hygiene` 与 `quality` 钩子放行，见「一、待验证」同名条目 |
| S5 设置页「可用指令」缺外部指令与自定义指令 | 已解决 | `command_registry.help_groups()` 在内置分组后追加两组，设置页可见 |
| S1 刷新后已执行卡片退回待执行 | 已解决 | `memLoadConv` 网络失败返回 `{ok:false}` 而非 null，加载锁按指数退避重试，实机连续刷新状态稳定 |
| S2 非末条卡片抢占自动执行 | 已解决 | 候选判据改为「末位 + isFreshReply」，实机不再复现 |
| S4 卡片退化为普通代码块 | 已解决 | 恢复逻辑补齐渲染所需字段，刷新后执行入口正常显示 |
| 末尾卡片待执行判定为 false | 正常行为 | 截图中均为 `reason=scroll`、`isFreshReply=false`，属向上滚动加载历史，按设计不放行 |
