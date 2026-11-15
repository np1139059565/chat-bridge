# B-11 摘除顺序表口径差异归并与九文件影响面夹具清单（只读复核）

> 2026-11-15 AI-B 交付（对应 docs/work-ai-b.md 当前任务 B-11，11:06 续派）。
> 性质：只读取证，零代码改动、零测试改动、不摘除任何标记、不实装、不代分发方拍板、不预设下发时点。
> 证据基线：origin/main e284557（B-10 验收合入 f2ccb87 之后，含 C-13 合入与 B-11/C-14 续派台账）；行号为本轮实仓 git grep / Python 直读实测。
> 引用（只读）：docs/c6-direct-path-inventory.md、docs/c7-standard-chain-migration-plan.md、docs/b10-removal-readiness-report.md。

## 一、两处口径差异逐项复核（交付 ①）

### 1.1 01c_bridge_cmd.js

| 维度 | 本轮实测（e284557） |
|---|---|
| c6 原表口径 | 列为九混存文件之一（c6 按当时全量符号口径；c7 第 1 节已声明 C-6 与 c7 检索口径不同、非仓内状态变化） |
| c7 五步分组表口径 | 步骤 2 分组列名 |
| 实仓现状 | 151 行；宽口径协议标记检索（bridge-chat-call / bridge-chat-res / external-call / run-command / is_tool_result / toolCalls / toolCallId / toolCall / TOOL_RESULT）零命中；唯一远程接口面为 /api/bridge/commands（管理面：saveBridgeCommand L93 / removeBridgeCommand L138）与 commandSource 对接 /api/commands 清单（L16-20 注释明示「执行与回执通道不变」） |
| 调用方 | extend/dialog/dialog.html L42 挂载；extend/dialog/parts/08f_commands.js L184/213/236/240 四处 UI 调用（startPickElement / saveBridgeCommand / editBridgeCommand / removeBridgeCommand）；01b_bridge.js L314 历史注释（「已移到 01c」） |
| 夹具 | 1 份文本级直接引用：flask_server/tests/js/test_translator.test.js L275-276，断言 commandSource / commandDefinitions 字串存在，非协议标记断言 |
| 只读裁定建议 | 本轮不可摘（无旧协议标记可摘）；该文件属「桥接指令管理面」非「协议标记面」，c7 步骤 2 列名属口径遗留。建议归并口径：顺序表执行时按「列名、零标记、无需动作」登记跳过，保留 c6 原表序行位作时间线留痕。此建议仅为分发方复核输入，不代拍板、不改 c6/c7 原文 |

### 1.2 05d_memory.js

| 维度 | 本轮实测（e284557） |
|---|---|
| c6 原表口径 | 九混存文件之一 |
| c7 五步分组表口径 | 未单列行（B-10 第三节登记的覆盖缺口） |
| 实仓现状 | 244 行；bridge-chat-res 仅 2 处且均为注释（L52 / L70，解释 isRealUserMessage 排除逻辑）；运行时真依赖是 msgSource(m) !== 'tool'（L78，判定入口在 05f_parse.js L390），自身不构造、不解析任何协议字串 |
| 调用方 | 记忆窗口角色判定链（_lastRealUserId / isRealUserMessage / noteUserTurn），为 msgSource 的下游消费者 |
| 夹具 | 文本级直接引用 0 份；行为级间接引用 0 份（isRealUserMessage / _lastRealUserId / noteUserTurn / _ensureMemoryState / memoryCheck / 05d_memory 六探针在测试目录 55 份 js 全零命中） |
| 只读裁定建议 | 注释级标记、消费面单一；建议归并到步骤 3 分组（与 05f_parse.js 同组）：其标记语义完全由 msgSource 判定迁移决定，步骤 3 执行时注释随 msgSource 新语义一并更新即可，无需独立摘除动作。此建议仅为分发方复核输入，不代拍板、不改 c6/c7 原文 |

## 二、九文件影响面夹具清单（交付 ②，按 B-10 第三节序）

夹具数为本轮文本级直接引用实测，与 B-10 第三节逐文件一致（3/3/1/5/0/6/4/4/2）；「协议标记面夹具」指夹具内含协议字串断言或协议语义行为断言（cardHasMessage / msgSource / executedSigs 等）。

