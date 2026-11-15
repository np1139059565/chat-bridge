# B-10 旧标记摘除前置就绪度报告（c6 九文件顺序表复核）

> 2026-11-15 AI-B 交付（对应 docs/work-ai-b.md 当前任务 B-10，10:05 续派）。
> 性质：只读就绪度取证，零代码改动、零测试改动、不摘除任何标记、不实装、不预设分发方裁定时点。
> 证据基线：origin/main 34e6029（含 B-8 0ccd0c7 / B-9 e3aa27b / B-7 收口片合并 ae0b1cb、C-10/C-11/C-12、c7 迁移计划、c6 盘点、b7 报告）；行号为本轮 origin/main 实仓 git grep / 精读实测。
> 引用（只读）：docs/c6-direct-path-inventory.md、docs/c7-standard-chain-migration-plan.md、docs/b6-legacy-caller-map.md、docs/b7-protocol-retirement-status.md、docs/a5-standard-chain-inventory.md、docs/work-board.md、extend/lib/standard_chain_pending_criteria.md（C-10）、standard_chain_replacement_map.md（C-12）、standard_chain_crossref_index.md（C-11）、standard_chain_b9_slot_contract.md。

## 一、总体结论

**旧标记摘除当前不下发，前置未满足。** 分发方 10:05:32 广播已按 C-10 S1-S4 逐槽判态并裁定「阶段 3 不进入摘除步」；本报告以实仓取证逐项钉死「还差什么」，共五层前置全部未满足，任何一方不得据此自行摘除或把 declared-placeholder 翻成已装配。

## 二、S1-S4 逐槽就绪度表（交付 ①）

| 槽位 | 当前态 | 缺口 | 触发表更的具体条件 | 分发方裁定点 |
|---|---|---|---|---|
| S1 #4 fetcher 跨侧 | 契约侧已对拍一致（A-7×C-7，分发方 10:05 广播判「一致」）；L10 入口在码：routes/chat_api.py `register_pre_dispatch_hook(fn(history)->None|list)` / `clear_pre_dispatch_hooks` / `_run_pre_dispatch_hooks` 唯一点位（历史合并后、_execute_pending 前），契约测试 test_chat_l10_contract.py 9 条 | L10 接真实模型缺外部模型服务与凭证，契约入口为可插拔占位、未注册真实模型钩子 | ①外部模型服务与凭证到位（用户侧排期）；②注册真实模型钩子并经真实使用验证；③分发方按 C-10 S1 判据复判 | L10 真实接入的排期与验收归用户侧与分发方；不构成运行时执行权迁移（广播原文），S1 当前态不触发摘除表更 |
| S2 #7 tool_calls 意图执行 | 装配面九步第 5 步仍 declared-placeholder：extend/lib/standard_chain_adapter.js `STATUS='declared-placeholder'`（L7）、六段中 `execute(card)` 返回占位（L11）、`by: KEY` 不变；B-8/B-9 纯函数层（standard_slot_m345.js / standard_chain_b9_slot_resolver.js）已入 main 但只做转换/拒绝语义，未装配运行时 M | 运行时执行权仍 100% 在旧建卡直调路径（05g_cards/06_execute），state.toolCalls 与 card.toolCall 无执行期下游（c6 L54/L60：toolCalls 0 处下游、card.toolCall 2 处仅取回执 id） | ①分发方下发摘除任务书；②执行方实装装配面九步第 5 步（execute 实装、运行时执行权迁标准链）；③分发方独立 worktree 验收通过 | 装配第 5 步由占位转实装并验收通过是 S4 摘除的硬前置（C-10 S2 判据原文）；时点归分发方，本报告不预设 |
| S3 #13 协议字段退役 | 替换位列全（b7 报告第三节 M1-M8 八槽四项齐全）且分发方判「一致」（10:05 广播） | 契约面判一致≠运行时退役：M1-M8 对应旧位仍在活链（见第四节逐文件取证），b7 第三节明确「三网关包装与公共层解析仍是真实生产链」；STATUS 仍 declared-placeholder（PROTOCOL_RETIREMENT_CONTRACT） | ①S2 装配实装并验收；②协议字段按替换位逐槽切到标准链并经真实使用；③分发方复判后 `PROTOCOL_RETIREMENT_CONTRACT.status` 方可转实装（C-10 S3 收口条件原文） | S3 判一致仅登记「列全且对齐」，不自动触发任何摘除；转实装时点归分发方 |
| S4 #14 旧标记摘除 | 运行时执行权未迁移（广播原文：bridge-chat-call / bridge-chat-res / is_tool_result 在活链多文件命中）、摘除任务书未下发、c6 九文件顺序表未执行（本轮逐行复核见第三节，九文件全部仍在活链） | 三项缺一不可：①运行时执行权已由旧链迁到标准链且分发方验收；②分发方另行下发摘除任务书；③按 c6 九文件顺序表执行 | 三项同时满足后方进入摘除步；任何一项缺位即保持现状不摘除 | C-10 S4 判据原文：「三笔齐备 + 运行时执行权迁移 + 分发方另行下发 + 按顺序表执行 → 方可摘除」；阶段 3 当前不进入摘除步 |

