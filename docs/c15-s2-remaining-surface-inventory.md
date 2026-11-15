# C-15 B-12 后 S2 余面与九步后续单点面判定报告

> 性质：B-12 合入后的只读取证判定片。只新增本报告与一份反查夹具，台账第五节只追加；零代码改动。
> 证据基线：实时 origin/main c817dea（含 B-12 验收合入 a0cb2f0、分支交付 c150b00、19:36 验收结论 dispatcher-20261115T193623-69215a、19:45 阶段级重新对拍 dispatcher-20261115T194511-c92792、19:49 任务书 dispatcher-20261115T194932-334b7c）；只读引用 C-8 矩阵（6394fbf / 17a8b32）、C-9 边界契约、C-10 判据、C-11 索引、C-12 映射、C-13 索引、C-14 签名总表、b10 就绪度、b11 口径归并、c6 盘点、c7 顺序表、b7 报告。
> 开工前置：git fetch origin --prune、git merge --ff-only origin/main 已完成，工作区干净，身份 actor=c（branch=work/ai-c）。
> 口径以 19:45 为准：S2 第 5 步 execute 单点已闭合、整体未齐备 / 待对拍；S4 摘除硬前置三项未全满足、阶段 3 不进入摘除步。
> 本报告所有排序建议仅为分发方复核输入：不代拍板、不改 S1-S4 判态、不预设下发时点、不自行圈定实装面。

## 一、C-9 六段（除 execute 外五段）当前态与签名总表 / 边界契约第四节对拍

B-12 后 `extend/lib/standard_chain_adapter.js` 实时形态：`STATUS = declared-placeholder`、`KEY = tool_call.id`、`EXECUTE_STATUS = implemented-S2-step5` 独立导出；`execute(card)` 单参保持 C-9 声明回显，`execute(card, deps)` 双参持执行编排骨架（七字段诊断复位、running 置位、委托 `deps.callTool(card)`、异常兜底写 error 不外抛、resolve 状态影子）。其余五段逐段核对如下。

| 段 | adapter 实时返回形状 | C-14 签名总表（第二节 / 第六节） | C-9 边界契约（第二节 / 第四节） | 判定 |
|---|---|---|---|---|
| parse | `{ by: KEY, block, status: STATUS }`，block 缺参回落 null，空 block 原样回显 | 第二节 parse(block) 行：by=KEY、block、status=STATUS | 第二节 parse 边界（null / undefined / 空 block / code 块）、G1 / G2 / G3 | 一致 |
| buildCard | `{ by: KEY, id, status: STATUS }`，id 缺参回落 null | 第二节 buildCard(call) 行 | 第二节缺 id 回落 null、不校验 function.name、不落消息树 | 一致 |
| reply | `{ by: KEY, role: tool, tool_call_id, status: STATUS }`，role 硬编码常量、content 不回显 | 第二节 reply(msg) 行：role=tool、tool_call_id、status=STATUS | 第二节 reply 边界：缺键归一、role 非 tool 强制归一、完整三键不回显 content、不抛错 | 一致 |
| dedupe | `{ by: KEY, a, b, status: STATUS }`，同 id 只回显 | 第二节 dedupe(a,b) 行 | 第二节同 id 不做判重决策、null 入参不抛错 | 一致 |
| restore | `{ by: KEY, sessionId, id, noMessageFingerprint: true, status: STATUS }`，sessionId 归一字符串 | 第二节 restore(sessionId,call) 行 | 第二节 G4 幂等、noMessageFingerprint 恒真、缺 call 回落 null | 一致 |