| 文件 | 直接夹具 | 是否属协议标记面 | 摘除时夹具侧最小动作（只描述不实装） | 刷新恢复/去重/兜底影响 |
|---|---|---|---|---|
| 00_data.js | 3 份：test_config_actions（L178，/api/clients 真源）、test_dialog_boot（L5/61，命名空间顺序）、test_dialog_contracts（L46，creator 顺序） | 三份直接夹具均非协议面；协议面影响在行为级：test_translator_wiring 2 处 cardHasMessage 断言 | 步骤 2 改 tool_call.id 配对时同步 cardHasMessage 行为断言；三份直接夹具（真源/顺序契约）零动作 | cardHasMessage nonce 配对为镜像去重键（external-call 与 bridge-chat-res 防镜像重复渲染）；L174 折叠状态键 |
| 01b_bridge.js | 3 份：test_config_audit（L50，保存文案）、test_translator（L272-274，/api/commands 接线）、test_translator_wiring（L194，dialectFor 调用点） | 三份均不断言 run-command 字串；run-command 在夹具中的分布仅 B-8/C-10/C-12 契约夹具（test_standard_slot_m345 11 处等），不直接引用 01b 本体 | M3 退役时 01b 直接夹具零动作；run-command 契约夹具按 B-8 落点口径 | 无（用户指令旁支，回执不进 AI 对话流） |
| 01c_bridge_cmd.js | 1 份：test_translator（L275-276，commandSource/commandDefinitions） | 否（管理面） | 零动作（见 1.1） | 无 |
| 05c_prompt.js | 5 份：test_05c_prompt_schema_coverage、test_orphan_slice_behavior（L34）、test_translator（L221/236/253）、test_translator_wiring（L196）、test_translator_wiring_require（L28） | 是（test_translator 含 bridge-chat-call 10 处 / bridge-chat-res 4 处，覆盖 05c 模板与回执信封；wiring_require 含装载契约） | 步骤 3 摘除信封构造点（L210/276 等）时同步 test_translator 信封类型断言；schema 覆盖与 orphan 行为夹具零协议动作 | 兜底三项补签对象（本体缺失逐字退回，B-10 记载 L41-45/L254-258/L283-287）随翻译层口径处理 |
| 05d_memory.js | 0 份（文本级 0、行为级 0） | 注释级（见 1.2） | 零夹具动作；注释随 msgSource 语义更新 | 无（记忆窗口角色判定，恢复链无涉） |
| 05f_parse.js | 6 份：test_card_build_behavior（L29）、test_orphan_slice_behavior（L33）、test_parse（L4/14/34）、test_parse_tolerant（L4/19）、test_scroll_autoexec（L23）、test_translator_wiring_require（L26） | 是，最重：test_parse（call 5 / res 2 / external-call 4 / msgSource 8）、test_parse_tolerant（call 2）、test_scroll_autoexec（call 2）、test_card_build_behavior（call 1） | 步骤 3 标准解析入口落地后，test_parse / test_parse_tolerant 解析用例按新入口重写（C-7 已注入 _c7_standard_entry 标准键断言、旧链断言保留）；msgSource 判定迁移时 8 处断言同步 | msgSource 为 05d 记忆窗口与折叠判定的唯一来源入口，迁移需整链同步 |
| 05g_cards.js | 4 份：test_card_build_behavior（L30）、test_card_sig_restore（L31）、test_scroll_autoexec（L25）、test_translator_wiring_require（L27） | 是（建卡与候选：bridge-chat-call L123、toolCalls L47/59/132、toolCall 10 处；回执 bridge-chat-res L430-438） | 步骤 4 state.toolCalls 有执行期下游后，建卡行为用例按新键同步；回执构造随 05c 步骤 3 同步 | L227 card.toolCallId = 'call_' + nonce 为刷新恢复链绑定点；autoCandidates/armedLast/rerunCard 生产端 |
| 05j_card_sig.js | 4 份：test_05j_card_sig_coverage（L1/10/17）、test_card_sig_restore（L30）、test_scroll_autoexec（L24）、test_standard_chain_field_matrix（L34） | 是（executedSigs：coverage 7 处、restore 6 处；双查构型 L26/57/113） | 步骤 5 executedSigs 去消息指纹时，coverage 旧键回退分支用例同步删除、restore 恢复键用例按 call_<nonce> 单键改写；另有行为级 test_clear_sessions_sig（executedSigs 5 处）随恢复键迁移同步 | executedSigs 双查（标准优先 + 旧 msgId 兼容）为刷新恢复与幽灵卡判据核心；覆盖率门禁敏感文件（C-7 首次验收曾因行/分支退化被拦，基线 78.05/56.00），删旧键分支改变分母需按基线流程处理 |
| translator.js | 2 份：test_translator（L16/268/271）、test_translator_wiring_require（L24） | 特殊：本体为翻译层，含旧协议字串属双向翻译职责（L84/85/90/123/126/161/163/166/177）；test_translator 为翻译层最重夹具（call 10 / res 4） | 摘旧标记时须按分发方定义的「本体上旧协议字串处理口径」同步翻译用例（可能整体保留只删旧侧导出）；dialog.html / manifest.json 挂载断言（L268-271）与协议无关 | FALLBACK_STANDARD 兜底在方言层；FALLBACK_TOOLS 字串夹具零命中，兜底断言走模板面（test_translator L235 「Tool·调用说明」） |

