# 对话框分片拆分历史与故障记录

> 从 `docs/dialog-parts-split-progress.md` 迁出的过程记录：一次线上故障的定位与修复、
> 两次拆分的具体动作、当时的质量检查现状与后续方向。
> 判断「现在该怎么做」以 `docs/dialog-parts.md` 为准。

## 五、故障记录：keyOfId is not a function

### 5.1 现象

接收网页消息时报 `Uncaught (in promise) TypeError: this.keyOfId is not a function`，
位置 `05_messages.js:247`，调用链 `04_sessions.js applyConversation → 05_messages.js ingestMessages`。
消息无法入树，界面功能中断。

### 5.2 根因

二次拆分把 `keyOfId`、`parentIdOf`、`isTreeTail`、`assembleBranchKeys` 移入 `05h_tree_query.js`，
迁移时挂到了 `D` 上，而全部调用点写的是 `this.xxx(...)`。`this` 是 Vue 实例，实例方法只来自 `D.methods`，
`D` 上的同名属性不会成为实例方法，故运行时报错。

四个函数同时失效，`keyOfId` 因调用最早而先报错。

### 5.3 修复

- `05h_tree_query.js`：声明 `const M = D.methods`，四个函数改为 `M.xxx = function`。
- `05_messages.js`：更正迁移说明注释，指明挂载点是 `D.methods`。

### 5.4 验证

- `node --check` 两文件通过。
- 全分片静态比对：以 `this.xxx(` 调用而无对应定义的，仅剩 `$forceUpdate`（Vue 内置）与 `_persist`（mounted 内动态挂载），均正常。

## 六、质量检查现状

闸门已统一为单一入口 `scripts/quality_rules.py`（十二项），提交钩子与 CI 跑同一个脚本，
CI 已去掉 `continue-on-error`。三项基础检查的实现迁至 `scripts/quality_extra.py`，
原 `scripts/check_quality.py` 保留为薄转发，只维持命令入口不断链。

存量违规登记在 `scripts/quality_baseline.json`：命中的打印时标注 `[已知]` 且不计入失败，
超出基线的标注 `[新增]` 并返回失败。故绿就是真绿，红就是真有新增问题。

**当前存量数字与批次进度以 `docs/quality-debt-tracker.md` 为准**，本文不重复登记。

已拆解的超标项（拆分前均先补行为测试，拆分后测试全通过）：

| 函数 | 拆分前 | 拆分后 |
|---|---|---|
| `channel/media.py` `push_collected` | 34 行 / cc=12 | 收集、取语音、发送三段 |
| `channel/push_pipeline.py` `_push_locked` | 101 行 / cc=29 | 筛选、配额、合并、逐条四段 |
| `channel/text.py` `_assemble_ordered` | 61 行 / cc=31 | Markdown 快捷、分组收集、渲染三段 |
| `05g_cards.js` | 470 行 | 335 行，签名存取四个函数迁入 `05j_card_sig.js` |
| `command_registry.py` | 469 行 | 294 行，分组与展示层迁入 `command_groups.py` |
| `04_sessions.js` `loadConversation` | 97 行 | 抽出 `_scheduleConvRetry` 与 `_mergeSavedConv` 两个方法 |

上述三项拆分只移动职责位置，不改行为：方法仍挂在 `D.methods` 上，调用方按 `this.xxx(...)` 调用不受影响；
`command_registry` 在文件末尾重新导出 `command_groups` 的公开函数，调用方仍按 `command_registry.xxx` 访问。
拆分后 python 测试 622 项、前端测试 157 项全部通过。

存量欠账的分布：

- 高复杂度函数集中在 `flask_server/remote_bridge/`（企微、微信、QQ 通道）、`flask_server/core/memory_*`、
  `scripts/hooks/`、`skills/anatomy/`、`flask_server/routes/tools.py`。
- 重复块主要集中在 `flask_server/tests/js/test_dialog_boot.test.js` 与 `test_dialog_contracts.test.js` 之间，
  以及 `flask_server/tools/file_image_impl.py` 与 `file_read_impl.py` 之间。

上述欠账来自首批重构之后新增的代码，未纳入过拆分治理。首批重构文档中「cc≥10 清零」的结论
适用于当时的代码范围，不代表当前全工程状态。

`extend/dialog/parts/` 下的分片：超大文件为 0，高复杂度函数为 0，
仅 `05_messages.js` 等文件因与相邻分片存在重复块被列出。

## 七、后续可选方向

1. 拆分高复杂度函数（存量 160 处，集中在 `remote_bridge/`、`core/memory_*`、
   `routes/tools.py`），单独立项、分批推进。每拆一个函数前先补行为测试。
   已拆处见第六节表格。
2. ~~合并对话框 JS 测试中 `test_dialog_boot` 与 `test_dialog_contracts` 的重复用例~~
   已完成：两份测试改用 `_dialog_fixture.js` 提供的加载顺序与沙箱替身，
   boot 183→75 行、contracts 195→126 行，用例数与行为覆盖不变（12 项全过）。
3. ~~合并 `file_image_impl.py` 与 `file_read_impl.py` 的重复片段~~
   已查明：两文件的重复位于导入区，属「依赖相同」而非「实现重复」，不做合并。
   `check_quality` 的重复检测补上多行导入续行识别，跨文件重复组 142→79。
4. ~~为质量脚本增加基线文件~~ 已完成：`scripts/quality_rules.py` 接入存量基线
   `scripts/quality_baseline.json`，按「检查项 + 文件」记录已知条数，只对新增违规返回失败。

优先级建议：存量清理分批推进，每拆一处同步调减基线，使基线成为净减少的度量。
合并两个脚本的口径（钩子跑九项、CI 跑三项且放行）需单独排期。

## 八、本次会话拆分记录（2026-11-08）

两次拆分均先落守卫再动刀，拆完以「语法、全量前端测试（249 项）、质量闸门、重复块指纹与 HEAD 差集」四连验证，全部通过。

### 8.1 05_messages.js → 05l_autoexec.js

| 项 | 值 |
|---|---|
| 拆出职责 | 自动执行决策末段（_finalizeAutoExec）与「推送时仍在生成」的待执行卡片暂存回捡 |
| 行数变化 | 05_messages 463 → 406；05l 新增 106 |
| html 注册 | 紧随 05_messages.js 之后 |

### 8.2 00_data.js → 00e_computed.js

| 项 | 值 |
|---|---|
| 拆出职责 | Vue computed 定义（curConv / messages / cardMap / sessionEntries / convList 等） |
| 行数变化 | 00_data 452 → 269；00e 新增 197 |
| html 注册 | 紧随 00_data.js 之后 |

另：两份建卡去重测试（相邻消息 / 同消息）逐字相同的桩安装、分片加载与 buildAll / freshState
辅助抽为 _dup_card_fixture.js（54 行），与 _part_stub / _dialog_fixture 同一惯例；
抽完后跨文件重复组指纹与 HEAD 差集为零，未新增任何重复。
