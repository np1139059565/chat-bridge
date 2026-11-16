# A-12 parse 段边界反查与 C-9 / C-14 状态标注对拍报告

> 性质：零代码改动的只读取证片（dispatcher-20261116T103235-72e379，阶段 3 续派 parse 单段圈定，不扩 dedupe / 其余四段 / 九步余面 / S1 L10）。只新增本报告与一份反查夹具，docs/work-ai-a.md 第五节只追加；不改他笔已合入 .md 与源码本体。
> 证据基线：实时 origin/main（开工 fetch --prune / merge --ff-only 完成、工作区干净，actor=a，branch=work/ai-a）；实时基线取 HEAD e7c3b44 实测。
> 引用（只读）：C-9 extend/lib/standard_chain_boundary_contract.md、C-14 extend/lib/standard_chain_c14_signature_table.md、C-15 docs/c15-s2-remaining-surface-inventory.md、b10 docs/b10-removal-readiness-report.md、A-11 / B-13 同型先例；判态锚以 19:45 dispatcher-20261115T194511-c92792 为准。
> 本报告所有差异登记仅为分发方复核输入：不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。

## 一、取证范围与方法

- 圈定：六段余面 parse 单段，逐项落「边界段原文 / 当前态 / 活调用方 / 依赖 / 禁区」，与 C-9 第一节 ### 1. parse(block) 段、C-9 第二节 parse 状态行、C-14 第二节 parse 签名行、C-15 第二节 parse 逐面基线、b10 就绪度表 S2 行逐行对拍。
- 方法：adapter（node 分支）实参直调断言返回形状与归一语义；契约 .md / 签名总表 / 余面判定 / 就绪度报告 / 活链文件 fs 只读反查，按字符码 10 切行、普通 indexOf / split（零反斜杠零正则）；关键串命中计数与 git grep 对拍。
- 夹具：flask_server/tests/js/test_standard_chain_a12_parse_boundary.test.js（10 用例，新增被测 JS 源 0，无 fs 写 / shell / 网络）。

## 二、代码实况：adapter.parse 逐项钉死

实时实仓（e7c3b44）`extend/lib/standard_chain_adapter.js`：L12 `var STATUS = 'declared-placeholder'`、L13 `var EXECUTE_STATUS = 'implemented-S2-step5'` 独立导出、L14 `var KEY = 'tool_call.id'`、L15 `function parse(block) { return { by: KEY, block: block || null, status: STATUS }; }`、L69 导出表 `parse: parse`（实仓行号实测；b10 历史快照 L11 / L7 措辞为 34e6029 时点行号，按 19:45 口径登记差异、不改写）。

| 边界项 | 实测（node 实参直调） | 与契约的关系 |
|---|---|---|
| 返回形状 | 恰三键 `by / block / status`，不产出 tool_calls、不含 call 键 | C-9 第一节四行、C-14 第二节 parse 行逐字一致 |
| code 块入参 | `out.block` 与入参同一引用，原样回显、不读 code | C-9「原样引用回显 / 不读 code、不产出 tool_calls」一致 |
| 缺参归一 | null / undefined / 0 / 空串 / false 一律 `block: null` | C-9 null / undefined 行一致，并向 G3 延伸 |
| 空 block | `{}` 真值原样回显、不补字段、不归一为 null | C-9「空对象为真值，原样回显、不补字段」一致 |
| truthy 直通 | 42 / 'x' / true / [] / {any:1} 原样引用回显 | C-9 第四行「block 原样引用回显」一致 |
| 不抛错 | NaN / {} / 3.14 等任意类型入参零抛错 | G3「异常输入不抛错」一致 |
| 幂等 | 同参两次调用返回新对象、深相等、不共享返回引用 | G3 回显语义一致 |
| 入参不改写 | 入参对象键数与内容零变化 | 纯声明段无副作用，一致 |
| STATUS / KEY / EXECUTE_STATUS | 恒 `declared-placeholder` / `tool_call.id` / `implemented-S2-step5` | G1、G2 一致；EXECUTE_STATUS 作用域不变 |

## 三、C-9 边界契约对拍（第一节 ### 1. parse(block) 段 + G1 / G2 / G3 + 第二节状态行）

| 契约点（实文反查） | 在文证据（行前缀 / 关键串，均恰 1 处） | 与实况判定 |
|---|---|---|
| 段标题 | `### 1. parse(block)` | 一致 |
| parse(null) 行 | 行前缀反查恰 1 行 → 返回 `{ by: KEY, block: null, status: STATUS }` | 一致 |
| parse(undefined) 行 | 行前缀反查恰 1 行 → 同上，缺块归一为 null | 一致 |
| parse({}) 行 | 行前缀反查恰 1 行 → 空对象为真值，原样回显、不补字段 | 一致 |
| code 块行 | 行前缀反查恰 1 行 → block 原样引用回显、不读 code、不产出 tool_calls | 一致 |
| 说明行 | `占位期不解析、不校验 type` | 一致 |
| G1 | `G1 **STATUS 恒为 `declared-placeholder`**` | 一致 |
| G2 | `G2 **唯一键**`（标准 `tool_call.id` 与 tool 三键） | 一致 |
| G3 | `G3 **异常输入不抛错**` | 一致 |
| 第二节状态行 | `| parse | declared-placeholder |`（含 `tool_call.id + tool 三键`、`n/a`、`否`） | 一致 |

## 四、C-14 签名总表对拍（第二节 parse 签名行 + 第六节 B-12 只追加登记）