**对拍结论**：五段与 C-14 第二节签名逐行一致（STATUS 恒 declared-placeholder、KEY 恒 tool_call.id、唯一键标准 tool_call.id 与 tool 消息三键、不含消息指纹），与 C-9 逐段边界语义一致。B-12 实装态由 `EXECUTE_STATUS` 独立导出表达：C-9 第四节与 C-14 第六节均为只追加登记，抬头、六段状态表与判据原文保持历史口径（「六段仍声明」「运行时执行权仍在旧直调路径」与第四节实装登记并存，按 19:45「不改写他笔已合入 .md 源码」保留）。`EXECUTE_STATUS` 在 `flask_server/tests/js/` 仅命中 `test_standard_chain_adapter_execute.test.js`（5 处），未进 C-14 六段断言面，作用域限于 execute 段。C-10 S2 判据「一致」字面含「adapter.execute 仍 declared-placeholder 且运行时执行权仍在旧链」，与 B-12 后实况部分不同步；按 19:45 收紧口径处理，此处仅登记「文档标注 vs 代码实况」差异供分发方复核，判据原文保持只追加、不改 STATUS。

## 二、C-8 第二节九步装配推演（除第 5 步外）逐面判定

C-8 第二节为只读推演与状态标注，不是实装任务书（19:45 明确）；其第 5 步行仍写「仍占位；运行时执行权在 05g_cards.js / 06_execute.js 旧直调路径 / 依赖 B-7=是」，与实时实况（B-12 已实装、分发方 a0cb2f0 验收）并存，属只追加保留的历史标注，本报告保持原文、仅登记差异。第 5 步基线：`06_execute.js` L85 委托 `window.AIMirrorStandardChainAdapter.execute(card, { callTool })`，`_callTool` / `_recordFailure` 留作 deps 注入源，`dialog.html` L26 追加 adapter 装载行；git grep 命中 `AIMirrorStandardChainAdapter` 3 文件、`adapter.execute` 5 文件。

