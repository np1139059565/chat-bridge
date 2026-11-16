# B-15 buildCard 单点边界反查与 C-9 / C-14 / C-15 / b10 状态标注对拍（只读取证）

> 性质：只读边界反查取证片，零代码改动、新增被测 JS 源 0。
> 任务书：dispatcher-20261116T222202-585cde（并行续派·六段声明函数边界反查·buildCard 单段，指派 b）。
> 证据基线：origin/main b3c7d97（B-14 已于 4ce0fd1、C-17 已于 a25fc98 合入后的实时 main）；行号为本轮实仓实测。
> 判态锚：以 19:45 dispatcher-20261115T194511-c92792 为准，不改写——S1 不变；S2 第 5 步 execute 单点已闭合、整体未齐备 / 待对拍；S3 不变；S4 三项硬前置仍未全满足，阶段 3 不进入摘除步。
> 本片仅声明态边界反查，不构成执行权迁移、不构成新前置、不触发摘除或实装动作。

## 一、取证对象与锚点

| 取证对象 | 文件 | 锚点（本轮实测） |
| --- | --- | --- |
| buildCard 唯一定义与导出 | extend/lib/standard_chain_adapter.js | L16 定义、L70 导出（81 行内 buildCard 恰 3 处：定义 1 + 导出行 2 字样） |
| 常量三件与 UMD | 同上 | L12 STATUS / L13 EXECUTE_STATUS / L14 KEY；L76-80 node 导出与 window 挂载 |
| C-9 边界段与状态行 | extend/lib/standard_chain_boundary_contract.md | L33 段头、L37-L39 三行边界、L41 说明行、L92 状态行 |
| C-14 签名与总表 | extend/lib/standard_chain_c14_signature_table.md | L32 签名行、L30 / L84 六段接口名行、第六节（L113 起）零 buildCard |
| C-15 标注行 | docs/c15-s2-remaining-surface-inventory.md | L16 第一节 buildCard 行、L32 第二节第 4 步行（仅作标注对拍输入、不取为范围） |
| b10 就绪度表 | docs/b10-removal-readiness-report.md | 全文零 buildCard 字样；L17 S2 #7 行原样在文 |
| 运行期建卡活链 | extend/dialog/parts/05g_cards.js | L33 / L67 / L196 建卡族、L112 / L127 落 card.toolCall / toolCallId、L123 bridge-chat-call 信封 |
| 键映射纯函数 | extend/lib/standard_chain_contract.js | L9 PREFIX、L10 makeToolCallId、L41 导出（45 行） |

## 二、边界段原文与实源逐行对拍

C-9 第一节「### 2. buildCard(call)」三行边界逐行与实测（node 分支 require adapter）对拍：

| C-9 输入（L37-L39） | C-9 返回形状 | C-9 不变量 | 实测 | 结论 |
| --- | --- | --- | --- | --- |
| `buildCard(null)` | `id: null` | 缺 call 不抛错 | id 为 null、恰三键、不抛错 | 一致 |
| `buildCard({})` / 缺 `id` | `id: null` | 缺 id 回落 null，不生成替代 id | {} / { id: null } / { id: undefined } / { name } 均 id 为 null | 一致 |
| `buildCard({ id: 'call_n1' })` | `id: 'call_n1'` | 标准键原样保留 | id 逐字回显、by=KEY、status=STATUS | 一致 |

说明行（L41）「不校验 `function.name`、不把卡片落到消息树、不触发建卡流程」：实测输出恒三键（by / id / status），无 function / 消息树 / 建卡副作用字段，一致。

补充归一语义（C-9 未单列、本轮实测）：实现为 `(call && call.id) || null`——falsy id（'' / 0 / false）归一 null，truthy id（含对象）原引用直通；每次调用返回新对象（形状幂等、逐字段深相等）；不比较不排序不合并。

## 三、当前态与活调用方

