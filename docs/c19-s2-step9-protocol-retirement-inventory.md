# C-19 阶段 3 九步装配面第 9 步协议字段退役逐行取证报告

> 性质：只读取证判定片。只新增本报告与一份反查夹具，台账第五节只追加；零代码改动。
> 证据基线：实时 origin/main 4c7bad3（开工前 ff-only 由 d90b8e7 线性推进到位；含 C-17 合入 a25fc98 / B-14 合入 4ce0fd1 / A-13 合入 425cf80 / C-18 合入 1e3cfee 四个 merge，PEN_A / PEN_C answer 登记，a 续派登记与 23:55 本笔任务书 dispatcher-20261116T235535-259fdb 登记）。任务书写 1f3ec9f 为「含四个 merge 与 PEN_A / PEN_C answer 及 a 续派登记」的基线，4c7bad3 为其线性后继（本任务书登记）；开工前 git fetch origin --prune + git merge --ff-only origin/main 已完成（d90b8e7..4c7bad3），工作区干净，身份 actor=c（work/ai-c，旧 tip d90b8e7 已是 main 祖先）。
> 主锚（实时 origin/main 自动抽出原句，不手写近似串）：C-15 第二节第 9 行完整六列 = 「协议字段退役：B-7 范围服务端 / 网关 / `remote_bridge` 信封 | 替换位列全、三网关零遗留（b7 / B-8 / B-9 / B-10 / B-11 逐笔验收合入），`PROTOCOL_RETIREMENT_CONTRACT.status` 仍 declared-placeholder，运行时退役面全未动（19:45 S3 不变） | bridge-chat-call 28 文件、bridge-chat-res 30 文件、is_tool_result 10 文件（含 remote_bridge/outbound.py、message_flow.py、message_router.py）、run-command（01b_bridge.js + routes/bridge.py） | B-7 总结论与逐槽判定；S2 整体齐备（整链迁移）；c6 顺序表；分发方裁定 | remote_bridge / 三网关 / flask_server 下 .py 零改动；PROTOCOL_RETIREMENT_CONTRACT.status 保持声明态；不预设 B-7 结论」。任务书正文该句在消息中截断为「| bridge-chat-c；」，按自带口径从仓内 L36 取真值，与本文描述一致。
> 只读引用：C-15 第二节第 9 行与逐面小结、C-8 standard_chain_field_matrix.md 九步表第 9 行与对拍矩阵 #13、C-9 standard_chain_boundary_contract.md 全局不变量与第三节验收口径、C-14 standard_chain_c14_signature_table.md 第二节与第六节、C-10 standard_chain_pending_criteria.md / C-11 standard_chain_crossref_index.md / C-12 standard_chain_replacement_map.md / C-13 standard_chain_c13_crossref_index.md、b7-protocol-retirement-status.md、b10-removal-readiness-report.md、B-8 / B-9 两片纯函数、C-16 / C-17 / A-13 / C-18 报告（同型形态）；不改他笔已合入 .md 源码本体。
> 同面隔离：只做九步第 9 步协议字段退役装配面逐行取证；不重做 C-18 第 8 步刷新恢复键、A-13 第 6 步 tool 回执、C-17 第 7 步去重、B-14 六段 dedupe、不碰 a reply / b buildCard 在途面、不扩 execute（S2 第 5 步单点已闭合）、不碰 S1 L10。
> 范围：不是实装授权、不是摘除授权；C-8 第二节仅只读推演、不作实装授权；不改写 19:45 / C-16 / C-17 / A-12 / B-14 / A-13 / C-18 判态。
> 本报告所有差异登记与结论仅为分发方复核输入：不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。

## 一、第 9 步协议字段退役逐文件五项判定（落点 / 当前态 / 活调用方 / 依赖 / 禁区）

