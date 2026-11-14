# C-11 三份契约文档交叉一致性总索引（漂移防护底稿）

> 性质：只读索引。只描述编号集合、STATUS 标注集合、唯一键语义声明与交叉引用，
> **不实装执行下游、不装配运行时 M、不建切换开关、不切活链、不预设 B-7 结论**。
> 被索引的三份已合入文档：
> - C-8 `standard_chain_field_matrix.md`：14 条逐项对拍矩阵（合并 17a8b32）；
> - C-9 `standard_chain_boundary_contract.md`：六段占位边界 / 异常语义契约（合并 3116ae0）；
> - C-10 `standard_chain_pending_criteria.md`：四条待对拍判据清单 S1-S4（合并 a92f1bf）。
> 代码侧只读基准：`extend/lib/standard_chain_adapter.js`（`STATUS` / `KEY` 与六段）
> 与 `extend/lib/standard_chain_contract.js`（`PRE_DISPATCH_HOOK_CONTRACT` /
> `PROTOCOL_RETIREMENT_CONTRACT` / `standardToolMessage` / `execKeyFromToolCall`）。
> B-7 按 12:25 与 14:16 广播仍在途（最后一笔整块大单，允许先交子面、余面拆 B-8/B-9）。

## 一、三份文档各自条目编号集合

| 文档 | 条目集合 | 数量 | 编号形态 |
| --- | --- | --- | --- |
| C-8 矩阵 | #1 至 #14（仅「## 一、逐项对拍矩阵」小节内 14 行；「## 二、九步装配推演」的 1-9 是步骤号，不计入矩阵条目） | 14 | 数字 1..14 |
| C-9 六段 | `parse` / `buildCard` / `execute` / `reply` / `dedupe` / `restore` | 6 | 函数名 + 边界小节 1..6 |
| C-10 四槽 | S1 / S2 / S3 / S4 | 4 | 槽位号 S1..S4，各对齐矩阵 #4/#7/#13/#14 |

三份合计 24 个可引用条目；任何一份出现第 15 条矩阵行、第 7 段接口、第 5 槽位，
或步骤号 1-9 被误当作矩阵条目，均视为漂移，由反查夹具拦截。

## 二、STATUS 标注集合（恒为 declared-placeholder）

| 面 | 标注位置 | 必须恒为 |
| --- | --- | --- |
| 六段适配层状态 | `standard_chain_adapter.js` 的 `STATUS`；C-9「## 二、逐段状态标注」6 行 | declared-placeholder |
| 钩子声明面 | `PRE_DISPATCH_HOOK_CONTRACT.status`；C-8 矩阵 #1/#2/#3 | declared-placeholder |
| 协议退役面 | `PROTOCOL_RETIREMENT_CONTRACT.status`；C-8 矩阵 #13；C-10 S3 | declared-placeholder |
| 四槽判据生效期 | C-10「通用三态判定口径」全局不变量 | declared-placeholder |

结论：B-7 到达并完成对拍前，三份文档里凡标 STATUS 的位置**必须全部**为
`declared-placeholder`；任一处提前写成实装态、或出现「已装配 / 已退役」字样，
即编号与状态漂移，分发方按不一致裁定，不由 c 自行改口径。

## 三、唯一键语义声明（三份必须一致）

| 面 | 唯一键文字 | 出现位置 |
| --- | --- | --- |
| 标准调用键 | 标准 `tool_call.id`（`call_<nonce>`） | C-8 #9/#10/#12、C-9 G2 与逐段状态表、C-10 全局不变量与 S2/S3 |
| tool 消息三键 | `role` / `tool_call_id` / `content` | C-8 #6/#11、C-9 reply 段、C-10 S3 替换位段 |
| 刷新恢复键 | `noMessageFingerprint`（去消息指纹） | C-9 G4 与 restore 段、C-8 #12、C-10 S2/S4 |

三份文档与两个 lib 的 `A.KEY === 'tool_call.id'`、`C.makeToolCallId(nonce)` 产出
`call_<nonce>`、`C.standardToolMessage` 产出三键，必须同向；
不得出现以旧 `msgId` / 消息指纹 / `bridge-chat-call` 等旧协议字段作唯一键的声明分叉。

## 四、逐项交叉引用表（矩阵 ↔ 六段 ↔ 四槽）