| # | 步骤与落点（已合入文件） | 当前态（实时实仓 c817dea） | 活调用方 | 依赖 | 禁区 |
|---|---|---|---|---|---|
| 1 | 模型回复 fetcher 返回 None / str / dict：`flask_server/core/chat_completions.py` 的 `model_reply_hook` / `_as_assistant_reply` | 已实交付；A-10 补 L10 生命周期契约 6 用例（`flask_server/tests/test_chat_l10_lifecycle.py`）并验收合入；入口仍可插拔占位，真实模型钩子未注册 | 服务端由模型调用，未接真实模型，前端零调用方 | 外部模型服务与凭证（用户侧排期）；B-7 统一对拍 | flask_server 下 .py 属 A-7 / A-10 面，本片零改动；不注册钩子、不装配运行时 M |
| 2 | 规范化追加 `_normalize_item` 三步一致：`core/chat_completions.py` | 已实交付，保持原状 | 服务端标准消息管线 | 无 | 同上 |
| 3 | 分发前钩子 `_run_pre_dispatch_hooks(history)`：`routes/chat_api.py` L36 / L60 / L213；`chat_completions.py` L356 装配指引注释 | 已实交付；装配仍占位（L78 注释指引、无代码调用）；A-10 夹具经 register / clear / pre_dispatch 装配面调用点实测 | 装配面调用点 | L10 真实模型接入（外部凭证） | 同上 |
| 4 | 标准 `tool_call.id` 建卡：`standard_chain_adapter.js buildCard`、`standard_chain_contract.js makeToolCallId` | buildCard 仍 declared-placeholder 回显；运行期建卡与候选仍由 `05g_cards.js` 承担（_translateToolCalls 落 card.toolCall / toolCallId，bridge-chat-call L123 命中） | `05g_cards.js` 活链，4 份 js 夹具；bridge-chat-call 全仓 28 文件命中 | 第 5 步单点已闭合可作基线；整链以三键重建待后续单点；旧标记摘除任务书（S4）；c6 九文件顺序表 | 活链文件（05g / 05j / 05c / 05f / 06_execute / 00_data / 01b / translator 等）零改动；旧标记全部保留；STATUS 保持声明态 |
| 6 | tool 消息回执：`standard_chain_contract.js standardToolMessage`；`adapter.reply` | 字段面一致、装配仍占位；三键纯函数在码（standardToolMessage 全仓 18 文件命中，多为夹具与契约文档），运行期回执仍走 05f_parse / 05c_prompt / 00_data / 06_execute 的 bridge-chat-res 旧链（全仓 30 文件命中） | 旧回执活链多文件；adapter.reply 无运行期下游 | 第 4 步建卡键落运行期；B-7 替换位 M1-M8 逐槽判定；c6 顺序表；前一单点（第 5 步） | 同第 4 步；不新增运行期探测分支、不建切换开关 |
| 7 | 去重：`adapter.dedupe`；`core/chat_completions.py pending_tool_calls` | 服务端按 tool_call_id 配对防重放已实交付；前端 dedupe 仍声明态；前端去重由 `00_data.js`（nonce 配对 external-call / bridge-chat-res、buildTimeline 折叠）与 `05j_card_sig.js`（标准 call_<nonce> + 旧 msgId 双查）承担 | 00_data.js 3 份夹具、05j_card_sig.js 4 份夹具 | 第 4 / 6 步键落运行期；刷新恢复键统一（c7 第 5 节）；c6 顺序表步骤 2 / 5 | 同第 4 步；executedSigs 双查构型保持 |
| 8 | 刷新恢复 `call_<nonce>` 键：`05j_card_sig.js` / `05g_cards.js`（C-7 实改） | 已实改并保持：标准键优先、旧 msgId 兼容双查、去消息指纹；`contract.js execKeyFromToolCall`（会话 id + nonce + 工具名 + 参数摘要）纯函数在码，运行期恢复仍走旧双查 | 05j_card_sig.js / 05g_cards.js 活链，4 份夹具 | execKeyFromToolCall 接入；c6 顺序表步骤 5；旧标记摘除任务书 | 同第 4 步；已合入实改零改写 |
| 9 | 协议字段退役：B-7 范围服务端 / 网关 / `remote_bridge` 信封 | 替换位列全、三网关零遗留（b7 / B-8 / B-9 / B-10 / B-11 逐笔验收合入），`PROTOCOL_RETIREMENT_CONTRACT.status` 仍 declared-placeholder，运行时退役面全未动（19:45 S3 不变） | bridge-chat-call 28 文件、bridge-chat-res 30 文件、is_tool_result 10 文件（含 remote_bridge/outbound.py、message_flow.py、message_router.py）、run-command（01b_bridge.js + routes/bridge.py） | B-7 总结论与逐槽判定；S2 整体齐备（整链迁移）；c6 顺序表；分发方裁定 | remote_bridge / 三网关 / flask_server 下 .py 零改动；PROTOCOL_RETIREMENT_CONTRACT.status 保持声明态；不预设 B-7 结论 |

**逐面小结**：第 1 / 2 / 3 步为服务端已实交付面、装配仍占位，依赖外部凭证；第 4 / 6 / 7 / 8 步落点均为「契约或纯函数在码 + 运行期仍由旧链承担」，活调用方全部保留，依赖前一单点与 c6 顺序表；第 9 步替换位契约面列全、运行时退役面全未动。九步余面无现成分发方裁定过的实装任务书（19:45：总线层「第 6 步」唯一命中为 19:36 本方 answer 自述）。

## 三、C-10 S1-S4 四槽与 b10 五层前置表（B-12 合入后逐槽核对）