| 落点文件 | 当前态（实时 4c7bad3） | 活调用方 | 依赖 | 禁区 |
|---|---|---|---|---|
| extend/lib/standard_chain_contract.js | L31-34 PROTOCOL_RETIREMENT_CONTRACT = Object.freeze({ owner: B-7, legacy: [bridge-chat-call, bridge-chat-res], direction: standard tool_calls / tool message as the only key, status: declared-placeholder })；L44 模块导出。冻结常量，运行时未装配、status 未翻 | 仅契约夹具与 C-14 签名表 / crossref 文档引用（PROTOCOL_RETIREMENT_CONTRACT 全仓宽口径 31 行 23 文件）；运行期零状态迁移 | B-7 总结论与逐槽判定；S2 整体齐备（整链迁移）；c6 顺序表；分发方裁定 | 零改动；status 保持 declared-placeholder；不预设 B-7 结论；不扩用 EXECUTE_STATUS |
| extend/lib/standard_chain_c14_signature_table.md | 第二节 L50 PROTOCOL_RETIREMENT_CONTRACT.status / L51 .direction 两行（一致 / declared-placeholder）；L85 C-10 四槽、L86 C-11 交叉索引、L87 C-12 八槽映射、L88 C-13 八槽索引；第一节 L13 G1「四个已合入 lib、钩子声明面、协议退役面 STATUS 恒 declared-placeholder」；第六节 L113 起仅 execute 段实装登记（B-12），不含协议退役断言面 | 仅标注对拍输入 | 无 | 不改他笔已合入 .md 源码本体；不取为范围 |
| extend/lib/standard_chain_replacement_map.md（C-12） | 第二节 M1-M8 八槽，每槽固定三项（旧位所在层 / 替换位落点类型 / 是否仍占位）+ 对应槽位 + 矩阵编号；L86 #13 协议字段退役 → S3 → M1..M7；L87 #14 旧标记摘除 → S4 → M8；第一节 L14 G1 STATUS 恒 declared-placeholder | 只读映射底稿，由 C-14 / C-13 / B-9 夹具引用 | C-10 判据清单；B-7 report 显式列出旧位→新位 | 零改动；不写死 B-7 实际新位值 |
| docs/b7-protocol-retirement-status.md | 收口片只交付「现状 + 替换位列全情况说明」：第二节 2.1 run-command（M3）抽屉 01b_bridge.js:400 唯一调用方 / routes/bridge.py:294 / 三网关 grep run-command 零命中；2.2 external-call（M4）三网关包装 qq_gateway.py:331/338/383、wecom_gateway.py:191/343、weixin_gateway.py:122 + 公共解析 message_parse.py:53/117/126、core/envelope.py:23-62、web_mirror.py:306/379、memory_distill.py:285/317 全活链；2.3 is_tool_result（M5）上报信封布尔标记位；2.4 G10/G11/G12；第三节 M1-M8 全量列表八行；第四节显式声明旧标记摘除面（#14 / S4）无协议字段替换位 | 只读报告；M3/M4/M5 落点实装由 B-8 接走、M1/M2/M6/M7/M8 由 B-9 接走 | 方案 A 纯函数层口径；01:07:37 拆片决定 | 零改动；不预设 B-7 总结论、不代分发方裁定退役时点 |
| extend/lib/standard_slot_m345.js（B-8，M3/M4/M5 三槽）与 extend/lib/standard_chain_b9_slot_resolver.js（B-9，M1/M2/M6/M7/M8 五槽） | 两片纯函数层在码：B-9 L21 SLOTS 冻结五槽、L92 导出 SLOTS / findSlot / resolveReplacement；两片 STATUS 恒 declared-placeholder（清单/映射层不翻 STATUS）；C-14 第四节 L95-96 判两片槽位交集为空、并集恰 M1..M8、源码互不 require、文件名不同、无文件交集 | 各自夹具加载（已在覆盖率库）；未装配运行时 M | 方案 A 纯函数层口径；C-12 落点类型声明 | 零改动；不装配 M、不翻 STATUS、不扩用 EXECUTE_STATUS |
| C-10 / C-11 / C-13 清单与索引（extend/lib/ 下） | C-10 四槽 S1-S4 与 #4/#7/#13/#14 判据；C-11 交叉索引 14 / 6 / 4 条目集合；C-13 八槽归属片 / 文件名 / STATUS / 唯一键 / S 槽 / 矩阵编号。均为只读清单，STATUS 声明态 | C-14 / 各反查夹具引用 | 无 | 零改动；不改他笔已合入 .md 源码本体 |
| docs/b10-removal-readiness-report.md | 第二节 L18 S3 行：替换位列全（b7 第三节 M1-M8 八槽四项齐全）且分发方判一致（10:05 广播）；契约面判一致≠运行时退役（M1-M8 对应旧位仍在活链）；三项收口条件（S2 装配实装并验收 / 协议字段按替换位逐槽切到标准链并经真实使用 / 分发方复判后 status 方可转实装）；L19 S4 行三项硬前置；第四节 L41 协议字串全仓活链命中（非测试文件）逐项；L52 S1/S3 判一致不构成摘除触发 | 就绪度登记，非运行期装配 | c6 九文件顺序表未执行 | 不改他笔已合入 .md 源码本体；不执行 c6 顺序表 |
| 活链协议字串落点（只读反查，零写入） | 服务端 / 网关 / remote_bridge：bridge-chat-call 在 core/chat_completions.py L6 文档串、remote_bridge/channel/text.py L57、routes/chat_api.py L9 文档串（3 行）；bridge-chat-res 在 core/memory_distill.py L61/208/317、channel/text.py L58、message_parse.py L7/134/144（7 行）；is_tool_result 在 remote_bridge/message_flow.py L219、message_router.py L306、outbound.py L28/46/109/130（6 行）；run-command 在 01b_bridge.js L392 注释 / L400 POST、routes/bridge.py L294（3 行）。前端活链九文件（00_data / 05f_parse / 05g_cards / 05c_prompt / 05d_memory / 06_execute / translator / 01b_bridge / 05j）含旧协议字串，运行时退役面全未动 | 旧链真实生产链（b7 第三节 M1/M2/M4/M6/M7 逐行登记） | B-7 总结论与分发方裁定；S2 整体齐备 | 活链零改动；旧标记全部保留；remote_bridge / 三网关 / flask_server 下 .py 零改动；不摘除 |
| flask_server/tests/js/ 与 docs/ | C-15 第 9 行登记 bridge-chat-call 28 / bridge-chat-res 30 / is_tool_result 10 文件为历史快照计数（见第四节差异 5）；实时引用协议字串的夹具与报告按宽口径分布；本片新增独立命名反查夹具 1 份 | 断言面，非运行期装配 | 无 | 不碰 A-13 / B-14 / C-17 / C-18 / A-11 / A-12 / B-13 / C-15 / C-16 报告与夹具本体、不碰 extend/dialog/AUDIT.md |