- 当前态：buildCard 仍 declared-placeholder 声明回显——L16 单行定义返回 `{ by: KEY, id: (call && call.id) || null, status: STATUS }`，恰三键；STATUS 恒 declared-placeholder、KEY 恒 tool_call.id；不扩用 EXECUTE_STATUS（adapter 源内 EXECUTE_STATUS 恰 6 处：L13、L24、L43、L53、L67，均为 B-12 execute 实装登记与导出，buildCard 输出 status 取值与 EXECUTE_STATUS 不同值）。
- 活调用方：运行期零调用方——四探针串（AIMirrorStandardChainAdapter.buildCard / adapter.buildCard( / AD.buildCard( / Adapter.buildCard(）对 parts 56 份 .js + adapter.js + contract.js + dialog.html 共 59 文件全零命中；git grep -F 全仓命中仅为 C-16 报告（L15 / L38）与 C-16 夹具（L56）等已合入文档 / 测试产物，非运行期调用方。
- 全仓宽口径 buildCard 144 行 / 35 文件（实测时点 b3c7d97，本笔报告与夹具未入库不计）——含契约 .md、总线登记、夹具与 _buildCard* 同名前缀文本命中；运行期调用方为 0。
- 运行期建卡与候选仍由 05g_cards.js 旧直调路径承担：L33 _buildCardsForIncoming → L67 _buildCardsForOne → L196 _buildCardForBlock，L112 _translateToolCalls → L127 落 `card.toolCall = calls[0]; card.toolCallId = calls[0].id;`（L123 bridge-chat-call 信封、L227 第二处 toolCallId），与 C-15 第二节第 4 步行「运行期建卡与候选仍由 05g_cards.js 承担」一致。
- 依赖与禁区：第 5 步单点已闭合可作基线；整链以三键重建待后续单点；S4 旧标记摘除任务书与 c6 九文件顺序表为禁区前置；contract.js makeToolCallId 纯函数在码（PREFIX 为 call_），运行期建卡未接入标准链。

## 四、四处标注对拍结论

- C-9（L33-L41 段 + L92 状态行）：三行边界 + 说明行 + declared-placeholder 状态行与实仓逐字一致；G1-G4 全量串在文。
- C-14（L32 签名行 + L30 / L84 六段接口名 + 第六节）：签名行唯一在文；第六节零 buildCard 字样，B-12 实装登记不涉及 buildCard。
- C-15（L16 第一节行 + L32 第二节第 4 步行）：三键形状与「id 缺参回落 null」与实测一致；第 4 步行「buildCard 仍 declared-placeholder 回显」与实仓一致（仅作标注对拍输入、不取为范围）。
- b10（全文 + L17 S2 行）：零 buildCard 字样；S2 #7 行原样在文（登记的是 execute 第 5 步，不与本片冲突）。

## 五、差异登记（仅供分发方复核，不代拍板、不改判态）

1. 主结论零差异：buildCard 声明态边界（三键回显 / 归一语义）与 C-9 / C-14 / C-15 / b10 四处标注同实时实仓一致；运行期零调用方。
2. C-16 宽口径历史快照漂移：C-16 登记「buildCard（全仓宽口径）93 行 / 28 文件」，本轮实测 144 行 / 35 文件——C-17 / B-14 总线消息与报告文本新增字样命中所致，运行期调用方仍 0，非行为漂移。
3. b10 / C-15 历史快照行号与措辞：b10 L33 依赖列「步骤 4」为九步序号引用（非本片范围）；C-15 第 4 步行为 461 字符长行原样在文；均不阻断对拍。
4. C-15 第一节为五段对拍表述（parse / buildCard / reply / dedupe / restore 五行，execute 由 B-12 单独登记），与本片单段（第 2 段）反查口径分层，不矛盾。
5. 05g 内 _buildCard* 同名前缀族（L33 / L50 / L54 / L67 / L100 / L196 等旧建卡直调路径函数）宽口径 grep 会命中 buildCard 子串，与 adapter.buildCard 是同名前缀异构体；四探针串精确反查不命中，口径分层已注明。
6. S2 / S4 判态不变：以 19:45 锚为准——S2 整体未齐备 / 待对拍、S4 三项硬前置仍未全满足；本片不构成执行权迁移、不构成新前置。

## 六、结论

buildCard 单段声明态边界与四处标注对拍零主差异；运行期 buildCard 零调用方、运行期建卡仍由 05g_cards.js 旧直调路径承担；差异登记 6 项均为口径分层或历史快照漂移、非行为差异。本报告与配套夹具为只读取证产物，仅供分发方复核输入，不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。

## 七、复核输入边界

本报告与配套夹具 flask_server/tests/js/test_standard_chain_b15_buildcard_boundary.test.js 为只读取证产物（夹具 12 条：形状恰三键 / 缺 call 归一 / 缺 id 回落 / 标准键回显 / falsy 归一与 truthy 直通 / 同异入参回显 / 幂等新对象 / C-9 / C-14 / C-15 / b10 对拍 / 运行期零调用方与唯一定义导出 / 常量作用域与 contract 键映射）。差异登记仅为分发方复核输入，不代拍板。
