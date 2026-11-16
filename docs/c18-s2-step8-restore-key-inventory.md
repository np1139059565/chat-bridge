# C-18 阶段 3 九步装配面第 8 步刷新恢复键逐行取证报告

> 性质：只读取证判定片。只新增本报告与一份反查夹具，台账第五节只追加；零代码改动。
> 证据基线：实时 origin/main b3c7d97（含 C-17 合入 a25fc98、B-14 合入 4ce0fd1、21:58 PEN_C 验收裁定、22:02 本笔任务书 dispatcher-20261116T220220-a65876、22:18 PEN_B 裁定与 22:22 续派登记）；开工前 git fetch origin --prune + git merge --ff-only origin/main 已完成（22511a9..b3c7d97），工作区干净，身份 actor=c（work/ai-c，旧 tip 22511a9）。
> 只读引用：C-15 c15-s2-remaining-surface-inventory.md 第二节第 8 行、C-9 standard_chain_boundary_contract.md 六段边界与第二节状态行、C-14 standard_chain_c14_signature_table.md 第二节签名行与第六节、C-8 standard_chain_field_matrix.md 第二节九步表第 8 行与对拍矩阵、b10-removal-readiness-report.md 第二 / 三 / 四节、c7-standard-chain-migration-plan.md 第 5 节、c6-direct-path-inventory.md、C-16 / C-17 报告（同型形态）；不改他笔已合入 .md 源码本体。
> 同面隔离：只做九步第 8 步刷新恢复键链路逐行取证；不扩第 6 步回执（a 在途）、不扩第 7 步去重（C-17 已消费）、不扩第 9 步（S3 不变）、不碰六段 adapter.buildCard 声明函数边界反查（b 在途 22:22 续派）、不碰六段 adapter.restore 声明函数边界反查（B-13 已消费）。C-9 restore 边界段与 C-14 restore 签名行仅作标注对拍输入，不取为范围。
> 范围：不是实装授权、不是摘除授权；C-8 第二节仅只读推演；不改写 19:45 / C-16 / C-17 / A-12 / B-14 判态。
> 本报告所有差异登记与结论仅为分发方复核输入：不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。

## 一、第 8 步刷新恢复键逐文件五项判定（落点 / 当前态 / 活调用方 / 依赖 / 禁区）

C-15 第二节第 8 行原文六列：刷新恢复 call_<nonce> 键：05j_card_sig.js / 05g_cards.js（C-7 实改） | 已实改并保持：标准键优先、旧 msgId 兼容双查、去消息指纹；contract.js execKeyFromToolCall（会话 id + nonce + 工具名 + 参数摘要）纯函数在码，运行期恢复仍走旧双查 | 05j_card_sig.js / 05g_cards.js 活链，4 份夹具 | execKeyFromToolCall 接入；c6 顺序表步骤 5；旧标记摘除任务书 | 同第 4 步；已合入实改零改写。实时逐文件展开如下。