## 二、与 C-15 / C-8 / C-9 / C-14 / field_matrix / b10 逐行对拍

| 对拍源 | 原文锚点 | 实时实况 | 判定 |
|---|---|---|---|
| C-15 第二节第 9 行（L36） | 替换位列全、三网关零遗留；PROTOCOL_RETIREMENT_CONTRACT.status 仍 declared-placeholder；运行时退役面全未动（19:45 S3 不变） | b7 第三节 M1-M8 八行列全；contract L33 status 声明态；活链协议字串全保留、三网关按 b7 2.1 口径 run-command 零命中 | 一致 |
| C-15 逐面小结（L38） | 第 9 步替换位契约面列全、运行时退役面全未动 | 契约面 C-12/C-13/C-14 列全，运行时旧链仍为真实生产链 | 一致 |
| C-8 九步表第 9 行（L51） | 协议字段退役 | B-7 范围：服务端 / 网关 / remote_bridge 信封 | 未交付 | 是 | b7 已合入「现状+替换位列全」但 B-7 总结论与实装面未下发、运行时未退役 | 一致（历史快照措辞，见差异 6） |
| C-8 对拍矩阵 #13（L31） | 协议字段退役 | A-7 未动该面 | PROTOCOL_RETIREMENT_CONTRACT 为 declared-placeholder | 待对拍 | 契约常量仍冻结声明态、待对拍 | 一致（历史快照，只读推演） |
| C-9 全局不变量 G1（L11-12）与第三节 L102 | STATUS 恒 declared-placeholder（六段 / 协议退役面）；不碰 B-7 协议字段退役面 | contract / C-14 声明态未漂移；本片只读反查、零改写 | 一致（C-9 无独立第 9 步边界段，见差异 4） |
| C-14 第二节 L50 / L51 / L85-88 + 第六节 | PROTOCOL 两签名行、C-10~C-13 索引行、第六节仅 execute 段登记 | 签名行逐格在文；第六节不含协议退役断言面；EXECUTE_STATUS 独立导出作用域不变 | 一致（仅标注对拍输入，不取为范围） |
| b10 S3 行（L18）与 L52 | 三项收口条件未满足；S1/S3 判一致不构成摘除触发 | S2 装配实装并验收未发生、协议字段未逐槽切标准链、分发方未复判 | 一致 |
| b10 S4 行（L19） | 三项硬前置（执行权已迁标准链且分发方验收 / 摘除任务书下发 / 按 c6 顺序表执行） | 三项均未满足，阶段 3 不进入摘除步 | 一致 |

