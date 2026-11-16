# B-13 restore 单点边界反查与 C-9 / C-14 状态标注对拍报告（只读取证）

> 任务源：dispatcher-20261115T222437-661433（阶段 3 续派，只读取证片，不是实装授权、不是验收结论）。
> 证据基线：origin/main 7be1210（含 A-11 验收合入与 B-12 实装面）；本报告结论均为该基点实仓实测。
> 性质：零代码改动；仅三件新增——本报告 + 反查夹具 + docs/work-ai-b.md 只追加完成记录。

## 一、范围与方法

- 范围：standard_chain_adapter.js 的 restore 段（定义 L61-L64、导出 L74）、boundary_contract.md（C-9）restore 段两处标注、c14_signature_table.md（C-14）第二节 L36 restore 行与第六节 L113 B-12 追加节、restore 运行期装配面（06_execute.js / 05f_parse.js / 00_data.js / 05g_cards.js / 05j_card_sig.js / dialog.html）。
- 方法：adapter 经 node require 只读（UMD node 分支）；.md 与活链文件 fs 只读、按字符码 10 切行、普通 indexOf / split，零反斜杠零正则；无 fs 写 / shell / 网络；结论按实仓取证登记、不预设。

## 二、restore 段逐项边界核对（代码实况 vs 文档标注）

| # | 核对项 | 代码实况 | C-9 标注 | C-14 标注 | 判定 |
| --- | --- | --- | --- | --- | --- |
| 1 | 返回形状恰五键 by / sessionId / id / noMessageFingerprint / status，无 msgId 键 | L61 函数体返回字面量 | 第一节第 6 段表格 + L96 第二节行 | L36 行「返回 by=KEY、sessionId、id、noMessageFingerprint=true、status=STATUS」 | 一致 |
| 2 | STATUS 恒 declared-placeholder | STATUS 常量与返回值 | L96 行 | L36 行末列 | 一致 |
| 3 | KEY 恒 tool_call.id | KEY 常量 | G2 / L96 行 | L36 行 by=KEY | 一致 |
| 4 | noMessageFingerprint 恒 true、键不含 msgId | 字面量 true | G4（L17） | L36 行 | 一致 |
| 5 | 空 sessionId 归一 ''（String 包装） | String(sessionId 或 ''） | 第 6 段表「空 sessionId → sessionId: ''」 | L36 行 sessionId | 一致 |
| 6 | 缺 call / 缺 id 回落 null 不抛错 | (call && call.id) || null | 第 6 段表「缺 call → id: null、不抛错」 | L36 行 id | 一致 |
| 7 | 幂等：每次新对象深相等、不累加、不写会话状态 | 纯函数 | G4 + 第 6 段表「重复恢复」行 | — | 一致 |
| 8 | 入参对象不被改写（纯读） | 只读两属性 | G4 幂等蕴含（夹具补断言） | — | 一致 |
| 9 | 唯一定义：function restore( 全仓恰 1 处（L61），UMD 导出 L74 | 实测 | 未显式承诺（本片新增取证） | — | 新证据 |
| 10 | 运行期零调用方：.restore( 全 extend 树 0 命中 | 实测 | 第 6 段说明「只钉声明语义，不改运行时」 | — | 一致 |

## 三、C-9 / C-14 状态标注对拍结论

- C-9（boundary_contract.md 共 143 行）：L17 G4 刷新恢复键语义、L75 第 6 段标题、L75-L82 边界表四行、L96 第二节状态行（tool 三键 + true（恒真） + 否），逐字在文、与代码实况一致。
- C-14（c14_signature_table.md 共 129 行）：L29 六段接口名行、L36 第二节 restore 签名行（一致 / declared-placeholder）、L83 C-9 六段边界行、L113 第六节标题；B-12 追加节（L113 起 16 行）不含 restore 字样，restore 段标注无漂移。
- 差异登记：无（零差异；本节仅为分发方复核输入，不代拍板、不改判态）。

## 四、运行期零装配面取证

- dialog.html 装载 standard_chain_adapter.js（B-12 追加的装载行仍在），restore 零装配不变量成立：不装配 M、不注册钩子、不建切换开关，全树 .restore( 零命中。
- 05j_card_sig.js 含 restore 字样 7 处（L86 / L96 / L123 / L124 / L130 / L132 / L133），均为 05j 自身 _restoreExecutedCards 与卡片级计数器文案，不是 adapter.restore 调用；standard_chain_contract.js 中 restore 字样 0 处；恢复键迁移方向（标准 call 优先 + 旧 msgId 双查、去消息指纹）由 05j / 05g 已合入实现承载，adapter.restore 保持声明态。

## 五、夹具与实测

- 夹具：flask_server/tests/js/test_standard_chain_b13_restore_boundary.test.js（123 行、7 测试），沿用 A-11 形态：零反斜杠零正则、字符码 10 切行、只读 require、fs 只读反查；新增被测 JS 源 0；tests/js 下夹具总数 55→56。
- 本机实测：node --test 单文件连续 10 轮 7 tests / 7 pass / 0 fail（10/10 全绿）；全量 js、全量 pytest、pre-commit 七道、quality 等以 docs/work-ai-b.md 第五节 B-13 完成记录同轮实测为准；覆盖率门禁以分发方环境判定（本机 node v24 报告前缀「跳过」不作达标依据，沿用 A-11 先例口径）。

## 六、明确不做（沿用任务书清单）

- 不改他笔已合入 .md 源码本体；不碰活链（05g_cards.js / 05j_card_sig.js / 05c_prompt.js / 05f_parse.js / 06_execute.js / 00_data.js / 01b_bridge.js / translator.js / dialog.html / standard_chain_adapter.js）；不摘除任何旧标记、不翻任何 STATUS、不扩用 EXECUTE_STATUS、不装配运行时 M、不注册钩子、不建切换开关、不新增运行期探测分支、不执行 c6 九文件顺序表、不动 docs/bus 他人消息；docs 只追加；不自行圈定下一实装面、不代分发方验收或裁定。未跟踪文件 extend/dialog/AUDIT.md 非本任务产物，未纳入、未改动。
- S4 旧标记摘除三项硬前置仍未全满足，阶段 3 不进入摘除步；S2 第 5 步单点已闭合、整体待对拍；S1 / S3 不变，以 19:45 判态为准。

## 七、结论

- restore 段「文档标注 vs 代码实况」零差异：C-9 restore 段两处标注、C-14 第二节 L36 行与第六节 B-12 追加节均与实仓一致；restore 运行期唯一定义、零装配、零调用方。差异登记为空，仅供分发方复核，不构成新前置、不触发任何摘除或实装动作。
