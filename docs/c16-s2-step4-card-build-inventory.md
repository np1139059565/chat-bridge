# C-16 阶段 3 九步装配面第 4 步建卡单步只读取证报告

> 性质：只读取证判定片。只新增本报告与一份反查夹具，台账第五节只追加；零代码改动。
> 证据基线：实时 origin/main 6315bf3（含 B-13 验收合入 6938125、08:38 验收裁定 dispatcher-20261116T083859-a53fbe、08:47 任务书 dispatcher-20261116T084752-9cc35f）；开工前 git fetch origin --prune + git merge --ff-only origin/main 已完成，工作区干净，身份 actor=c（work/ai-c）。
> 只读引用：C-8 standard_chain_field_matrix.md 第二节第 4 步行、C-9 standard_chain_boundary_contract.md 第一/二/四节、C-14 standard_chain_c14_signature_table.md 第二/六节、b10-removal-readiness-report.md 第二/三/四节、c6-direct-path-inventory.md、c7-standard-chain-migration-plan.md、c15-s2-remaining-surface-inventory.md 第二节第 4 步行；不改他笔已合入 .md 源码本体。
> 范围：只做第 4 步一步，不扩第 6 / 7 / 8 步、不扩 dedupe、不扩 S1 L10、不碰六段其余声明态；不是实装授权、不是摘除授权。
> 本报告所有差异登记与结论仅为分发方复核输入：不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。

## 一、第 4 步建卡逐文件五项判定（落点 / 当前态 / 活调用方 / 依赖 / 禁区）

C-8 第二节第 4 步推演行（L46）原文：标准 tool_call.id 建卡 | extend/lib/standard_chain_adapter.js buildCard；standard_chain_contract.js makeToolCallId | 仍占位；运行时建卡仍在 extend/dialog/parts/05g_cards.js，旧标记保留 | 依赖 B-7 = 否。实时逐文件展开如下。