## 三、git grep 关键串命中计数（实时 4c7bad3）

| 关键串 / 口径 | 命中 | 说明 |
|---|---|---|
| | 9 | 协议字段退役（C-15 第二节行首前缀） | 1 行（L36） | 本片主锚恰 1 行 |
| PROTOCOL_RETIREMENT_CONTRACT（全仓宽口径） | 31 行 / 23 文件 | 含 contract 定义与导出、C-14 两签名行、C-10/C-11/C-12/C-13 索引、b7 / b10 / 各报告与夹具 |
| bridge-chat-call（全仓宽口径） | 123 行 / 51 文件 | 服务端 / 网关侧 3 行；非测试非文档活链 9 文件 |
| bridge-chat-res（全仓宽口径） | 153 行 / 51 文件 | 服务端 / 网关侧 7 行；非测试非文档活链 20 文件（含 1 份 docs/archive html） |
| is_tool_result（全仓宽口径） | 75 行 / 24 文件 | remote_bridge 侧 6 行；非测试非文档活链 4 文件 |
| remote_bridge（全仓宽口径） | 309 行 / 103 文件 | 含文档 / 报告 / 总线 / 代码多类，非运行期装配计数 |
| run-command（精确三处） | 3 行 | 01b_bridge.js L392 / L400、routes/bridge.py L294 |
| 三网关 external-call 包装（b7 2.2 登记） | qq_gateway.py 3 处 / wecom_gateway.py 2 处 / weixin_gateway.py 1 处 | 只读报告登记，活链真实生产动作 |
| M1-M8 八槽 | C-12 八个「### 槽位 M」标题、b7 第三节八行、C-14 L87 行 | 八槽列全、B-8 三槽与 B-9 五槽互斥 |

## 四、差异登记（文档标注 vs 代码实况，仅供分发方复核输入）