- 第二节签名行 `| parse(block) |` 恰 1 行：`standard_chain_adapter.js | 返回 by=KEY、block、status=STATUS | 一致 | declared-placeholder |`——与实时形态逐格一致。
- 第六节「execute 段实装登记（B-12，2026-11-15 追加）」只追加节不含 parse 字样（slice 反查零命中）：parse 段仍纯声明，与 EXECUTE_STATUS 独立导出并行不悖，抬头与历史表按 19:45「不改写他笔已合入 .md 源码」保持原文。

## 五、C-15 逐面基线与 b10 就绪度对拍

- C-15 第二节 parse 行（`| parse |` 恰 1 行）：`{ by: KEY, block, status: STATUS }，block 缺参回落 null，空 block 原样回显`，对拍 C-14 / C-9 判「一致」——与本报告第二节实测逐格吻合。
- b10 就绪度表 S2 行 `| S2 #7 tool_calls 意图执行 |` 恰 1 行（实文行前缀实测），其「装配面九步第 5 步仍 declared-placeholder」为 34e6029 历史快照措辞；按 19:45 收紧口径：第 5 步 execute 单点已闭合、整体未齐备 / 待对拍。本片不改写 b10 原文，仅登记「历史快照 vs 实时裁定」口径差异供分发方复核；b10 基线保持只追加。
- EXECUTE_STATUS 命中计数（git grep -c 实测）：a11 / execute / b13 / c15 四夹具 2 / 5 / 2 / 3 处；较 C-15 时点增长系 A-11 / B-13 / C-15 自身引用，作用域仍限 execute 段、未进 C-14 六段断言面。

## 六、运行期下游取证（parse 段纯声明、零调用方）

- adapter 源 `function parse(` 恰 1 处（唯一定义）、`.parse(` / `JSON.parse(` 零命中；`standard_chain_contract.js` 全文零 `parse` 字串（键映射真源 makeToolCallId / nonceFromToolCallId 不涉 parse 面）。
- 活链六文件（06_execute / 05f_parse / 00_data / 05g_cards / 05j_card_sig / dialog.html）对 `AD.parse(` / `Adapter.parse(` / `AIMirrorStandardChainAdapter.parse` / `adapter.parse` 四串全部零命中——adapter.parse 运行期零调用方；dialog.html 装载 adapter 本体但无 parse 下游。
- `.parse(` 计数恒等：05f 5 处、00_data 1 处、05g 1 处、其余 0，与各文件 `JSON.parse(` 计数逐文件相等（夹具断言钉死）——全部为 JSON 反序列化、非 adapter.parse 调用（05f JSON.parse 上下文逐一精读核对：修复解析 / 切片解析 / src 解析等纯 JSON 面）。
- 依赖 / 禁区（沿 C-15 第二节第 4 步面）：依赖第 5 步单点闭合仅作基线；禁区为活链零改动、STATUS 保持声明态、不把声明态翻成已装配。

## 七、差异登记与结论

1. **主结论零差异**：parse 返回形状 / 缺参归一 / 空 block 真值 / truthy 引用回显 / 不抛错 / 幂等 / STATUS 恒声明态 / KEY=tool_call.id / 唯一定义 / 运行期零调用方，与 C-9 第一节、G1-G3、第二节状态行、C-14 第二节 parse 行、C-15 parse 行逐格一致。
2. **b10 历史快照措辞漂移**：S2 行「装配面九步第 5 步仍 declared-placeholder」、L42 附近「execute(card) 占位（L11）」与 B-12 后实况（execute 已实装、parse 实测 L15）并存，按 19:45 收紧口径登记，不改写原文。
3. **C-15 快照 KEY 示值**：分发方随任务书快照中 adapter 导出示值 KEY='.id' 为 B-12 时点旧值；实时实仓 KEY='tool_call.id'（node 实参直调 + A-11 / B-13 实时夹具断言同值互证），C-9 / C-14 / C-15 实文均以 KEY 符号或 tool_call.id 表述、无矛盾。
4. **EXECUTE_STATUS 计数增长**：4 夹具 12 处命中，均系自身登记或同型先例引用，作用域不变，不构成新前置。
5. parse 仅声明态边界反查，不构成执行权迁移、不构成新前置；S1 不变、S2 第 5 步单点已闭合 / 整体未齐备 / 待对拍、S3 不变、S4 三项硬前置未全满足，阶段 3 不进入摘除步。

## 八、边界与只追加记录

- 范围：只新增本报告、`flask_server/tests/js/test_standard_chain_a12_parse_boundary.test.js` 与 docs/work-ai-a.md 第五节只追加完成记录；零代码改动；新增被测 JS 源 0。
- 不碰：活链九文件与 adapter / contract 本体、C-15 / C-16 / A-11 / B-13 / b10 报告与夹具本体、docs/bus 他人消息、hooks / 90-70 阈值 / js_coverage_baseline.json、extend/dialog/AUDIT.md；不装配运行时 M、不注册钩子、不建切换开关、不新增运行期探测分支、不摘除任何旧标记、不翻任何 STATUS（含不扩用 EXECUTE_STATUS）、不执行 c6 顺序表；docs 只追加（0 删除）。
- 防重窗：夹具头部 require 五行与 a11 同族样板构成跨文件重复窗，按 A-10 口径调序差异化归零（quality 全量 0 新增，闸门组数对账回基线，单文件 3 连跑全绿不变）。
- 验收实测：单文件 node --test 3 连跑全绿（10 tests / 10 pass / 0 fail）；全量 js 门禁、全量 pytest、quality / doc-sync / pre-commit / diff --check 见台账完成记录（以收口轮实跑为准）。

> 本报告仅为分发方复核输入，不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。