九文件小结：全部仍存在、全部活链、零摘除；夹具侧影响集中在 05f（6 份、协议断言最重）、05c（5 份、信封与兜底）、05g/05j（各 4 份、恢复链与执行权）；01c/05d 两侧零或近零影响，佐证两处口径差异均为低风险登记项。

## 三、显式结论（交付 ③）

1. 两处口径差异不构成新前置、不触发摘除动作：01c 属「列名、零标记」的口径遗留（管理面文件），05d 属「注释级、未单列」的覆盖缺口（msgSource 下游消费者），均无运行时协议构造/解析点。
2. 归并建议（仅分发方复核输入，不代拍板、不改 c6/c7 原文）：01c 按「列名、零标记、无需动作」登记跳过；05d 归并到步骤 3 分组随 msgSource 语义一并更新。
3. 摘除统一硬前置沿用 S4 三项与 10:05:32 广播判态：①运行时执行权已由旧链迁到标准链且分发方验收；②分发方另行下发摘除任务书；③按 c6 九文件顺序表执行。三项缺一不可，当前均未满足，阶段 3 不进入摘除步。
4. 本报告为只读取证基线：零代码、零测试改动、不实装、不建切换开关、不新增运行期探测分支、不摘除任何标记、不把 declared-placeholder 翻成已装配、不预设下发时点。

## 四、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| pre-commit 七道 | pre-commit run --all-files | 提交时实跑（js-tests/quality/diff 已单独先测，见下）；见第五节完成记录 |
| 全量 pytest | python -m pytest tests -q -p no:cacheprovider（flask_server/ 下，单进程串行） | 1078 passed / 1 failed；唯一失败 test_weixin_protocol.py::TestClientContract::test_production_client_gets_ctx_path（ensure_wx_login 需真实环境，本机无凭证返回 None），与 B-10 记录载明的同项环境存量波动一致；单文件复跑见下 |
| check_js_tests.py | python scripts/hooks/check_js_tests.py | rc=0，554/554 全过，覆盖率达标（24 项存量欠账在基线内，无退化与新增） |
| quality | python scripts/quality_rules.py | rc=0，全部命中为 [已知]，零 [新增] |
| diff --check | git diff --check / git diff --cached --check | rc=0 干净（含新报告与只追加记录暂存前后） |
| 边界 | git status 核对 | 实测：新增未跟踪仅 docs/b11-order-table-reconciliation.md 1 份，已跟踪改动仅 docs/work-ai-b.md 只追加；零代码、零测试改动；extend/dialog/AUDIT.md 为未跟踪文件，非本任务产物，未纳入提交、未改动 |

> 实测结果以收口轮实跑为准，不谎报全绿、不自填。
