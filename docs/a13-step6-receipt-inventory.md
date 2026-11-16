# A-13 九步第 6 步 tool 消息回执链路逐行取证与标注对拍报告

> 性质：零代码改动的只读取证片（dispatcher-20261116T202644-440f67，并行补派·九步第 6 步回执逐行取证，沿用 C-16 九步第 4 步逐行取证片形态）。只新增本报告与一份反查夹具，docs/work-ai-a.md 第五节只追加；不改他笔已合入 .md 与源码本体。
> 证据基线：开工时点 origin/main 2fed217（fetch --prune / merge --ff-only 完成、工作区干净，actor=a，branch=work/ai-a）；收口前 fetch 复核、ff-only 跟进至 b3c7d97（b14 合入后）作为提交基点；A-12 合入 a4d9f2d、A-11 1ddeee1、C-16 a6208bf 均在祖先链（merge-base --is-ancestor 实测 rc=0，ff 跟进后仍在祖先链）。
> 引用（只读）：C-9 extend/lib/standard_chain_boundary_contract.md、C-14 extend/lib/standard_chain_c14_signature_table.md、C-15 docs/c15-s2-remaining-surface-inventory.md、C-8 extend/lib/standard_chain_field_matrix.md、b10 docs/b10-removal-readiness-report.md、A-11 docs/a11-reply-boundary-inventory.md（隔离参照，不碰本体）。
> 本报告所有差异登记仅为分发方复核输入：不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。

## 一、取证范围与方法

- 圈定：九步余面第 6 步 tool 消息回执单步，逐项落「逐文件落点 / 当前态 / 活调用方 / 依赖 / 禁区」五项；与 C-8 第二节第 6 步行、C-15 第二节 | 6 | 行、C-9 第一节 ### 4. reply(msg) 边界段、C-14 第二节 adapter 表 reply 行与 standardToolMessage 行、b10 就绪度表逐行对拍。
- 面内对象三件：standard_chain_contract.js standardToolMessage 三键纯函数（含 String 归一语义）、standard_chain_adapter.js reply 段声明态、运行期回执 bridge-chat-res 旧链（05f_parse.js / 05c_prompt.js / 00_data.js / 06_execute.js / 05g_cards.js / 05d_memory.js / 07_cards.js / 05_messages.js / 05i_files.js / 06c_file_attach.js / 08b_settings.js / 03_bridge.js / translator.js）。
- 与 A-11 隔离：A-11 已消费「六段 reply 声明函数边界反查」单点面；本片是九步第 6 步链路级取证，覆盖 standardToolMessage 纯函数实测、translator fromToolMessage 运行期活翻译面、回执旧链 13 文件逐行落点与 git grep 全仓计数，不重做 A-11 的段内边界矩阵（其结论仅引用不复测）。
- 方法：夹具只读 require 已合入 adapter / contract / translator 三个 lib；契约 .md / 就绪度报告 / 活链文件 fs 只读反查，按字符码 10 切行、普通 indexOf / split（零反斜杠零正则）；关键串命中计数与 git grep 对拍；无 fs 写 / shell / 网络。

## 二、代码实况：第 6 步三面逐项钉死

### 2.1 standardToolMessage 三键纯函数（contract 侧）

源码定义（standard_chain_contract.js L15-17，全仓唯一定义）：

    function standardToolMessage(callId, content) {
      return { role: 'tool', tool_call_id: String(callId), content: String(content == null ? '' : content) };
    }

五项实测（夹具第 1-3 节）：恰三键 role / tool_call_id / content、无第四键（无 msgId / name / fingerprint）；role 硬编码 'tool'；callId / content String 归一（null / undefined / 42 / 对象一律转字符串，content null 归一空串）；幂等每次新对象；PRE_DISPATCH_HOOK_CONTRACT / PROTOCOL_RETIREMENT_CONTRACT 冻结对象 status 恒 declared-placeholder。全仓 git grep 命中 26 文件（开工基线 2fed217；收口基点 b3c7d97 复测 27，差量仅 b14 报告与总线消息；extend/lib 6 + docs 5 + flask_server/tests/js 15），代码侧唯一定义与导出各 1 处，无运行期调用方——纯函数在码、未装配，与 C-15 第二节 | 6 | 行「三键纯函数在码」一致。

### 2.2 adapter.reply 声明态（四键回显、零下游）

