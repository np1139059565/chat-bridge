# C-17 阶段 3 九步装配面第 7 步去重逐行取证报告

> 性质：只读取证判定片。只新增本报告与一份反查夹具，台账第五节只追加；零代码改动。
> 证据基线：实时 origin/main 2fed217（含 A-12 合入 a4d9f2d、19:08 B-14 任务书登记 55d94d0、20:26 / 20:27 两笔并行补派任务书本笔 dispatcher-20261116T202702-d19473）；开工前 git fetch origin --prune + git merge --ff-only origin/main 已完成，工作区干净，身份 actor=c（work/ai-c）。
> 只读引用：C-15 c15-s2-remaining-surface-inventory.md 第二节第 7 行与逐面小结、C-9 standard_chain_boundary_contract.md 第五节与第二节状态行、C-14 standard_chain_c14_signature_table.md 第二节 dedupe 签名行、b10-removal-readiness-report.md 第二 / 三 / 四节、C-8 standard_chain_field_matrix.md 第二节第 7 步行、c6-direct-path-inventory.md、c7-standard-chain-migration-plan.md、C-16 c16-s2-step4-card-build-inventory.md（同型形态）；不改他笔已合入 .md 源码本体。
> 同面隔离：只做九步第 7 步去重装配链路逐行取证；不扩第 6 步回执（a 在途）、不扩第 8 / 9 步、不碰六段 adapter.dedupe 声明函数边界反查（b 在途）。C-9 第五节 dedupe 边界段与 C-14 dedupe 签名行仅作「前端 dedupe 仍声明态」标注对拍输入，不取为本片范围。
> 范围：不是实装授权、不是摘除授权；C-8 第二节仅只读推演、不作实装授权；不改写 19:45 / C-16 / A-12 判态。
> 本报告所有差异登记与结论仅为分发方复核输入：不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。

## 一、第 7 步去重逐文件五项判定（落点 / 当前态 / 活调用方 / 依赖 / 禁区）

C-15 第二节第 7 行原文六列：去重 | adapter.dedupe；core/chat_completions.py pending_tool_calls | 服务端按 tool_call_id 配对防重放已实交付；前端 dedupe 仍声明态；前端去重由 00_data.js（nonce 配对 external-call / bridge-chat-res、buildTimeline 折叠）与 05j_card_sig.js（标准 call_<nonce> + 旧 msgId 双查）承担 | 00_data.js 3 份夹具、05j_card_sig.js 4 份夹具 | 第 4 / 6 步键落运行期；刷新恢复键统一（c7 第 5 节）；c6 顺序表步骤 2 / 5 | 同第 4 步；executedSigs 双查构型保持。实时逐文件展开如下。