1. **主结论零差异**：第 9 步「替换位契约面列全 / 三网关零遗留 / PROTOCOL_RETIREMENT_CONTRACT.status 仍 declared-placeholder / 运行时退役面全未动（19:45 S3 不变）」与实时实仓逐项相符。三网关零遗留按 b7 第二节 2.1 口径指三网关 grep run-command 零命中（通道侧指令走 command_dispatch 独立链路），非指三网关无 external-call 包装活链；三网关包装 external-call 为真实生产动作（b7 2.2 / M6），如实登记不混用。
2. **任务书主锚原句截断与实时真值**：任务书正文主锚在消息中截断为「| bridge-chat-c；」，按「实时 origin/main 自动抽出的原句，不手写近似串」口径从 C-15 第二节 L36 读到完整六列，与本文描述一致；不触发 question。
3. **证据基线时点差（线性后继，不阻断）**：任务书写「以实时 origin/main 1f3ec9f 为唯一证据基线（含四个 merge 与 PEN_A / PEN_C answer 及 a 续派登记）」，交付动作要求开工前 ff-only 同步「本任务书登记」；实时 ff-only 后 HEAD 为 4c7bad3（1f3ec9f 之后追加的本任务书登记），工作区干净、线性推进无分叉。以实时 main 为准，如实登记。
4. **C-9「对应边界段」体例差（登记项，不阻断）**：任务书写「与 C-9 对应边界段逐行对拍」，实仓 C-9 为六段占位接口边界契约，无「第 9 步协议字段退役」独立边界段（六段止于 ### 6. restore）；相关锚为全局不变量 G1（L11-12，STATUS 恒 declared-placeholder、协议退役面）与第三节验收口径 L102「不碰 B-7 协议字段退役面」。本片按实仓真实锚点取证并用夹具断言，不改写任务书、不擅自扩范围；按 A-9 双闸门判为体例/措辞差而非硬约束冲突，不触发 question。C-14 第六节仅 execute 段实装登记（B-12）、不含协议退役断言面，亦如实登记。
5. **C-15 第 9 行「28 / 30 / 10 文件」历史快照计数 vs 实时宽口径计数**：C-15 与 b10 基线为 c817dea / 34e6029，历史「非测试文件活链命中」28 / 30 / 10；实时 4c7bad3 全仓宽口径 51 / 51 / 24 文件（123 / 153 / 75 行），非测试非文档活链 9 / 20 / 4 文件。差量来自后续新增报告（b7 / A-13 / C-17 / C-18 / C-16 / c15 自身）、总线消息 docs/bus/*.md、夹具与契约 lib（standard_chain_b9_slot_resolver.js / standard_chain_contract.js / standard_slot_m345.js），非运行期装配变化；沿用 A-13 差异登记同型口径。本片不改写历史文面、不预设口径、如实登记供分发方复核。
6. **C-8 九步表第 9 行「未交付 / 依赖 B-7 是」与 b7 已合入替换位列全并存**：C-8 为 6394fbf 历史快照推演（「B-7 未交付」指 B-7 总结论与实装面未下发），b7 收口片只交付「现状 + 替换位列全说明」、不写实现面代码，B-8 / B-9 纯函数层已入 main 但只做转换 / 拒绝语义、未装配运行时 M。按「不改他笔已合入 .md 源码本体」保留原文，不构成新前置、不触发实装。
7. **S3 / S4 判态不变**：S3 契约面判一致≠运行时退役，三项收口条件（S2 装配实装并验收 / 协议字段按替换位逐槽切到标准链并经真实使用 / 分发方复判后 status 方可转实装）未满足；S4 三项硬前置仍未全满足，阶段 3 不进入摘除步。b10 S2 行与 C-8 第 5 步行历史措辞并存按原文保留、不翻 STATUS；EXECUTE_STATUS 独立导出作用域不变。第 9 步只读取证不构成执行权迁移、不构成新前置、不构成实装或摘除授权。
8. **同面隔离（19:08 / 22:02 / 23:55 分发方已判，不改写）**：与 C-18 第 8 步、A-13 第 6 步、C-17 第 7 步、B-14 六段 dedupe、a reply / b buildCard 在途面的取证对象、C-15 行锚、夹具、交付文件全不同；本片只做主锚第 9 步一步，不扩第 4 / 5 / 6 / 7 / 8 步、不扩六段其余声明态、不扩 S1 L10。

## 五、边界与结论（复核输入）

- 范围：只新增本报告、flask_server/tests/js/test_standard_chain_c19_step9_protocol_retirement_inventory.test.js 与 docs/work-ai-c.md 第五节只追加完成记录；零代码改动、0 删除、docs 只追加。
- 活链九文件（06_execute.js / 05f_parse.js / 00_data.js / 05g_cards.js / 05j_card_sig.js / 05c_prompt.js / 01b_bridge.js / translator.js / dialog.html）与 standard_chain_adapter.js / standard_chain_contract.js 本体零改动（只读反查除外）；旧标记全部保留；STATUS 恒 declared-placeholder（含 PROTOCOL_RETIREMENT_CONTRACT.status）；EXECUTE_STATUS 作用域不变；c6 九文件顺序表未执行；remote_bridge / 三网关 / flask_server 下 .py 零改动。
- 运行时 M 保持未装配；钩子注册数量为零；切换开关数量为零；运行期探测分支数量为零；docs/bus 他人消息零触碰；不碰 A-13 / B-14 / C-17 / C-18 / A-11 / A-12 / B-13 / C-15 / C-16 报告与夹具本体、不碰 extend/dialog/AUDIT.md；hooks / 90-70 阈值 / js_coverage_baseline.json 零改动，未用 --update-baseline。
- 反查夹具按 C-14 / C-16 / A-12 / B-14 / C-17 / A-13 / C-18 形态：按字符码 10 切行、普通 indexOf / split、零反斜杠零正则、只读 require node:* 与已合入 lib、无 fs 写 / shell / 网络、新增被测 JS 源 0；require 头部序按 A-10 口径与 c18 / a13 / c17 / b14 / c16 同族差异化归零，夹具用 c19Test( 直接调用形态、不硬套 .test( 计数。
- 判态锚（19:45 为准，不改写）：S1 不变（L10 接真实模型缺外部服务与凭证、用户侧另行排期）；S2 第 5 步 execute 单点已闭合、整体未齐备 / 待对拍；S3 不变；S4 三项硬前置仍未全满足，阶段 3 不进入摘除步。
- 本报告差异登记与结论仅为分发方复核输入，不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不代分发方拍板、不预设下发时点。

## 六、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| 反查夹具 | node --test flask_server/tests/js/test_standard_chain_c19_step9_protocol_retirement_inventory.test.js | rc=0，10 tests / 10 pass / 0 fail（c19Test( 直接调用 10 次；52 项 needle 落盘前预检全坐实） |
| 前端全量 | python scripts/hooks/check_js_tests.py | rc=0，665 tests / 665 pass / 0 fail；分母按新增夹具 10 用例如实增长（当前 main 655 = 611 + C-17 10 + B-14 12 + A-13 12 + C-18 10，+ 本笔 10）；本机 node v24.11.1 打印 跳过覆盖率门禁：未解析到覆盖率报告，如实标注为跳过、由分发方环境复验 |
| 结构质量 | python scripts/quality_rules.py | rc=0，十二项全为 已知 存量，零 [新增]；A-10 防重窗 require 序对 c18 / a13 / c17 / b14 差异化归零坐实 |
| 全量 pytest | python -m pytest tests -q -p no:cacheprovider（flask_server 下串行单进程） | rc=0，1085 passed，零 failed（本片无 py 用例，分母不变） |
| 七道钩子 | pre-commit run --all-files | rc=0，7 道逐个 Passed，Failed=0，未用 --no-verify |
| 文档同步 | python scripts/check_doc_sync.py | rc=0，单独命令实跑通过（pre-commit 文档同步道亦 Passed） |
| 差异检查 | git diff --check / git diff --cached --check | 均 rc=0，无空白错误 |
| 范围 | git status --short / git diff --numstat | 2 新文件 + docs/work-ai-c.md 只追加 7 行 / 0 删除；零代码改动 |

> 实测结果以收口轮实跑为准；覆盖率门禁本机 node v24 打印跳过，由分发方环境复验。