源码定义（standard_chain_adapter.js，A-11 已钉、本片复核维持）：恰四键 { by: KEY, role: 'tool', tool_call_id: (msg && msg.tool_call_id) || null, status: STATUS }；role 硬编码常量、content 不回显、缺键归一 null、不抛错、幂等新对象；STATUS 恒 declared-placeholder、KEY 恒 tool_call.id。'.reply(' 全仓 12 文件命中，全部为 docs（a11 报告与 bus 消息）与 flask_server/tests/js 夹具（以 AdapterLib.reply( 调用形态测声明态），extend/ 侧零命中；adapter 本体为 function reply 定义 + reply: reply 导出（L59 / L72）；'AIMirrorStandardChainAdapter.reply' 全仓唯一命中为 docs/a11-reply-boundary-inventory.md（文档自身引用）；extend/dialog/parts/ 与 extend/content/ 活链零 reply 调用。adapter.reply 无运行期下游——与 C-15 第二节 | 6 | 行一致。

### 2.3 运行期回执旧链：bridge-chat-res 落地与消费全景

全仓 git grep 命中 44 文件 118 行（开工基线 2fed217；收口基点 b3c7d97 复测 47 文件 126 行，差量仅 b14 报告与总线消息）。运行期链路（extend/ 前端活链）逐文件落点：

| 文件 | 命中 | 落点性质 | 五项登记 |
|---|---|---|---|
| extend/lib/translator.js | 4 处（L90/161/166/177） | 标准链本体运行期活翻译面：fromToolMessage(msg, compact) 把标准 tool 消息（role:'tool' 判定、content JSON 解析整体带出、tool_call_id 剥 call_ 前缀还原 nonce、success 缺省补 true）翻成 bridge-chat-res 文本贴回网页对话；toToolMessage 为执行信封→标准 tool 消息反向纯函数 | 落点：运行期翻译；当前态：活链在用（阶段 2 标准链本体）；活调用方：toToolMessage / fromToolMessage 双向导出、dialog.html L25 装载；依赖：第 4 步建卡键落运行期、B-7 M1-M8 逐槽判定；禁区：b10 登记为「翻译层本体含旧协议字串、摘旧标记时须整译、待分发方定义处理口径」 |
| extend/dialog/parts/05c_prompt.js | 6 处（L39/205/210/262/269/276） | 方言提示词回执格式说明（L39 大模板）+ 回传结果组装（L210 payload = { tool, type: 'bridge-chat-res', nonce }）+ 截图精简回传标记 screenshotMark（L262/269/276） | 落点：提示词与回传组装；当前态：活链；活调用方：postCardResult 路径经 06_execute 调用；依赖：同上；禁区：b10 行「步骤 3」 |
| extend/dialog/parts/05f_parse.js | 3 处（L371/376/390） | msgSource 唯一入口：user 消息含 bridge-chat-res 判 'tool' 来源（L390），收敛「内容反推来源」的分散判定 | 落点：消息来源判定；当前态：活链；活调用方：消息树建节点；依赖：第 4 步；禁区：b10 行「步骤 3、摘除即断主链」 |
| extend/dialog/parts/00_data.js | 3 处（L71/73/174） | cardHasMessage 按 nonce 配对 external-call / bridge-chat-res 防镜像重复渲染（L73）+ 折叠状态（L174） | 落点：配对去重与折叠展示；当前态：活链；活调用方：buildTimeline；依赖：第 4 / 6 步键统一（c7 第 5 节）；禁区：nonce 配对构型保持 |
| extend/dialog/parts/06_execute.js | 1 处（L300） | 工具截图回传标记注释（screenshotMark 经 05c 产出）；postCardResult（L285-）为回传统一入口：AI 卡片结果回传网页、截图走图片+精简标记、文件走附件分支；指令回执走 /api/bridge/result 不进本函数（隔离铁律） | 落点：回传执行端；当前态：活链；活调用方：自动回传 / 复制结果跳倒计时两处共用；依赖：第 5 步（B-12 已闭合、executeCard 中段已委托 adapter.execute）；禁区：B-12 实装面零改写 |
| extend/dialog/parts/05g_cards.js | 3 处（L430/431/438） | 消息级质量回传：无卡片可搭时以 bridge-chat-res 格式入队（payload L436-443 含 nonce 与 msg_id） | 落点：质量告警回传；当前态：活链；活调用方：enqueueSend 统一队列；依赖：第 4 步；禁区：活链零改动 |
| extend/dialog/parts/05d_memory.js | 2 处（L52/70） | isRealUserMessage 排除工具结果回传：bridge-chat-res 虽 user 角色落地但非用户发言，不误触记忆窗口 | 落点：记忆窗口角色判定；当前态：活链；依赖：第 6 步键统一；禁区：b10 登记顺序表覆盖缺口（c7 五步表未单列行） |
| extend/dialog/parts/07_cards.js / 05_messages.js / 05i_files.js / 06c_file_attach.js / 08b_settings.js / extend/content/03_bridge.js | 各 1-2 处 | 渲染角色（07 L270/417 独立第三类）、code 块采集（05_messages L173）、文件回传标记采集（05i L30）、附件去重（06c L85）、统计口径（08b L197）、输入框标记防误判（03_bridge L375） | 均为消费面注释或判定，活链零改动 |

服务端侧（只读登记、不在本片面内实装）：flask_server/remote_bridge 2 文件（message_parse.py 3 处、channel/text.py 1 处）+ core/memory_distill.py（3 处）+ tools/file_image_impl.py（1 处）共 4 文件命中（另 flask_server/tests 2 个测试文件引用），属 B-7 / S3 第 9 步协议字段退役面，本片零触碰。

## 三、四处锚点逐行对拍

### 3.1 C-8 第二节第 6 步行（field_matrix.md 装配推演表）

| 对拍项 | C-8 标注 | 代码实况 | 结论 |
|---|---|---|---|
| 落点 | standard_chain_contract.js standardToolMessage；standard_chain_adapter.js reply | 两处均在码（L15 / reply 段），唯一定义 | 一致 |
| 状态 | 字段面一致；装配仍占位 | standardToolMessage 纯函数在码未装配；adapter.reply 声明态零下游 | 一致 |
| 依赖 B-7 | 否 | 本片不涉 B-7，登记不动 | 一致 |

### 3.2 C-15 第二节 | 6 | 行（余面判定表）

| 对拍项 | C-15 标注 | 代码实况 | 结论 |
|---|---|---|---|
| 字段面一致、装配仍占位 | 同 C-8 | 同上钉死 | 一致 |
| standardToolMessage 全仓 18 文件命中，多为夹具与契约文档 | 文面 18；c817dea 复测 19，未复现 | 开工 2fed217 复测 26；收口 b3c7d97 复测 27 | 计数漂移，差异登记 |
| 运行期回执仍走 05f_parse / 05c_prompt / 00_data / 06_execute 的 bridge-chat-res 旧链（全仓 30 文件命中） | 文面 30；c817dea 复测 41，未复现 | 四文件落点实测维持；开工 2fed217 复测 44 文件 118 行、收口 b3c7d97 复测 47 文件 126 行 | 落点一致；计数漂移，差异登记 |
| 旧回执活链多文件；adapter.reply 无运行期下游 | 同上 | extend 活链零 .reply( 调用、AIMirrorStandardChainAdapter.reply 唯一命中为 A-11 文档 | 一致 |
| 依赖：第 4 步建卡键落运行期；B-7 替换位 M1-M8 逐槽判定；c6 顺序表；前一单点（第 5 步） | — | 第 5 步已闭合（B-12 / a0cb2f0）仅作基线，判态以 19:45 为准 | 一致 |
| 禁区：同第 4 步；不新增运行期探测分支、不建切换开关 | — | 本片零代码改动，全部禁区遵守 | 一致 |

### 3.3 C-9 第一节 ### 4. reply(msg) 边界段 + C-14 第二节两行

- C-9 第一节第 4 段三行（缺键归一 / role 非 tool 强制归一 / 完整三键 content 不回显）与第二节 reply 状态行：A-11 已逐行钉死一致，本片复核维持（2.2 节），不重录矩阵。
- C-14 第二节 adapter 表 reply 行（by=KEY、role=tool、tool_call_id、status=STATUS）与 standardToolMessage 行（{role:tool,tool_call_id,content} 三键）：逐格与实仓一致（2.1 / 2.2 节实测）。
- G2 唯一键（tool_call.id 与 tool 消息三键、不含消息指纹）：standardToolMessage 实测恰三键无 msgId；execKeyFromToolCall 不含消息指纹（contract 注释与实现一致）。

### 3.4 b10 就绪度表逐行对拍

- S2 行「装配面九步第 5 步仍 declared-placeholder」为 34e6029 历史快照措辞；按 19:45 收紧口径：第 5 步 execute 单点已闭合（EXECUTE_STATUS = implemented-S2-step5）、整体未齐备 / 待对拍。登记差异不改写（A-12 同款口径）。
- S4 行三项硬前置未全满足维持：执行权未 100% 迁移（第 6 步回执链路本片实测仍全走旧链）、摘除任务书未下发、c6 九文件顺序表未执行。
- 逐文件行核对：00_data（L71/73/174）、05c（L39/205/210/262/269/276，b10 记 6 处 L205/210/262/269/276 等，计数与行号一致）、05f（L371/376/390）、05d（L52/70）、05g（L430/431/438）、translator（L90/161/166/177）——逐文件行号与 b10 快照一致（34e6029 后活链零改动互证）。

## 四、差异登记（供分发方复核，不代拍板）

1. **standardToolMessage 全仓计数漂移**：C-15 文面记 18 文件；本片在C-15 引用基线 c817dea 及相邻 rev 复测为 19 文件，未能复现文面数（或系 C-15 计数口径差异，文面未标口径）；开工基线 2fed217 复测 26 文件、收口基点 b3c7d97 复测 27 文件（本片交付后 +2：报告与夹具自身）。差量全部为后续只读交付报告 / 夹具与总线消息自身的引用与登记，非运行期装配变化——「纯函数在码、未装配」结论不变。
2. **bridge-chat-res 全仓计数漂移**：C-15 文面记 30 文件；本片在C-15 引用基线 c817dea 及相邻 rev 复测为 41 文件，未能复现文面数（或系 C-15 计数口径差异，文面未标口径）；开工 2fed217 复测 44 文件 118 行、收口 b3c7d97 复测 47 文件 126 行。差量含后续交付合入与 docs 追加；extend 活链 12 文件落点与 b10 快照逐行一致。
3. **b10 S2 行第 5 步状态措辞时点漂移**：b10 记「装配面九步第 5 步仍 declared-placeholder」（34e6029 快照措辞），实时 adapter L13 EXECUTE_STATUS = 'implemented-S2-step5'（B-12 已闭合第 5 步单点、19:45 收紧口径）。历史快照措辞，登记不改写、不翻 STATUS。
4. **任务书锚点指代漂移**：任务书写「C-9 第四节 reply 边界段」，实文 reply 边界段在 C-9 第一节 ### 4（第四节为 B-12 execute 只追加登记、不涉 reply，A-11 已钉）。本片按实文取证，不构成范围冲突。

## 五、结论

- **主结论零差异**：九步第 6 步回执链路「文档标注 vs 代码实况」逐行一致——standardToolMessage 三键纯函数在码未装配、adapter.reply 声明态零下游、运行期回执全量走 bridge-chat-res 旧链（13 个 extend 前端文件落点钉死），与 C-8 第 6 步行、C-15 | 6 | 行、C-9 第一节第 4 段、C-14 第二节两行、b10 就绪度表逐行对拍一致。
- 差异登记 4 项（2 项计数漂移、1 项 b10 S2 快照措辞、1 项任务书锚点指代），均为登记性、不阻断、不改判态。
- S1 不变；S2 第 5 步单点已闭合、整体未齐备 / 待对拍；S3 不变；S4 三项硬前置未全满足，阶段 3 不进入摘除步（19:45 判态锚不变）。
- 本片只读取证，不构成执行权迁移、不构成新前置；下一单点面（第 7 步去重已派 c、第 8 / 9 步未派）由分发方另行圈定。

## 六、边界与只追加记录

- 范围：只新增本报告、flask_server/tests/js/test_standard_chain_a13_step6_receipt.test.js 与 docs/work-ai-a.md 第五节只追加完成记录；零代码改动；新增被测 JS 源 0（夹具只读 require 已合入 adapter / contract / translator 三个 lib，均已在覆盖率报告内）。
- 不碰：活链九文件与 adapter / contract 本体（只读反查除外）、C-15 / C-16 / A-11 / B-13 / A-12 / b10 报告与夹具本体、card_sig 先例族、extend/dialog/AUDIT.md、docs/bus 他人消息、hooks / 90-70 阈值 / js_coverage_baseline.json。
- 不装配运行时 M、不注册钩子、不建切换开关、不新增运行期探测分支、不摘除任何旧标记、不翻任何 STATUS（含不扩用 EXECUTE_STATUS）、不执行 c6 九文件顺序表；docs 只追加（0 删除）。
- 夹具形态：零反斜杠零正则、按字符码 10 切行、普通 indexOf / split、只读 require node:* 与已合入 lib、无 fs 写 / shell / 网络；防重窗 require 序差异化按 A-10 口径开工即归零（与 a11 / a12 头部错序）。
- 验收实测：单文件 node --test 全绿（12 tests）、全量 js 门禁、全量 pytest（基线 1085）、quality / doc-sync / pre-commit 七道 / diff --check 以收口轮实跑为准；本机 node v24 覆盖率报告前缀差异打印不作达标依据，分发方环境直跑为准。
- 提交：基于收口时点 origin/main b3c7d97 新建提交、未 amend 已合入历史、一次提交收口、正常跑钩子不用 --no-verify；并行期间若 push 被并发拒绝先 fetch + ff-only 再重试自己的 send、勿 force-with-lease 回退已发总线消息；force-with-lease 仅更新本方 origin/work/ai-a；send report 回提交 hash 与实测数字，按 C-16 干净形态写 a -> dispatcher . report 且标题带 reply-to: dispatcher-20261116T202644-440f67。