| 落点文件 | 当前态（实时 2fed217） | 活调用方 | 依赖 | 禁区 |
|---|---|---|---|---|
| flask_server/core/chat_completions.py | L155 _pending_key(tc, answered, seen) 归一化 tc 的 id 字段，无 id / 已回填 / 本轮已收返回 None；L163 pending_tool_calls(messages) 取 _answered_call_ids(messages) 为 answered，遍历 messages 仅取 role 为 assistant 的 tool_calls（非 dict 跳过），对每个 tc 调 _pending_key，命中则 seen.add(key) 并 out.append(tc)，按提交顺序返回；文档字符串明确「防重放以 tool_call_id 配对、已回填不再重复执行、客户端重发全量历史天然幂等、同一 id 多次声明以首次为准、无 id 跳过」 | flask_server/routes/chat_api.py L142 _execute_pending 调 cc.pending_tool_calls(history)；core L163 定义；chat_api L138 注释 | A-4 标准链路；第 6 步 tool 消息回执（a 在途）提供已回填 tool 结果 | 零改动；不碰服务端防重放判定；不改 _pending_key / seen 语义 |
| flask_server/routes/chat_api.py | L135 _execute_pending(history)：for call in cc.pending_tool_calls(history) 逐个 cc.execute_tool_call(call)，再 cc.tool_message_from_call(call, body) 追加 round_messages；L138 注释「防重放由 cc.pending_tool_calls 按 tool_call_id 配对完成」 | 分发前钩子链 _run_pre_dispatch_hooks 后由路由调用；3 行命中（定义 L135 / 注释 L138 / 调用 L142） | 服务端已实交付，无外部前置 | 零改动；不碰路由执行编排 |
| extend/lib/standard_chain_adapter.js | L12 STATUS=declared-placeholder、L13 EXECUTE_STATUS=implemented-S2-step5 独立导出、L14 KEY=tool_call.id；L60 dedupe(a, b) 返回 { by: KEY, a: a || null, b: b || null, status: STATUS }，同 id 与异 id 均原样回显不吞并、不比较、不排序、不去重，null 入参缺失侧回落 null 不抛错；L73 导出 | 运行期精确串 AIMirrorStandardChainAdapter.dedupe / adapter.dedupe( / AD.dedupe( / Adapter.dedupe( / .dedupe( 在 extend/dialog 与 extend/lib 与 flask_server/core/routes 全 0 命中；仅契约夹具经 node 分支 require | 无（声明态）；六段 dedupe 边界反查归 b（B-14 在途） | 零改动；STATUS 保持 declared-placeholder；不扩用 EXECUTE_STATUS 到 dedupe；不把本函数边界当本片范围 |
| extend/dialog/parts/00_data.js | 镜像区去重主链：L57 D.cardHasMessage(conv, card) 对未 executed 或无 nonce 返回 false，遍历 msgTree 的 user 节点 blocks，JSON.parse 后按 obj.type 为 external-call 或 bridge-chat-res 且 obj.nonce === card.nonce 判为已有消息本体（避免同一卡片数组态 + 消息本体态重复渲染）；L110 D.buildTimeline 用 externalCards.filter 调 !D.cardHasMessage(conv, c) 折叠，再按 anchorKey 分桶 / orphan 排列；L174 toolMsgOpen 折叠 bridge-chat-res 大 JSON 注释 | 00_data.js 内 bridge-chat-res 3 行 / external-call 3 行 / buildTimeline 1 行；C-15 第 7 行登记 3 份 js 夹具引用；b10 第三节登记 3 份 | 第 4 步键落运行期（card.toolCallId 由 05g L127 落）；c6 顺序表步骤 2（nonce 配对改 tool_call.id 配对）；刷新恢复键统一 | 活链零改动；nonce 配对与折叠构型保持；不摘除 bridge-chat-res / external-call 旧标记 |
| extend/dialog/parts/05j_card_sig.js | 执行签名双查去重主链：L24 _executedSig(msgId, call) 取 stdId = call.toolCallId 或 call.id，keyId = stdId || msgId，拼 sigNew（会话 id + keyId + tool + 参数摘要）与 sigOld（会话 id + msgId + 同 tail），按 sigNew 优先、sigOld 回退查 executedSigs；L55 _markExecutedSig(card) 取 stdId2 = card.toolCallId 或 card.toolCall.id，keyId2 = stdId2 || card.msgId，按同键格式登记；L113 _restoreExecutedCards 取 keyId = card.toolCallId || card.msgId 纠正刷新后执行态；建键均不含消息指纹之外的字段、去消息指纹方向一致（C-7 实改构型仍在码） | 05j 内 _executedSig 3 行 / toolCallId 3 行 / msgId 7 行；C-15 第 7 行登记 4 份 js 夹具引用；b10 第三节登记 4 份 | c6 顺序表步骤 5（execKeyFromToolCall 接入且 executedSigs 去消息指纹）；第 8 步刷新恢复键统一 | 活链零改动；标准 call_<nonce> + 旧 msgId 双查构型保持；不摘除旧键回退 |
| extend/lib/standard_chain_boundary_contract.md | C-9 第五节 ### 5. dedupe(a, b) 四行边界：同 call_<nonce> id 原样回显、占位期不做判重决策不吞并；不同 id 原样回显、不比较不排序不去重；null 入参缺失侧回落 null 不抛错；说明「唯一键标准下同 id 即同一调用的判定留给后续实装，本期只保证形状稳定」。第二节 L95 状态行 dedupe / declared-placeholder / tool_call.id + tool 三键 / n/a / 否 | 仅标注对拍输入，非运行期装配 | 无 | 不改他笔已合入 .md 源码本体；仅作前端 dedupe 仍声明态标注，不取为范围 |
| extend/lib/standard_chain_c14_signature_table.md | C-14 第二节 L35 签名行 dedupe(a,b) / standard_chain_adapter.js / 返回 by=KEY、a、b、status=STATUS / 一致 / declared-placeholder；L30 六段接口名含 dedupe；L84 C-9 六段边界含 dedupe | 仅标注对拍输入 | 无 | 同上；不取为范围 |
| extend/lib/standard_chain_field_matrix.md | C-8 第二节第 7 步行：去重 | standard_chain_adapter.js dedupe；服务端 core/chat_completions.py pending_tool_calls | 服务端已实交付；前端去重仍占位（历史快照措辞） | 依赖 B-7 否 | 只读推演、不作实装授权 | 不改他笔已合入 .md 源码本体；19:45 口径不从零定义范围 |
| flask_server/tests/js/ 与 docs/ | C-15 第 7 行登记 00_data.js 3 份夹具、05j_card_sig.js 4 份夹具；b10 第三节同数；本片新增独立命名反查夹具 1 份 | 断言面，非运行期装配 | 无 | 不碰 C-15 / C-16 / A-11 / B-13 / A-12 报告与夹具本体与 card_sig 先例族 test_card_sig_restore.test.js、不碰 extend/dialog/AUDIT.md |

## 二、与 C-15 / C-9 / C-14 / b10 逐行对拍

| 对拍源 | 原文锚点 | 实时实况 | 判定 |
|---|---|---|---|
| C-15 第二节第 7 行（L34） | 服务端按 tool_call_id 配对防重放已实交付；前端 dedupe 仍声明态；前端去重由 00_data.js 与 05j_card_sig.js 承担 | core L155-184 + chat_api L135-145 服务端配对链在码；adapter.dedupe L60 声明回显、运行期五精确串全 0；00_data L57/L110 + 05j L24/L55/L113 双链在码 | 一致 |
| C-15 第 7 行依赖 / 禁区列 | 第 4 / 6 步键落运行期；刷新恢复键统一（c7 第 5 节）；c6 顺序表步骤 2 / 5；同第 4 步；executedSigs 双查构型保持 | 第 4 步 C-16 已取证（05g L127 落 card.toolCallId）；第 6 步 a 在途；c6 步骤 2 / 5 未执行；05j 双查构型未变 | 一致（前置未满足态） |
| C-9 第五节 dedupe 边界段（L65-73）与第二节状态行（L95） | 同 / 异 id 原样回显不吞并、null 回落不抛错、占位期不做判重决策；dedupe 状态行 declared-placeholder / 否 | adapter L60 四入参形状逐项相符；STATUS / KEY 未漂移；运行期零调用方 | 一致（仅标注对拍输入，不取为范围） |
| C-14 第二节 dedupe 签名行（L35） | 返回 by=KEY、a、b、status=STATUS / 一致 / declared-placeholder | 签名行逐格在文；第六节 B-12 只追加登记未提 dedupe；EXECUTE_STATUS 独立导出作用域不变 | 一致（仅标注对拍输入，不取为范围） |
| b10 第三节 00_data.js 行（L27）与 05j_card_sig.js 行（L34） | 00_data：bridge-chat-res 3 处、external-call 3 处、cardHasMessage 按 nonce 配对、buildTimeline 去重、3 份夹具 / c6 步骤 2；05j：toolCall 3 处、标准键 + msgId 旧键双查、4 份夹具 / c6 步骤 5 | 实时命中 3 / 3 / 1 与 3 / 3 / 7 全数相符；_executedSig 现 L24、_markExecutedSig 现 L55、_restoreExecutedCards 现 L113（b10 快照标 L26/L57/L113），语义未变 | 一致（行号漂移见第四节） |
| C-8 第二节第 7 步行 | 服务端已实交付；前端去重仍占位（历史快照措辞） | 服务端配对链在码、前端 dedupe 声明态、活链旧链承担去重 | 一致（只读推演，不作实装授权） |

## 三、git grep 关键串命中计数（实时 2fed217）

| 关键串 / 口径 | 命中 | 说明 |
|---|---|---|
| pending_tool_calls（core + routes） | 3 行 / 2 文件 | core L163 定义、chat_api L138 注释、L142 调用 |
| tool_call_id（core + routes） | 10 行 / 2 文件 | 服务端配对键字段面 |
| AIMirrorStandardChainAdapter.dedupe / adapter.dedupe( / AD.dedupe( / Adapter.dedupe( / .dedupe(（extend/dialog + extend/lib + core + routes） | 各 0 行 / 0 文件 | 六段 dedupe 运行期零调用方，坐实前端 dedupe 仍声明态 |
| bridge-chat-res（仅 00_data.js） | 3 行 | L71 注释 / L73 判定 / L174 折叠注释，与 b10 3 处相符 |
| external-call（仅 00_data.js） | 3 行 | L50 / L73 / L113，与 b10 3 处相符 |
| buildTimeline（仅 00_data.js） | 1 行（L110） | 折叠入口唯一定义 |
| _executedSig（仅 05j_card_sig.js） | 3 行 | 双查签名函数 |
| toolCallId（仅 05j_card_sig.js） | 3 行 | L26 / L57 / L113，与 b10 toolCall 3 处相符 |
| msgId（仅 05j_card_sig.js） | 7 行 | 旧键兼容双查面 |
| dedupe（adapter + C-9 + C-14 三文件） | 7 行 / 3 文件 | 含定义 / 导出 / 边界段 / 状态行 / 签名行 / 六段接口名，运行期调用方仍 0 |
| 第 7 行锚（docs + extend/lib 宽口径 | 7 |） | 14 行 | 含九步表 / 对拍表 / 就绪度表等历史引用；C-15 第二节本片锚点恰 1 行（L34） |

## 四、差异登记（文档标注 vs 代码实况，仅供分发方复核输入）

1. **主结论零差异**：第 7 步「服务端 pending_tool_calls 按 tool_call_id 配对防重放已实交付」「前端 dedupe 仍 declared-placeholder 声明态、运行期零调用方」「前端去重由 00_data.js nonce 配对 + buildTimeline 折叠与 05j_card_sig.js 标准键 + 旧 msgId 双查承担」三项，与 C-15 第 7 行 / C-9 状态行 / C-14 签名行 / b10 就绪度表与实时实仓逐项相符。
2. **同面隔离（19:08 分发方已判，不改写）**：九步第 7 步装配面取证对象为服务端配对链 + 前端活链去重链路；六段 adapter.dedupe 声明函数边界反查（b 在途 B-14）取证对象为纯声明函数返回形状 / STATUS / KEY / 零调用方。两者对象、锚点、夹具、交付文件全不同，不构成重复交付。本片把 C-9 第五节与 C-14 签名行仅作「前端 dedupe 仍声明态」标注对拍输入，不写六段 dedupe 边界反查夹具、不扩为范围。
3. **b10 / C-15 历史快照行号漂移（登记项，不阻断）**：b10 与 C-15 证据基线为 34e6029 / c817dea，00_data 行标 bridge-chat-res L71/73/174、external-call L50/73/113，05j 行标 toolCall L26/57/113；实时 2fed217 中 D.cardHasMessage 在 L57、判定在 L73、buildTimeline 在 L110、折叠注释在 L174，_executedSig 在 L24、_markExecutedSig 在 L55、_restoreExecutedCards 在 L113。命中计数 3 / 3 / 1 与 3 / 3 / 7 全数未变，差异仅为历史快照行号，不构成新前置、不触发摘除或实装动作。
4. **C-15 第 7 行「00_data.js 3 份夹具、05j_card_sig.js 4 份夹具」为活调用方列历史计数**：本片不新增活链夹具、不改写该列；新增 1 份独立命名反查夹具使 check_js_tests.py 分母按用例数如实增长（611 + 本笔），与活链夹具计数不是同一口径。
5. **b10 S2 行与 C-8 第 5 步行历史措辞并存**：b10 L17「装配面九步第 5 步仍 declared-placeholder / execute(card) 返回占位」与 C-8 第 5 步行「仍占位」属 34e6029 历史快照，19:45 已收紧为第 5 步单点已闭合（B-12，分发方 a0cb2f0 验收），C-15 第 25 行亦登记并存。按「不改他笔已合入 .md 源码本体」保留原文，不改写、不翻 STATUS；EXECUTE_STATUS 独立导出作用域不变。
6. **S4 判态不变**：三项硬前置（执行权已迁标准链且分发方验收 / 摘除任务书下发 / 按 c6 九文件顺序表执行）仍未全满足，阶段 3 不进入摘除步。服务端 pending_tool_calls 已实交付不等于执行权迁移；第 7 步只读取证不构成执行权迁移、不构成新前置、不构成实装授权。

## 五、边界与结论（复核输入）

- 范围：只新增本报告、flask_server/tests/js/test_standard_chain_c17_step7_dedupe_inventory.test.js 与 docs/work-ai-c.md 第五节只追加完成记录；零代码改动、0 删除、docs 只追加。只做九步第 7 步一步，不扩第 6 / 8 / 9 步、不扩六段 dedupe 声明函数边界反查、不扩 S1 L10。
- 活链九文件（06_execute.js / 05f_parse.js / 00_data.js / 05g_cards.js / 05j_card_sig.js / 05c_prompt.js / 01b_bridge.js / translator.js / dialog.html）与 standard_chain_adapter.js / standard_chain_contract.js 本体零改动（只读反查除外）；旧标记全部保留；STATUS 恒 declared-placeholder；EXECUTE_STATUS 作用域不变；c6 九文件顺序表未执行。
- 运行时 M 保持未装配；钩子注册数量为零；切换开关数量为零；运行期探测分支数量为零；docs/bus 他人消息零触碰；不碰 C-15 / C-16 / A-11 / B-13 / A-12 报告与夹具本体、card_sig 先例族 test_card_sig_restore.test.js 与 extend/dialog/AUDIT.md；hooks / 90-70 阈值 / js_coverage_baseline.json 零改动，未用 --update-baseline。
- 反查夹具按 C-14 / C-16 / A-12 形态：按字符码 10 切行、普通 indexOf / split、零反斜杠零正则、只读 require node:* 与两个已合入 lib、无 fs 写 / shell / 网络、新增被测 JS 源 0；require 头部序按 A-10 口径与 a11 / a12 / b13 / boundary / c16 同族差异化归零，避免收口轮防重窗返工。
- 判态锚（19:45 为准，不改写）：S1 不变（L10 接真实模型缺外部服务与凭证、用户侧另行排期）；S2 第 5 步 execute 单点已闭合、整体未齐备 / 待对拍；S3 不变；S4 三项硬前置仍未全满足，阶段 3 不进入摘除步。
- 本报告差异登记与结论仅为分发方复核输入，不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不代分发方拍板、不预设下发时点。

## 六、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| 反查夹具 | node --test flask_server/tests/js/test_standard_chain_c17_step7_dedupe_inventory.test.js | rc=0，10 tests / 10 pass / 0 fail（C-15 第 7 行六列、服务端配对链、adapter.dedupe 声明回显、运行期五精确串递归扫零命中、00_data 镜像去重、05j 双查构型、C-9 / C-14 标注对拍、b10 就绪度表、contract 键映射、报告六节） |
| 前端全量 | python scripts/hooks/check_js_tests.py | rc=0，621 tests / 621 pass / 0 fail；分母按新增夹具 10 用例如实增长（A-12 合入后 611 + 本笔 10）；本机 node v24.11.1 打印 跳过覆盖率门禁：未解析到覆盖率报告，如实标注为跳过、由分发方环境复验 |
| 结构质量 | python scripts/quality_rules.py | rc=0，十二项全为 已知 存量，零 [新增]；A-10 防重窗 require 序差异化归零坐实 |
| 全量 pytest | python -m pytest tests -q -p no:cacheprovider（flask_server 下串行单进程） | rc=0，1085 passed in 24.30s，零 failed（本片无 py 用例，分母不变） |
| 七道钩子 | pre-commit run --all-files | rc=0，语法校验（py / js / json / yaml）........................................Passed；仓库卫生（临时文件 / 超大文件）..........................................Passed；结构质量（十二项检查）...................................................Passed；文档同步（路由 / 工具收录）..............................................Passed；前端逻辑测试（node --test）..............................................Passed；主题副本同步（单一真源）.................................................Passed；依赖漂移校验（requirements）.............................................Passed |
| 文档同步 | python scripts/check_doc_sync.py | rc=0，单独命令实跑通过（pre-commit 文档同步道亦 Passed） |
| 差异检查 | git diff --check / git diff --cached --check | 均 rc=0，无空白错误 |
| 范围 | git status --short / git diff --numstat | 2 新文件 + docs/work-ai-c.md 只追加 7 行 / 0 删除；零代码改动 |

> 实测结果以收口轮实跑为准；覆盖率门禁本机 node v24 打印跳过，由分发方环境复验。