| 矩阵条目 | C-9 六段接口 / 代码面对应 | C-10 槽位 | 同义异名说明 | STATUS 约束 |
| --- | --- | --- | --- | --- |
| #4 fetcher 契约 | 六段无直接对应；指向 A-7 `model_reply_hook` / `_as_assistant_reply` 与 `PRE_DISPATCH_HOOK_CONTRACT`（跨侧） | S1 | 「fetcher 跨侧」「模型回复入口」「`fn(history)` 钩子面」三种说法同面 | declared-placeholder |
| #7 tool_calls 意图执行 | `execute`（六段第 3 段，占位）；服务端 `pending_tool_calls` / `_execute_pending` 已实交付 | S2 | 「意图执行」「execute 段」「运行时执行权仍在旧链」同面 | declared-placeholder |
| #13 协议字段退役 | 六段无直接对应；指向 `PROTOCOL_RETIREMENT_CONTRACT`（契约面声明） | S3 | 「协议字段退役」「替换位变更面」「B-7 核心面」同面 | declared-placeholder |
| #14 旧标记摘除 | `restore` 的去消息指纹面（C-9 第 6 段）；运行时标记在 `05g_cards.js` / `05j_card_sig.js` | S4 | 「旧标记」「活链保持」「`call_<nonce>` 优先 + 旧 `msgId` 兼容双查」同面 | declared-placeholder |
| #1/#2/#3 钩子签名与点位 | 六段无直接对应（`PRE_DISPATCH_HOOK_CONTRACT` 名字面） | 无直接槽（S1 判据引用） | 「钩子名字面」「分发前钩子」「L213 点位」同面 | declared-placeholder |
| #5/#6/#9/#10/#11/#12 标准字段与键 | `parse` / `buildCard` / `reply` / `dedupe` / `restore` 的键位声明 | S2/S3/S4 的判据段引用 | 「标准三键」「`tool_call.id`」「去消息指纹」同面 | declared-placeholder |

交叉引用表内每个编号都可在对应文档里找到：矩阵 #4/#7/#13/#14 命中 C-8 的 14 行，
`parse`/`buildCard`/`execute`/`reply`/`dedupe`/`restore` 命中 C-9 六段标题与状态表，
S1/S2/S3/S4 命中 C-10 四个槽位标题；任一悬空编号即漂移，由夹具断言拦截。

## 五、B-7 判定时点（沿用 C-10，不另立口径）

按 12:25 分发方口径，B-7 可按一次提交收口，也可先交已完成子面、余面拆 B-8/B-9 续派。
两种形态下「三笔对拍齐备」的判定时点同为：B 侧替换位全部显式列全、分发方逐片验收合入、
按 C-8 矩阵 14 条与 A-7 实交付逐项对拍完毕；不以单笔 B-7 提交落地为齐备标志，
也不因拆片提前摘旧标记。本索引**沿用 C-10 判据、不另立口径**、不预设 B-7 是否拆片、
不代替分发方裁定时点。旧标记摘除仍按 01:17 更正待三笔齐备后由分发方另行下发，
不构成本笔验收条件、不是新前置。

## 六、边界与只追加记录

- 范围：只新增本文件（`extend/lib/` 下总索引）与 `flask_server/tests/js/` 下反查夹具；
  只读三份 `.md` 与两个已合入 lib，不改任何 lib 源码、不改三份文档、不碰他笔文件。
- 夹具：断言三份条目数分别 14 / 6 / 4、STATUS 全为 `declared-placeholder`、
  唯一键声明一致、交叉引用表无悬空编号、不预设 B-7 是否拆片；
  全文规避跨端反斜杠转义差异（零反斜杠、零正则、按字符码 10 切行）。
- 新增被测 JS 源文件数为 0（索引为 `.md`，不进覆盖率分母、不被 quality 扫描）；
  本机 node v24 的「ℹ 前缀 / 分层路径」报告差异不作达标依据，
  不改钩子脚本 / 90-70 阈值 / `js_coverage_baseline.json`、不用 `--update-baseline`。
- docs 只追加：本笔不删改历史台账与总线消息；记录由 `send report` 追加到 `docs/bus/c.md`，
  分发方验收结论由其追加到 work-board。
- 提交：基于实时 `origin/main` 新建提交，勿 amend 已合入历史、
  勿 force-with-lease 回退已发总线消息；一次提交收口，
  `force-with-lease` 更新 `origin/work/ai-c`，`send report` 回 hash 与实测。