| 落点文件 | 当前态（实时 6315bf3） | 活调用方 | 依赖 | 禁区 |
|---|---|---|---|---|
| extend/lib/standard_chain_adapter.js | STATUS=declared-placeholder、KEY=tool_call.id、EXECUTE_STATUS=implemented-S2-step5 独立导出；L16 buildCard(call) 返回 by=KEY / id / status=STATUS，缺 call 或缺 id 回落 null，不生成替代 id、不落消息树；L70 导出 | 运行期 .buildCard( 与 AIMirrorStandardChainAdapter.buildCard 均 0 命中；仅契约夹具经 node 分支 require | 无（声明态，不依赖 B-7） | 零改动；STATUS 保持 declared-placeholder；不扩用 EXECUTE_STATUS 到 buildCard |
| extend/lib/standard_chain_contract.js | L9 PREFIX=call_、L10 makeToolCallId(nonce) 产出 call_<nonce>、L11-13 nonceFromToolCallId 反解、standardToolMessage(callId,content) 产三键、execKeyFromToolCall 会话 id+nonce+工具名+参数摘要（不含消息指纹）、assertStandardToolCall 校验 id 与 function.name；L41 导出 | 运行期源码 0 调用；makeToolCallId 全仓宽口径 6 行 / 4 文件（contract.js 定义+导出、C-14 签名表、C-11 索引、C-8 矩阵 #9/#10 引用），均为文档或夹具引用 | 键映射真源，第 4 步装配时作为唯一键来源 | 零改动；不装配运行时 M；不新增运行期探测分支 |
| extend/dialog/parts/05g_cards.js | 运行期建卡与候选主链：_buildCardsForOne L100 逐块建卡 → L103 this._translateToolCalls(holder, m, blocks, state)；L112 定义，L114 取 window.AIMirrorTranslator，L115 m.role 非 assistant 守卫，L122 ensureNonce(card)，L123 构造 bridge-chat-call 协议信封（tool / parameters / nonce；该文件内精确 1 处），L126 T.toToolCalls(one)，L127 card.toolCall = calls[0]; card.toolCallId = calls[0].id，L129 T.fromBlocks(protocol)，L132 state.toolCalls 汇入 tr.calls；L34/L37/L38 产 autoCandidates / armedLast / rerunCard，L56 _decideIssueTarget 选执行目标 | 该文件内行级命中：bridge-chat-call 1、bridge-chat-res 3、toolCall 10、toolCalls 3、autoCandidates 16、armedLast 4、rerunCard 4；b10 登记 4 份 js 测试引用；state.toolCalls 运行期 2 处（L59 回显、L132 汇入） | 第 5 步 execute 单点已闭合（B-12，06_execute L85 委托 adapter.execute）仅作基线；S4 摘除任务书；c6 九文件顺序表步骤 4（state.toolCalls 有执行期下游） | 活链零改动；旧标记全部保留；不摘除 bridge-chat-call / bridge-chat-res；不切活链 |
| extend/dialog/parts/05j_card_sig.js | 刷新恢复下游读回：L57 card.toolCallId 或 card.toolCall.id 标准键优先、旧 msgId 兼容双查，L113 card.toolCallId 或 card.msgId 恢复键（C-7 实改构型仍在码） | card.toolCallId 运行期 3 处（05g L127、05j L57/L113）；card.toolCall 运行期 6 处（05c L257/L286、05g L108 注释/L127、05j L57/L113） | 第 8 步刷新恢复键统一（c7 第 5 节）；c6 顺序表步骤 5 | 活链零改动；executedSigs 双查构型保持；不摘除 |
| extend/dialog/parts/05c_prompt.js | 提示词拼装读回：L257 / L286 card.toolCall.id 优先、T.callIdFromNonce(nonce) 兜底 | 上述 2 处读回 | 第 6 步 tool 消息回执面（本片不扩） | 活链零改动；本体缺失逐字退回兜底保持 |
| extend/lib/translator.js | 翻译层本体：toToolCalls / fromBlocks 把 bridge-chat-call 代码块翻成标准 tool_calls（规格 3.1 / 4.4），含旧协议字串属双向翻译职责 | 05g L114 取全局、L126/L129 调用；dialog.html L25 与 manifest.json L28 挂载 | 第 3 步标准 tool_calls 解析入口可用（c6 顺序表步骤 3） | 活链零改动；本体上旧协议字串处理口径归分发方定义 |
| extend/dialog/dialog.html | B-12 在 lib 区末尾追加 standard_chain_adapter.js 装载行（L26），translator 之后、parts 之前；adapter 浏览器分支挂 window.AIMirrorStandardChainAdapter | 06_execute.js L85 经该全局调用 adapter.execute（第 5 步，本片不扩） | B-12 已合入 | 活链零改动；不新增装载行、不装配 buildCard 下游 |
| flask_server/tests/js/ | b10 登记 4 份夹具引用 05g_cards.js（test_card_build_behavior / test_card_sig_restore / test_scroll_autoexec / test_translator_wiring_require）；全仓 buildCard 宽口径 93 行 / 28 文件（含文档与夹具），运行期调用方 0 | 断言面，非运行期装配 | 无 | 本片只新增独立命名夹具，不碰 C-15 / A-11 / B-13 报告与夹具本体 |

## 二、与 C-8 / C-9 / C-14 / b10 逐行对拍

| 对拍源 | 原文锚点 | 实时实况 | 判定 |
|---|---|---|---|
| C-8 第二节第 4 步行（L46） | 仍占位；运行时建卡仍在 05g_cards.js，旧标记保留 / 依赖 B-7 否 | buildCard 声明回显、运行期零调用方；05g L103/L112/L123/L127/L132 承担建卡与候选；bridge-chat-call 1 处、bridge-chat-res 3 处全保留 | 一致 |
| C-9 第一节第 2 段（L33-39）与第二节状态行（L92） | buildCard(null) / 缺 id 回落 id: null 不生成替代 id；buildCard({ id: call_n1 }) 原样保留；状态行 buildCard / declared-placeholder / tool_call.id + tool 三键 / n/a / 否 | adapter L16 三入参形状逐项相符；STATUS / KEY 未漂移；C-9 第四节 B-12 只追加登记不涉 buildCard | 一致 |
| C-14 第二节 buildCard 行（L32）与第六节（L113-128） | buildCard(call) / standard_chain_adapter.js / 返回 by=KEY、id、status=STATUS / 一致 / declared-placeholder；第六节只追加 execute 实装登记、STATUS 恒声明态、EXECUTE_STATUS 不进六段断言面 | 签名行逐格在文；第六节未提 buildCard；EXECUTE_STATUS 独立导出作用域不变 | 一致 |
| b10 就绪度表 05g_cards.js 行（L33）与第二节 S2 行（L17） | bridge-chat-call 1 处（L123）、bridge-chat-res 3 处、toolCalls 3 处、toolCall 10 处：建卡与候选 + _translateToolCalls 落 card.toolCall/toolCallId；4 份 js 测试引用 / 步骤 4：state.toolCalls 有执行期下游 | 05g 内行级命中 1 / 3 / 3 / 10 与 b10 全数相符；_translateToolCalls 定义现 L112（b10 快照未逐行标定义行）、汇入现 L132；S2 行仍写 execute 占位属 34e6029 历史快照，19:45 已收紧为第 5 步单点已闭合 | 一致（行号漂移见第四节） |

## 三、git grep 关键串命中计数（实时 6315bf3）

| 关键串 / 口径 | 命中 | 说明 |
|---|---|---|
| .buildCard(（extend/dialog + extend/lib + extend/content + flask_server/core/routes/remote_bridge） | 0 行 / 0 文件 | 标准链 buildCard 无运行期调用方，坐实仍占位 |
| AIMirrorStandardChainAdapter.buildCard（同范围） | 0 行 / 0 文件 | 浏览器全局未装配 buildCard 下游 |
| bridge-chat-call（宽口径：extend + flask_server/tests/js + docs + core + routes） | 96 行 / 42 文件 | 含文档、总线、夹具与活链；不可直接当运行期计数 |
| bridge-chat-call（仅 05g_cards.js） | 1 行（L123） | 与 C-8 第 4 步行旧标记保留、b10 表 1 处（L123）逐字相符 |
| _translateToolCalls（运行期范围） | 2 行 / 1 文件（05g L103 调用、L112 定义） | 建卡末尾唯一接线点 |
| state.toolCalls（运行期范围） | 2 行 / 1 文件（05g L59 回显、L132 汇入）；05g 内 toolCalls 行级 3 | 与 b10 toolCalls 3 处口径一致 |
| card.toolCallId（运行期范围） | 3 行 / 2 文件（05g L127、05j L57/L113） | 刷新恢复与去重下游读回 |
| card.toolCall（运行期范围） | 6 行 / 3 文件（05c L257/L286、05g L108/L127、05j L57/L113） | 含 1 处注释（05g L108） |
| makeToolCallId（同运行期范围） | 6 行 / 4 文件 | 仅 contract.js 定义+导出（L10/L41）与 C-14 / C-11 / C-8 三份文档引用；运行期源码 0 调用 |
| buildCard（全仓宽口径） | 93 行 / 28 文件 | 含 C-8/C-9/C-14/总线/夹具，运行期调用方仍为 0 |

## 四、差异登记（文档标注 vs 代码实况，仅供分发方复核输入）

1. **主结论零差异**：第 4 步 buildCard 仍 declared-placeholder 回显、运行期零调用方；运行期建卡与候选由 05g_cards.js 的 _translateToolCalls 落 card.toolCall / toolCallId 承担；bridge-chat-call 在 05g 内 1 处命中且旧标记保留。三项与 C-8 第 4 步行 / C-9 / C-14 / b10 与实时实仓逐项相符。
2. **b10 历史快照行号漂移（登记项，不阻断）**：b10 证据基线为 34e6029，其 05g_cards.js 行号集（toolCall L47/59/108/127/132/227/324/327/331/338、bridge-chat-call L123、bridge-chat-res L430/431/438）取自该快照；实时 6315bf3 中 _translateToolCalls 定义在 L112、ensureNonce 在 L122、bridge-chat-call 在 L123、card.toolCall/toolCallId 落点在 L127、state.toolCalls 汇入在 L132、bridge-chat-res 三处仍在文件后段。语义与命中计数未变，差异仅为历史快照行号，不构成新前置、不触发摘除或实装动作。
3. **C-8 矩阵 #10 与第二节第 4 步分层**：矩阵 #10 buildCard / dedupe 以 tool_call.id 为唯一键 / 一致 是字段面对拍结论，不等于装配面实装；第二节第 4 步行 仍占位 是装配面标注，二者不矛盾。C-8 第二节为只读推演与状态标注，不是分发方下发过的实装任务书（19:45 口径）。
4. **b10 步骤 4：state.toolCalls 有执行期下游 是前置条件描述**：该列属 c6/c7 九文件摘除顺序表步骤 4 的触发条件，不是当前已满足态。实时 state.toolCalls 仅 2 处（L59 回显、L132 汇入），下游消费者为 05c_prompt / 05j_card_sig 的 card.toolCall 读回；19:45 阶段级重新对拍判 S4 三项硬前置仍未全满足（仅第 5 步单点迁移并验收、摘除任务书未下发、c6 顺序表未执行、九文件全活链零摘除），阶段 3 不进入摘除步。
5. **C-9 抬头与 C-14 第六节并存**：C-9 抬头 六段仍为 declared-placeholder / 运行时执行权仍在旧直调路径 与 C-14 第六节 execute 段实装登记（B-12） 为只追加保留的历史标注与实装登记并存；实装态由 EXECUTE_STATUS 独立导出表达，不涉 buildCard，模块 STATUS 恒 declared-placeholder。按 不改他笔已合入 .md 源码本体 保留原文，不改写、不翻 STATUS。

## 五、边界与结论（复核输入）

- 范围：只新增本报告、flask_server/tests/js/test_standard_chain_c16_step4_inventory.test.js 与 docs/work-ai-c.md 第五节只追加完成记录；零代码改动、0 删除、docs 只追加。
- 活链文件（05g_cards.js / 05j_card_sig.js / 05c_prompt.js / 05f_parse.js / 06_execute.js / 00_data.js / 01b_bridge.js / translator.js / dialog.html / standard_chain_adapter.js / standard_chain_contract.js）零改动；旧标记全部保留；STATUS 恒 declared-placeholder；EXECUTE_STATUS 作用域不变；c6 九文件顺序表未执行。
- 运行时 M 保持未装配；钩子注册数量为零；切换开关数量为零；运行期探测分支数量为零；docs/bus 他人消息零触碰；不碰 C-15 / A-11 / B-13 报告与夹具本体、不碰 extend/dialog/AUDIT.md；hooks / 90-70 阈值 / js_coverage_baseline.json 零改动，未用 --update-baseline。
- 判态锚（19:45 为准，不改写）：S1 不变（L10 接真实模型缺外部服务与凭证、用户侧另行排期）；S2 第 5 步 execute 单点已闭合、整体未齐备 / 待对拍；S3 不变；S4 三项硬前置仍未全满足，阶段 3 不进入摘除步。
- 本报告差异登记与结论仅为分发方复核输入，不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不代分发方拍板、不预设下发时点。

## 六、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| 反查夹具 | node --test flask_server/tests/js/test_standard_chain_c16_step4_inventory.test.js | rc=0，8 tests / 8 pass / 0 fail（第 4 步推演行、buildCard 三入参与零运行期调用方、contract 键映射、C-9 状态行、C-14 签名行与第六节、b10 就绪度表、05g 命中计数与 05j 读回、报告六节） |
| 前端全量 | python scripts/hooks/check_js_tests.py | rc=0，601 tests / 601 pass / 0 fail；分母按新增夹具 8 用例如实增长（C-15 合入后 593 + 本笔 8）；本机 node v24.11.1 前缀差异打印 跳过覆盖率门禁：未解析到覆盖率报告，如实标注为跳过、由分发方环境复验 |
| 结构质量 | python scripts/quality_rules.py | rc=0，十二项全为 已知 存量，零 [新增] |
| 全量 pytest | python -m pytest tests -q -p no:cacheprovider（flask_server 下串行单进程） | rc=0，1085 passed in 27.20s，零 failed（本片无 py 用例，分母不变） |
| 七道钩子 | pre-commit run --all-files | rc=0，语法校验（py / js / json / yaml）........................................Passed；仓库卫生（临时文件 / 超大文件）..........................................Passed；结构质量（十二项检查）...................................................Passed；文档同步（路由 / 工具收录）..............................................Passed；前端逻辑测试（node --test）..............................................Passed；主题副本同步（单一真源）.................................................Passed；依赖漂移校验（requirements）.............................................Passed |
| 差异检查 | git diff --check / git diff --cached --check | 均 rc=0，无空白错误 |
| 范围 | git status --short / git diff --numstat | 2 新文件 + docs/work-ai-c.md 只追加 7 行 / 0 删除；零代码改动 |

> 实测结果以收口轮实跑为准；覆盖率门禁本机 node v24 前缀差异打印 跳过，由分发方环境复验。
