# 待办清单

> 本文件记录已确认但尚未排期处理的问题与工作项。
> 每条必须写明：现象、根因或取证方向、影响面、优先级。
> 处理完成后移出本文件，结论记入对应专题文档。

## 一、下一阶段重点

### 合并对话框 JS 测试与文件工具的重复块

**位置**：`flask_server/tests/js/test_dialog_boot.test.js` 与 `test_dialog_contracts.test.js`；
`flask_server/tools/file_image_impl.py` 与 `file_read_impl.py`。

**处理方向**：先按用例语义归并，再抽公共夹具与公共函数，各调用点改为引用。
合并后用例总数与行为覆盖不应减少，只减少重复实现；抽函数前先补两条路径的行为测试。

**优先级**：P1。

## 二、待排期

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

## 三、暂缓

### 高复杂度函数与重复块清理

**现状**：提交钩子跑 `scripts/quality_rules.py`（九项结构检查），CI 跑
`scripts/check_quality.py`（三项基础检查）。九项检查当前全部达标，基线为空。

**决定**：批量清理继续暂缓；闸门本身的基线已就位。

**已就位**：`scripts/quality_rules.py` 接入存量基线 `scripts/quality_baseline.json`，
按「检查项 + 文件」记录已知条数，命中基线的不计入失败，超出部分算新增并返回失败。
登记形态见 `scripts/quality_baseline.py` 模块说明。

**尚待处理**：两个脚本口径不一致——硬拦提交的是九项，CI 跑的是三项且设了
`continue-on-error`，等于不设防。合并口径与取消放行需单独排期。

**处理方向**：存量清理分批推进，每拆一处就从基线里相应调减，使基线成为净减少的度量。

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

## 四、已关闭

| 问题 | 结论 | 依据 |
|---|---|---|
| S3 幽灵卡片：执行时被判不在镜像中而拒绝 | 已解决 | 镜像判定改用工具名与参数组成的执行签名（`cardMatchesBySig`），不依赖随重渲染变化的代码块 id |
| 提交钩子：三项结构质量超标 | 已解决 | 三个文件按职责拆分，`hygiene` 与 `quality` 钩子放行，详见 `docs/dialog-parts-split-progress.md` 第六节 |
| S5 设置页「可用指令」缺外部指令与自定义指令 | 已解决 | `command_registry.help_groups()` 在内置分组后追加两组，设置页可见 |
| S1 刷新后已执行卡片退回待执行 | 已解决 | `memLoadConv` 网络失败返回 `{ok:false}` 而非 null，加载锁按指数退避重试，实机连续刷新状态稳定 |
| S2 非末条卡片抢占自动执行 | 已解决 | 候选判据改为「末位 + isFreshReply」，实机不再复现 |
| S4 卡片退化为普通代码块 | 已解决 | 恢复逻辑补齐渲染所需字段，刷新后执行入口正常显示 |
| 末尾卡片待执行判定为 false | 正常行为 | 截图中均为 `reason=scroll`、`isFreshReply=false`，属向上滚动加载历史，按设计不放行 |