## 三、c6 九文件摘除顺序表逐行复核（交付 ②）

顺序表本体在 docs/c7-standard-chain-migration-plan.md 第 2 节（五步分组，基准为 c6 第一节九混存文件原表）。逐文件当前实测（origin/main 34e6029）：

| 文件（c6 原表序） | 存在 | 活链 | 调用方 / 标记现状（本轮实测） | 摘除前置 | 预计影响面 |
|---|---|---|---|---|---|
| 00_data.js | 是 | 是 | bridge-chat-res 3 处（L71/73/174）、external-call 3 处（L50/73/113）：cardHasMessage 按 nonce 配对 external-call 与 bridge-chat-res 防镜像重复渲染、buildTimeline 去重外部卡片；3 份 js 测试引用 | 步骤 2：nonce 配对改 tool_call.id 配对 | 配对与折叠展示（镜像去重）、夹具 3 份 |
| 01b_bridge.js | 是 | 是 | run-command 2 处（L392 注释、L400 POST /api/bridge/run-command）：网页抽屉唯一调用方；3 份 js 测试引用 | 步骤 2：迁标准链或按 M3 退役取证 | 用户指令旁支（与 QQ 指令同链，回执不进 AI 对话流）、夹具 3 份 |
| 01c_bridge_cmd.js | 是 | 是 | 本轮宽窄口径检索 bridge-chat-call / bridge-chat-res / external-call / run-command / toolCalls / toolCallId / nonce / msgId / executedSigs 全部零命中；文件为远程桥接指令增删改管理（/api/bridge/commands），无旧协议标记。C-6 将其列九混存文件之一按当时全量符号口径（c7 第 1 节已声明 C-6 与 c7 检索口径不同、非仓内状态变化）；1 份 js 测试引用 | 步骤 2 分组列名，但本轮实测无旧标记可摘 | 桥接指令管理面（若摘除仅涉 /api/bridge/commands 接口面，非协议标记面）、夹具 1 份 |
| 05c_prompt.js | 是 | 是 | bridge-chat-call 1 处（L39）、bridge-chat-res 6 处（L205/210/262/269/276 等）、external-call 1 处（L252）、toolCall 2 处（L257/286）；5 份 js 测试引用 | 步骤 3：标准 tool_calls 解析入口可用 | 提示词拼装与回执信封翻译（含本体缺失逐字退回兜底 L41-45/L254-258/L283-287，兜底三项补签对象）、夹具 5 份 |
| 05d_memory.js | 是 | 是 | bridge-chat-res 2 处（L52/70）：工具结果独立第三类角色判定，不误触记忆窗口；0 份 js 测试直接引用（C-6 列九文件按符号口径，非夹具依赖） | 步骤 2 配对面，但 c7 五步表未显式列行——本报告如实登记为顺序表覆盖缺口（c7 第 2 节表格未单列 05d_memory.js，仅以 c6 原表为准） | 记忆窗口角色判定；无直接夹具 |
| 05f_parse.js | 是 | 是 | bridge-chat-call 3 处（L215/229/234）：parseToolCall 只认 bridge-chat-call；bridge-chat-res 3 处（L371/376/390）：msgSource 判 tool 来源；external-call 2 处（L334/351）；6 份 js 测试引用 | 步骤 3：标准 tool_calls 解析入口可用 | 调用解析与消息来源判定（旧执行主链唯一解析入口，摘除即断主链）、夹具 6 份 |
| 05g_cards.js | 是 | 是 | bridge-chat-call 1 处（L123）、bridge-chat-res 3 处（L430/431/438）、toolCalls 3 处（L47/59/132）、toolCall 10 处（L47/59/108/127/132/227/324/327/331/338）：建卡与候选 + _translateToolCalls 落 card.toolCall/toolCallId；4 份 js 测试引用 | 步骤 4：state.toolCalls 有执行期下游 | 建卡候选主链（autoCandidates/armedLast/rerunCard 生产端；executeCard 驱动端在 06_execute）、刷新恢复链绑定、夹具 4 份 |
| 05j_card_sig.js | 是 | 是 | toolCall 3 处（L26/57/113）：_executedSig 标准键+msgId 旧键双查（L26-40）、_markExecutedSig 按 card.toolCallId（L57）、_restoreExecutedCards 按 card.toolCallId||msgId（L113）——C-7 已实改的双查构型仍在码；4 份 js 测试引用 | 步骤 5：execKeyFromToolCall 接入且 executedSigs 去消息指纹（第 5 步原文） | 刷新恢复与去重（executedSigs 落盘、幽灵卡判据）、夹具 4 份 |
| translator.js | 是 | 是 | bridge-chat-call 4 处（L84/85/123/126）、bridge-chat-res 4 处（L90/161/166/177）、external-call 1 处（L163）：新标准链本体本身含旧协议字串（双向翻译职责所在）；dialog.html L25 / manifest.json L28 挂载 | 步骤 3：标准 tool_calls 解析入口可用；本体为翻译层，摘旧标记时须整译 ||| 翻译层本体（不属旧链，但含旧协议字串），摘除动作待分发方定义「本体上旧协议字串的处理口径」（可能整体保留只删旧侧导出） | 夹具 2 份；兜底（FALLBACK_STANDARD） |