| 槽位 | C-10 判据收口条件 | B-12 后实时态（19:45 口径） | b10 就绪度表对应层 | 判定（复核输入） |
|---|---|---|---|---|
| S1 #4 fetcher 跨侧 | 契约侧一致；L10 接真实模型需外部服务与凭证 | 不变：A-10 生命周期契约已验收合入，入口仍可插拔占位，真实模型钩子未注册 | 第 4 层「S1 缺 L10 真实模型接入」保持 | 一致，不构成运行时执行权迁移 |
| S2 #7 tool_calls 意图执行 | 三笔齐备 + 第 5 步由 declared-placeholder 转实装且分发方验收通过 | 第 5 步单点已满足（a0cb2f0：570/570、七钩子、1085 pytest、边界探针 6/6）；模块 STATUS 恒 declared-placeholder、其余五段仍声明、标准执行链未整体以 tool_call.id 与 tool 消息三键重建、执行权未 100% 脱离旧链环境适配面，19:45 判「单点已闭合、整体未齐备 / 待对拍」 | 第 1 层由「执行权全未迁移」收紧为「仅第 5 步单点迁移并验收，不等于整链迁移完成」（19:36 措辞过宽按 19:45 收紧） | 整体待对拍 |
| S3 #13 协议字段退役 | 替换位判定一致 + 三网关零遗留 + 逐项对拍完毕后 PROTOCOL_RETIREMENT_CONTRACT.status 方可转实装 | 不变：判一致（契约面列全对齐），status 仍 declared-placeholder，运行时退役面全未动 | 第 5 层「S3 判一致仅契约面」保持 | 一致，不触发摘除 |
| S4 #14 旧标记摘除 | 三笔齐备 + 执行权迁移 + 分发方另行下发摘除任务书 + 按 c6 九文件顺序表执行 | 19:45 收紧为三项硬前置：①仅完成第 5 步单点迁移并验收（整链未完成，不满足）；②摘除任务书未下发；③c6 顺序表未执行（九文件全活链、零摘除）；阶段 3 不进入摘除步 | 第 1 / 2 / 3 层与总体结论「旧标记摘除当前不下发，前置未满足」保持 | 保持现状不摘除 |

b10 报告证据基线为 34e6029 历史只读快照，B-12 后保持只追加、未改写；本节以 19:36 / 19:45 实时裁定为准逐槽核对，并登记该「历史快照 vs 实时裁定」口径差异供分发方复核。

## 四、下一合法可验收单点面：排序建议与可实测口径

> 本节全部为分发方复核输入：不代拍板、不改 S1-S4 判态、不预设下发时点、不自行圈定实装面。19:45 已明确总线任务书层「第 6 步」从无裁定过的范围 / 硬约束 / 验收标准，C-8 第二节第 6 步行只是只读推演；任何实装片由分发方另行下发任务书。

| 序 | 候选单点面（类别） | 与硬约束的相容性 | 可实测口径 | 依赖 / 禁区 |
|---|---|---|---|---|
| 1 | 六段余面之一（reply 或 restore）的边界反查夹具 + C-9 / C-14 状态标注对拍片（只读取证类） | 零代码改动；只新增夹具与 docs 报告；活链零改动；运行时 M 保持未装配；切换开关数量为零；运行期探测分支数量为零；STATUS 保持 declared-placeholder；EXECUTE_STATUS 作用域不变 | 按 C-14 形态（按字符码 10 切行、普通 indexOf / split、零反斜杠零正则、新增被测 JS 源 0、hooks / 90-70 / baseline 零改动）；node 单文件断言该段返回形状 / STATUS / KEY / noMessageFingerprint 与 C-9 第二节、C-14 第二节一致；check_js_tests.py 全量 rc=0 且覆盖率无退化与新增欠账；quality_rules.py 零新增；全量 pytest 零 failed；pre-commit 七道逐个 Passed 且提交不带 --no-verify；diff --check rc=0；只追加复验 0 删除 | 依赖：无外部前置，不依赖 B-7 与前一单点。禁区：同第二节活链禁区；不把声明态翻成已装配 |
| 2 | 九步余面单步（第 4 步建卡 / 第 6 步回执 / 第 7 步去重）的「文档标注 vs 代码实况」逐行取证片（只读取证类） | 本报告第二节已铺逐面基线，收窄到单步即可自带实测；零代码改动，只新增一份 docs 报告与可选反查夹具；推演表保持只读地位 | 逐文件落点 / 当前态 / 活调用方 / 依赖 / 禁区五项与实时 origin/main 对拍为真；git grep 命中计数与夹具反查关键命中串；验收套件同候选 1 | 依赖：第 5 步单点已闭合仅作基线；c6 九文件顺序表保持未执行状态。禁区：不把只读推演当实装授权；不自行圈定实装面 |
| 3 | S1 L10 真实模型接入前置（前置类，不建议作为执行方可验收单点） | 代码侧只到显式可插拔入口；缺外部模型服务与凭证，属用户侧排期 | 如分发方裁定，仅能做契约入口只读复核（A-10 六用例已覆盖生命周期与请求间隔离），不构成运行时执行权迁移 | 依赖：外部凭证到位。禁区：flask_server 下 .py 零改动；不接真实模型、不代用户排期 |