| 落点文件 | 当前态（实时 b3c7d97） | 活调用方 | 依赖 | 禁区 |
|---|---|---|---|---|
| extend/dialog/parts/05j_card_sig.js | 刷新恢复主链在码：L24 _executedSig(msgId, call) 取 stdId = call.toolCallId 或 call.id，keyId = stdId || msgId，拼 sigNew（会话 id + keyId + tool + 参数摘要）与 sigOld（会话 id + msgId + 同 tail），按 sigNew 优先、sigOld 回退双查；L55 _markExecutedSig(card) 取 stdId2 = card.toolCallId 或 card.toolCall.id，keyId2 = stdId2 || card.msgId，同键格式登记 executedSigs；L86 _restoreExecutedCards(conv, convId) 取 id = convId 或 activeConv、store = c.executedSigs，L113 keyId = card.toolCallId || card.msgId，L117-118 按 id + keyId + card.tool + JSON.stringify(card.parameters) 拼 sig，命中置 executed / status done / restoredFromSig；L146 cardMatchesBySig 按「工具名 + 参数」匹配、不掺消息指纹 | 05j 内 toolCallId 3 行 / msgId 7 行 / _restoreExecutedCards 1 行（定义）/ executedSigs 4 行（字面子串 5，L62 同行双命中）；会话加载链 04_sessions.js 调 _restoreExecutedCards（c6 L89） | 第 4 步建卡落 card.toolCallId（C-16 已取证）；c6 顺序表步骤 5 / c7 第 5 节「execKeyFromToolCall 接入且 executedSigs 去消息指纹」 | 活链零改动；标准 call_<nonce> 优先 + 旧 msgId 兼容双查构型保持；不摘除旧键回退、不接入 execKeyFromToolCall |
| extend/dialog/parts/05g_cards.js | 建卡侧落标准键：L127 由 T.toToolCalls 命中后 card.toolCall = calls[0]、card.toolCallId = calls[0].id；L221 注释「标准 tool_call.id 优先（call_<nonce>），05j 双查回退旧 msgId 键兼容旧存档 / 夹具」；L227 holder.cards[b.id].toolCallId = call.toolCallId = cid ? cid(nonce) : call_ 前缀拼 nonce；L228 const doneSig = this._executedSig(this.msgId(m), call)；L229-232 命中签名即置 executed / done / restoredFromSig | 05g 内 card.toolCallId 1 行（L127）；L227 经 call.toolCallId 回写；C-7 实改构型在码 | 第 4 步建卡候选（C-16）；05j 双查签名库 | 活链零改动；bridge-chat-call 旧信封与 call_ 前缀构型保持；不摘除旧标记 |
| extend/lib/standard_chain_contract.js | L19-26 execKeyFromToolCall(call, sessionId) 纯函数在码：nonceFromToolCallId(call.id) 反解 nonce、取 tool 或 function.name、参数 JSON.stringify 摘要（catch 回落 String），返回 [会话 id, nonce, 工具名, 参数摘要].join 竖线，L18 注释明确「不含消息指纹」；L41-44 模块导出含 execKeyFromToolCall / makeToolCallId / nonceFromToolCallId / standardToolMessage | 运行期精确串 execKeyFromToolCall 在 parts + dialog.html + core + routes 全 0 命中；仅契约夹具与 C-14 签名表 / crossref 文档引用（全仓宽口径 35 行 22 文件，lib 与文档侧 4 行） | 无（纯函数契约面，未接入运行期） | 零改动；不装配运行时 M；不把纯函数接进 05j / 05g 活链 |
| extend/lib/standard_chain_adapter.js | L61-63 restore(sessionId, call) 返回 by=KEY、sessionId = String(sessionId || 空)、id = call.id 或 null、noMessageFingerprint 恒 true、status = STATUS；L74 导出；L12 STATUS = declared-placeholder、L13 EXECUTE_STATUS = implemented-S2-step5 独立导出、L14 KEY = tool_call.id | 运行期精确串 AIMirrorStandardChainAdapter.restore / adapter.restore( / AD.restore( / Adapter.restore( / .restore( 在 parts + dialog.html + 两个 lib + core + routes 全 0 命中 | 无（声明态）；六段 restore 边界反查由 B-13 已消费 | 零改动；STATUS 恒 declared-placeholder；不扩用 EXECUTE_STATUS 到 restore；不把本函数边界当本片范围 |
| extend/lib/standard_chain_boundary_contract.md | C-9 第一部分 ### 6. restore(sessionId, call)（L75）四行边界：空 sessionId 归一为空串、noMessageFingerprint 恒真（G4）、重复恢复幂等每次新对象、缺 call 时 id 为 null；L84-85 说明与 05j / 05g 实改方向一致、本段只钉声明语义不改运行时；第二节 L96 状态行 restore / declared-placeholder / tool_call.id + tool 三键 / true（恒真）/ 否 | 仅标注对拍输入，非运行期装配 | 无 | 不改他笔已合入 .md 源码本体；仅作标注，不取为范围 |
| extend/lib/standard_chain_c14_signature_table.md | C-14 第二节 L36 restore 签名行（返回 by=KEY、sessionId、id、noMessageFingerprint=true、status=STATUS / 一致 / declared-placeholder）、L46 execKeyFromToolCall(call,sessionId) 行（会话 id + call_<nonce> 反解 nonce + 工具名 + 参数摘要，noMessageFingerprint）、L30 六段接口名含 restore、L84 C-9 六段边界含 restore；第六节 L113 起为 execute 段实装登记（B-12），不含 restore 断言面 | 仅标注对拍输入 | 无 | 同上；不取为范围 |
| extend/lib/standard_chain_field_matrix.md | C-8 第二节九步表 L50 第 8 行：刷新恢复 call_<nonce> 键 | 05j_card_sig.js 与 05g_cards.js（C-7 实改） | 已实改（标准键优先、旧 msgId 兼容双查、去消息指纹），不切活链 | 否；另 L26 对拍矩阵 #8「规范化追加 _normalize_item」与 L30 #12「restore 段」为不同口径（见第四节差异 5） | 只读推演、不作实装授权 | 不改他笔已合入 .md 源码本体；19:45 口径不从零定义范围 |
| docs/b10-removal-readiness-report.md / c7 / c6 | b10 第三节 L34 05j 行登记 toolCall 3 处（L26/57/113）、标准键 + msgId 旧键双查、4 份 js 测试引用、步骤 5；L43 刷新恢复链须先统一恢复键（c7 第 5 节）；第二节 L19 S4 三项硬前置；c7 L27 第 5 组「执行、去重、恢复」判据 execKeyFromToolCall 接入且 executedSigs 去消息指纹；c6 L36 executedSigs 落盘与 L89-90 恢复 / 幽灵卡复核 | 断言面与就绪度登记，非运行期装配 | c6 顺序表步骤 5 未执行 | 不改他笔已合入 .md 源码本体；不执行 c6 九文件顺序表 |
| flask_server/tests/js/ 与 docs/ | C-15 第 8 行登记 4 份夹具（C-7 时代 4 份：test_card_sig_restore / test_clear_sessions_sig / test_05j_card_sig_coverage / test_scroll_autoexec）；实时引用 05j_card_sig.js 的 js 夹具为 9 份（含 A-12 / B-13 / B-14 / C-16 / C-17 / field_matrix 等后续新增），口径差见第四节差异 4；本片新增独立命名反查夹具 1 份 | 断言面，非运行期装配 | 无 | 不碰 C-15 / C-16 / C-17 / A-11 / B-13 / A-12 / B-14 报告与夹具本体与 card_sig 先例族 test_card_sig_restore.test.js、不碰 extend/dialog/AUDIT.md |

## 二、与 C-15 / C-9 / C-14 / C-8 / b10 / c7 / c6 逐行对拍

| 对拍源 | 原文锚点 | 实时实况 | 判定 |
|---|---|---|---|
| C-15 第二节第 8 行（L35） | 已实改并保持标准键优先 / 旧 msgId 兼容双查 / 去消息指纹；contract.js execKeyFromToolCall 纯函数在码，运行期恢复仍走旧双查 | 05j L24 / L55 / L113 与 05g L127 / L227 双链在码；contract L19-26 纯函数在码但活链运行期零命中；adapter.restore 声明态 | 一致 |
| C-15 第 8 行依赖 / 禁区列 | execKeyFromToolCall 接入；c6 顺序表步骤 5；旧标记摘除任务书；同第 4 步；已合入实改零改写 | execKeyFromToolCall 未接入、c6 步骤 5 未执行、摘除任务书未下发；C-7 实改构型未变 | 一致（前置未满足态） |
| C-9 ### 6. restore 边界段（L75-85）与第二节 L96 状态行 | 空 sessionId 归一、noMessageFingerprint 恒真、幂等新对象、缺 call 为 null；restore 状态行 declared-placeholder / true（恒真）/ 否 | adapter L61-63 四入参形状逐项相符；STATUS / KEY 未漂移；运行期零调用方 | 一致（仅标注对拍输入，不取为范围） |
| C-14 第二节 L36 restore 签名行 / L46 execKeyFromToolCall 行 | 返回 by=KEY、sessionId、id、noMessageFingerprint=true、status=STATUS；会话 id + nonce + 工具名 + 参数摘要 | 签名行逐格在文；第六节仅 execute 段实装登记（B-12）、不含 restore 断言面；EXECUTE_STATUS 独立导出作用域不变 | 一致（仅标注对拍输入，不取为范围） |
| C-8 第二节九步表第 8 行（L50） | 刷新恢复 call_<nonce> 键 / 05j 与 05g（C-7 实改）/ 已实改不切活链 / 依赖否 | 05j / 05g 实改在码、活链旧链承担恢复、不切活链 | 一致（只读推演，不作实装授权） |
| b10 第三节 05j 行（L34）与 L43 刷新恢复链 | toolCall 3 处（L26/57/113）、双查构型、4 份夹具、c7 第 5 节统一恢复键 | 实时 toolCallId 3 / msgId 7 / _restoreExecutedCards 1 / executedSigs 4；_executedSig 现 L24、_markExecutedSig 现 L55、_restoreExecutedCards 定义现 L86（L113 仍为 keyId 行），语义未变 | 一致（行号漂移见第四节） |
| c7 第 5 节（L27）与 c6 步骤 5（L36 / L89-90） | execKeyFromToolCall 接入且 executedSigs 去消息指纹；executedSigs 落盘、_restoreExecutedCards 补判 | 判据行在文；运行期恢复仍走旧双查、纯函数未接入、executedSigs 仍落盘 | 一致（仅作就绪度基线，未执行） |

## 三、git grep 关键串命中计数（实时 b3c7d97）

| 关键串 / 口径 | 命中 | 说明 |
|---|---|---|
| | 8 | 刷新恢复（C-15 第二节前缀） | 1 行 | 本片主锚恰 1 行（L35） |
| execKeyFromToolCall（parts + dialog.html + core + routes 活链运行期） | 0 行 / 0 文件 | 纯函数未接入运行期，坐实运行期恢复仍走旧双查 |
| execKeyFromToolCall（extend + docs + flask_server/tests/js 宽口径） | 35 行 / 22 文件 | 含契约夹具 / 报告 / 索引；其中 lib 与契约文档侧 4 行（contract L19 / L42、C-14 L46、crossref L11） |
| AIMirrorStandardChainAdapter.restore / adapter.restore( / AD.restore( / Adapter.restore( / .restore(（parts + html + 两个 lib + core + routes） | 各 0 行 / 0 文件 | 六段 restore 运行期零调用方，STATUS 恒声明态 |
| toolCallId（仅 05j_card_sig.js） | 3 行 | L26 / L57 / L113，与 b10 toolCall 3 处相符 |
| msgId（仅 05j_card_sig.js） | 7 行 | 旧键兼容双查面 |
| _restoreExecutedCards（仅 05j_card_sig.js） | 1 行（L86 定义） | 调用方在 04_sessions.js 会话加载链（c6 L89） |
| executedSigs（仅 05j_card_sig.js） | 4 行（L62 同行双命中，字面子串 5） | 签名库读写面 |
| card.toolCallId（仅 05g_cards.js） | 1 行（L127） | 建卡候选落标准键；L227 为 holder.cards[b.id].toolCallId 不同字面 |
| restore（C-9 状态行 / C-14 签名行 / 六段接口名） | 分布 4 行 | 仅标注对拍输入，运行期调用方 0 |
| | 5 | execKeyFromToolCall（c7 宽口径） | 若干 | 就绪度判据行，未执行 c6 顺序表 |

## 四、差异登记（文档标注 vs 代码实况，仅供分发方复核输入）

1. **主结论零差异**：第 8 步「05j / 05g 已实改并保持标准键优先 + 旧 msgId 兼容双查 + 去消息指纹」「contract.execKeyFromToolCall 纯函数在码」「运行期恢复仍走旧双查、纯函数未接入」三项，与 C-15 第 8 行 / C-9 状态行 / C-14 签名行 / C-8 九步表 / b10 就绪度表 / c7 第 5 节与实时实仓逐项相符。
2. **任务书「C-9 第五节边界段」为编号措辞差（登记项，不阻断）**：22:02 任务书写「C-9 第五节边界段（仅作标注对拍输入）」，实仓 C-9 第一部分 ### 5. dedupe(a, b)（L65）为 dedupe 段、### 6. restore(sessionId, call)（L75）才是刷新恢复键边界段，第二节状态行在 L96。本片按实仓真实锚点 ### 6 取证并用夹具断言，不改写任务书措辞、不擅自扩范围；按 A-9 双闸门判为措辞差而非硬约束冲突，不触发 question。
3. **同面隔离（19:08 / 22:02 分发方已判，不改写）**：九步第 8 步装配面取证对象为 05j / 05g 活链刷新恢复链路 + contract 纯函数未接入；六段 adapter.restore 声明函数边界反查（B-13 已消费）、六段 adapter.buildCard 声明函数边界反查（b 22:22 在途）取证对象为纯声明函数返回形状 / STATUS / KEY / 零调用方。本片把 C-9 restore 边界段与 C-14 签名行仅作标注对拍输入，不写六段 restore 边界反查夹具、不扩为范围。C-14 第六节仅 execute 段实装登记（B-12），不含 restore 断言面，亦如实登记。
4. **C-15 第 8 行「4 份夹具」为历史快照计数**：C-15 / b10 基线为 c817dea / 34e6029，4 份精确名为 C-7 时代 test_card_sig_restore.test.js / test_clear_sessions_sig.test.js / test_05j_card_sig_coverage.test.js / test_scroll_autoexec.test.js；实时引用 05j_card_sig.js 的 js 夹具为 9 份（含 A-12 / B-13 / B-14 / C-16 / C-17 / field_matrix 后续新增）。本片不新增活链夹具、不改写该列；新增 1 份独立命名反查夹具使 check_js_tests.py 分母按用例数如实增长（当前 main 633 + 本笔），与活链夹具计数不是同一口径。
5. **b10 / C-15 历史快照行号漂移与 C-8 编号口径（登记项，不阻断）**：b10 L34 标 toolCall 3 处 L26/57/113，实时 _executedSig 在 L24、_markExecutedSig 在 L55、_restoreExecutedCards 定义在 L86（L113 仍为 keyId 行）；命中计数（git grep 行数口径）3 / 7 / 1 / 4 全数未变；executedSigs 字面子串 5 系 L62 同行双命中，非实仓漂移。C-8 内 #8「规范化追加」、#12「restore 段」与九步表第 8 行「刷新恢复键」为三处不同编号口径，仅登记区分、不混作本片范围。差异仅为历史快照与编号措辞，不构成新前置、不触发摘除或实装动作。
6. **S4 判态不变**：三项硬前置（执行权已迁标准链且分发方验收 / 摘除任务书下发 / 按 c6 九文件顺序表执行）仍未全满足，阶段 3 不进入摘除步。C-7 已实改的刷新恢复链不等于执行权迁移，execKeyFromToolCall 纯函数在码亦不等于已接入；第 8 步只读取证不构成执行权迁移、不构成新前置、不构成实装或摘除授权。b10 S2 行与 C-8 第 5 步行历史措辞并存按「不改他笔已合入 .md 源码本体」保留原文，不翻 STATUS；EXECUTE_STATUS 独立导出作用域不变。

## 五、边界与结论（复核输入）

- 范围：只新增本报告、flask_server/tests/js/test_standard_chain_c18_step8_restore_key_inventory.test.js 与 docs/work-ai-c.md 第五节只追加完成记录；零代码改动、0 删除、docs 只追加。只做九步第 8 步一步，不扩第 6 / 7 / 9 步、不扩六段 buildCard / restore 声明函数边界反查、不扩 S1 L10。
- 活链九文件（06_execute.js / 05f_parse.js / 00_data.js / 05g_cards.js / 05j_card_sig.js / 05c_prompt.js / 01b_bridge.js / translator.js / dialog.html）与 standard_chain_adapter.js / standard_chain_contract.js 本体零改动（只读反查除外）；旧标记全部保留；STATUS 恒 declared-placeholder；EXECUTE_STATUS 作用域不变；c6 九文件顺序表未执行。
- 运行时 M 保持未装配；钩子注册数量为零；切换开关数量为零；运行期探测分支数量为零；docs/bus 他人消息零触碰；不碰 C-15 / C-16 / C-17 / A-11 / B-13 / A-12 / B-14 报告与夹具本体、card_sig 先例族 test_card_sig_restore.test.js 与 extend/dialog/AUDIT.md；hooks / 90-70 阈值 / js_coverage_baseline.json 零改动，未用 --update-baseline。
- 反查夹具按 C-14 / C-16 / A-12 / B-14 / C-17 形态：按字符码 10 切行、普通 indexOf / split、零反斜杠零正则、只读 require node:* 与两个已合入 lib、无 fs 写 / shell / 网络、新增被测 JS 源 0；require 头部序按 A-10 口径与 a11 / a12 / b13 / b14 / c16 / c17 同族差异化归零，避免收口轮防重窗返工。
- 判态锚（19:45 为准，不改写）：S1 不变（L10 接真实模型缺外部服务与凭证、用户侧另行排期）；S2 第 5 步 execute 单点已闭合、整体未齐备 / 待对拍；S3 不变；S4 三项硬前置仍未全满足，阶段 3 不进入摘除步。
- 本报告差异登记与结论仅为分发方复核输入，不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不代分发方拍板、不预设下发时点。

## 六、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| 反查夹具 | node --test flask_server/tests/js/test_standard_chain_c18_step8_restore_key_inventory.test.js | rc=0，10 tests / 10 pass / 0 fail；第 7 条 executedSigs 双口径（git grep 行数 4 / split 字面子串 5，L62 同行双命中）订正后全绿 |
| 前端全量 | python scripts/hooks/check_js_tests.py | rc=0，643 tests / 643 pass / 0 fail；分母按新增夹具 10 用例如实增长（当前 main 633 = 611 + C-17 10 + B-14 12，+ 本笔 10）；本机 node v24.11.1 打印 跳过覆盖率门禁：未解析到覆盖率报告，如实标注为跳过、由分发方环境复验 |
| 结构质量 | python scripts/quality_rules.py | rc=0，十二项全为 已知 存量，零 [新增]；A-10 防重窗 require 序差异化归零坐实 |
| 全量 pytest | python -m pytest tests -q -p no:cacheprovider（flask_server 下串行单进程） | rc=0，1085 passed，零 failed（本片无 py 用例，分母不变） |
| 七道钩子 | pre-commit run --all-files | rc=0，7 道逐个 Passed，Failed=0，未用 --no-verify |
| 文档同步 | python scripts/check_doc_sync.py | rc=0，单独命令实跑通过（pre-commit 文档同步道亦 Passed） |
| 差异检查 | git diff --check / git diff --cached --check | 均 rc=0，无空白错误 |
| 范围 | git status --short / git diff --numstat | 2 新文件 + docs/work-ai-c.md 只追加 7 行 / 0 删除；零代码改动 |

> 实测结果以收口轮实跑为准；覆盖率门禁本机 node v24 打印跳过，由分发方环境复验。