九文件小结：全部存在、全部活链、零摘除。c7 顺序表（五步分组）覆盖 c6 九文件中的 8 个（01c 列名但本轮实测无旧标记、05d 未单列行）；本报告如实登记两处口径差异，供分发方复核顺序表时参考，不构成新前置、不要求改 c7。摘除的统一硬前置仍为第二节 S4 三项（执行权迁移 + 任务书下发 + 按表执行）。

## 四、活链运行时证据（摘除前置未满足的实码支撑）

- 协议字串全仓活链命中（origin/main 34e6029，非测试文件）：bridge-chat-call：05f_parse.js、05g_cards.js、05c_prompt.js、translator.js；bridge-chat-res：00_data.js、05c_prompt.js、05d_memory.js、05f_parse.js、05g_cards.js、translator.js、01g_external_cards.js、01j_card_consume.js（c6 已列）+ 服务端 message_parse.py；external-call：00_data.js、05c_prompt.js、05f_parse.js、translator.js + 三网关包装层 + 公共解析层（b6 地图）；run-command：01b_bridge.js（抽屉唯一调用方）+ routes/bridge.py（服务端入口）；is_tool_result：outbound.py 构造单点 + message_flow.py/message_router.py 消费两点（b7 报告 2.3）。
- 运行时执行权：adapter.js `execute(card)` 占位（L11，declared-placeholder），B-8/B-9 纯函数层未装配运行时 M；旧链 executeCard（06_execute.js）承担每一次真实工具执行（c6 运行时口径 100%）。
- 刷新恢复链：executedSigs 双查构型（标准 call_<nonce> 优先 + 旧 msgId 兼容）在码，摘除须先统一恢复键（c7 第 5 节「刷新恢复键迁移」）。

## 五、显式结论（交付 ③）

**旧标记摘除当前不下发，前置未满足。** 依据（只描述判据、不实装、不预设下发时点）：

1. 运行时执行权未由旧链迁到标准链：adapter 装配面九步第 5 步（execute）仍 declared-placeholder，未实装、未验收。
2. 摘除任务书未下发：分发方 10:05:32 广播明确「任何一方不得据此自行摘除或把 declared-placeholder 翻成已装配」，无摘除任务书在总线中。
3. c6 九文件顺序表未执行：九文件全部存在、全部活链、零摘除（第三节逐行复核）。
4. S1/S3 判一致不构成摘除触发：S1 缺 L10 真实模型接入（外部凭证另行排期），S3 判一致仅为契约面列全对齐，运行时退役面全未动。
5. 本报告为只读取证基线，供分发方后续裁定；不实装、不建切换开关、不新增运行期探测分支、不摘除任何标记。

## 六、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| pre-commit 七道 | pre-commit run --all-files | 通过（七道全 Passed，2026-11-15 收口轮实测） |
| 全量 pytest | python -m pytest tests -q -p no:cacheprovider（flask_server/ 下，单进程串行） | 1078 passed / 1 failed，唯一失败 test_weixin_protocol.py::TestClientContract::test_production_client_gets_ctx_path（B-7 记录载明的已知失败，非本任务引入） |
| check_js_tests.py | python scripts/hooks/check_js_tests.py | 通过：545/545，覆盖率达标，无退化与新增 |
| quality 新增 | 结构质量十二项 | 通过：python scripts/quality_rules.py 退出码 0，全部为 [已知] 存量，无 [新增] |
| diff --check | git diff --check / git diff --cached --check | 通过：无空白错误 |
| 边界 | git status 核对 | 新增仅本报告 1 份 + docs/work-ai-b.md 只追加；零代码、零测试改动。extend/dialog/AUDIT.md 为未跟踪文件，非本任务产物，未纳入提交、未改动 |

> 实测结果以收口轮实跑为准，不谎报全绿、不自填。