**排序建议**：候选 1 优先于候选 2，候选 2 优先于候选 3。前两者零代码、自带实测、与 S4 三项硬前置及「活链零改动 / STATUS 保持声明态 / 切换开关为零」全部相容，且不需要外部凭证；候选 3 缺外部条件。最终由分发方圈定不超过 1 个可验收面并另行下发实装任务书。

## 五、边界与结论（复核输入）

- 范围：只新增本报告、`flask_server/tests/js/test_standard_chain_c15_inventory.test.js` 与 `docs/work-ai-c.md` 第五节只追加完成记录；零代码改动。
- 活链文件（05g_cards.js / 05j_card_sig.js / 05c_prompt.js / 05f_parse.js / 06_execute.js / 00_data.js / 01b_bridge.js / translator.js / dialog.html 等）零改动；旧标记全部保留；STATUS 保持 declared-placeholder；EXECUTE_STATUS 保持独立导出、作用域不变；c6 九文件顺序表保持未执行状态。
- 运行时 M 保持未装配；钩子注册数量为零；切换开关数量为零；运行期探测分支数量为零；docs/bus 他人消息零触碰；docs 只追加（0 删除）；hooks / 90-70 阈值 / js_coverage_baseline.json 零改动，--update-baseline 未使用。
- 判定：S2 第 5 步单点已闭合、整体未齐备 / 待对拍；五段声明态与 C-14 / C-9 逐项一致；九步余面落点 / 当前态 / 活调用方 / 依赖 / 禁区逐面登记完毕；S4 三项硬前置未全满足，阶段 3 不进入摘除步。
- 本报告建议仅为分发方复核输入，不代拍板、不改 S1-S4 判态、不预设下发时点。

## 六、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| 反查夹具 | node --test flask_server/tests/js/test_standard_chain_c15_inventory.test.js | rc=0，8 tests / 8 pass / 0 fail（五段声明回显、execute 独立导出、第 5 步委托装载、只追加登记、九步推演保留、S4 判据、活链留存、报告六节齐全） |
| 前端全量 | python scripts/hooks/check_js_tests.py | rc=0，578 tests / 578 pass / 0 fail；本机 node v24.11.1 前缀差异打印「跳过覆盖率门禁：未解析到覆盖率报告」，如实标注为跳过，由分发方环境复验 |
| 结构质量 | python scripts/quality_rules.py | rc=0，十二项全为「已知」存量，零 [新增] |
| 全量 pytest | python -m pytest tests -q -p no:cacheprovider（flask_server 下串行单进程） | rc=0，1085 passed in 30.10s，零 failed |
| 七道钩子 | pre-commit run --all-files | rc=0，语法校验（py / js / json / yaml）........................................Passed；仓库卫生（临时文件 / 超大文件）..........................................Passed；结构质量（十二项检查）...................................................Passed；文档同步（路由 / 工具收录）..............................................Passed；前端逻辑测试（node --test）..............................................Passed；主题副本同步（单一真源）.................................................Passed；依赖漂移校验（requirements）.............................................Passed |
| 差异检查 | git diff --check / git diff --cached --check | 均 rc=0，无空白错误 |
| 范围 | git status --short / git diff --numstat | 2 新文件 + docs/work-ai-c.md 只追加 7 行 / 0 删除；零代码改动 |

> 实测结果以收口轮实跑为准；覆盖率门禁本机 node v24 前缀差异打印「跳过」，由分发方环境复验。
