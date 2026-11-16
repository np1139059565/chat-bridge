# B-14 dedupe 单点边界反查与 C-9 / C-14 / C-15 / b10 状态标注对拍（只读取证）

> 性质：只读边界反查取证片，零代码改动、新增被测 JS 源 0。
> 任务书：dispatcher-20261116T190823-edaafe（阶段 3 续派·dedupe 单段边界反查，指派 b）。
> 证据基线：origin/main 0ad583a（提交基线；取证实测笔 55d94d0，区间 55d94d0..0ad583a 仅总线消息笔、被取证对象零变化，合并后夹具重跑 12/12 复核；A-12 已于 a4d9f2d 合入）；行号为本轮实仓实测。
> 判态锚：以 19:45 dispatcher-20261115T194511-c92792 为准，不改写——S1 不变；S2 第 5 步 execute 单点已闭合、
> 整体未齐备 / 待对拍；S3 不变；S4 三项硬前置仍未全满足，阶段 3 不进入摘除步。
> 本片仅声明态边界反查，不构成执行权迁移、不构成新前置、不触发摘除或实装动作。

## 一、取证对象与锚点

- 对象：extend/lib/standard_chain_adapter.js 内 adapter.dedupe 纯声明函数（定义 L60、导出 L73，全仓唯一定义）。
- 锚点四件：C-9 第五节 ### 5. dedupe(a, b)（L65-L73，四行边界表与说明行 L73）；C-9 第二节 dedupe 状态行（L95）
  与全局不变量 G1-G4（L11-L18）；C-14 第二节 dedupe 签名行（L35）、六段接口名行（L30）、C-9 六段边界行（L84）、
  第六节（L112 起）零 dedupe；C-15 第二节第 7 行（L34，按任务书同面判性段仅取「前端 dedupe 仍声明态」标注，
  不当本片取证范围）与 b10 就绪度表（全文零 dedupe 字样）。

## 二、边界段原文与实源逐行对拍

| 项 | C-9 契约（第五节） | 实源 adapter.js L60 | 一致性 |
| --- | --- | --- | --- |
| 返回形状 | by=KEY、a、b、status=STATUS | function dedupe(a, b) { return { by: KEY, a: a 或 null, b: b 或 null, status: STATUS }; } | 一致 |
| 同 call_nonce id | a / b 原样回显；占位期不做判重决策、不吞并 | 双键独立保留同值，无吞并分支 | 一致 |
| 不同 id | a / b 原样回显；不比较、不排序、不去重 | 纯回显，无比较逻辑 | 一致 |
| null 入参 | 缺失侧回落 null；不抛错（G3） | 任一侧缺失各自归一 null，零抛错路径 | 一致 |
| 说明行（L73） | 同 id 判定留给后续实装，本期只保证形状稳定 | 实源无任何判重决策代码 | 一致 |

补充实证（实源语义超集，登记非漂移）：归一语义为任一侧 falsy（undefined / 空串 / 0 / false）均归一 null；
一切真值（含空对象）按原引用直通，不复制不深比较。C-9 表仅列 null 侧，实源行为覆盖且不冲突。

## 三、当前态与活调用方

- 常量：STATUS 恒 declared-placeholder（L12）、KEY 恒 tool_call.id（L14）、EXECUTE_STATUS 独立导出
  implemented-S2-step5（L13）作用域不变；dedupe 返回 status 取 STATUS、不触碰 EXECUTE_STATUS。
- 唯一定义与导出：function dedupe( 全仓恰 1 处（adapter L60）；导出面 dedupe 属性恰 1 行（L73）；
  adapter 全文件 dedupe 字样恰 3 次（定义 1 + 导出行 2）。
- 运行期零调用方：精确串 AIMirrorStandardChainAdapter.dedupe / adapter.dedupe( / AD.dedupe( / Adapter.dedupe(
  在 extend/dialog/parts/ 全部 56 份 .js、adapter.js、contract.js、dialog.html 全零命中。
- 活链依赖：无。C-15 第 7 行载明前端去重现由 00_data.js（nonce 配对 external-call / bridge-chat-res、
  buildTimeline 折叠）与 05j_card_sig.js（标准 call_nonce + 旧 msgId 双查）承担，adapter.dedupe 未参与
  任何运行期链路；活链旧标记全保留。

## 四、四处标注对拍结论

| 锚点 | 行号 | 关键串 | 命中 | 结论 |
| --- | --- | --- | --- | --- |
| C-9 第五节标题 | L65 | ### 5. dedupe(a, b) | 1 | 逐字在文 |
| C-9 第五节边界表 | L67-L72 | 三行输入边界与不变量 | 1/1/1 | 逐串在文 |
| C-9 第五节说明行 | L73 | 本期只保证形状稳定 | 1 | 逐字在文 |
| C-9 第二节状态行 | L95 | dedupe 五格（declared-placeholder、tool 三键、n/a、否） | 1 | 逐格在文 |
| C-9 G1-G4 | L11-L18 | G1 / G2 / G3 / G4 | 4 | 逐条在文 |
| C-14 签名行 | L35 | dedupe(a,b)、返回 by=KEY、a、b、status=STATUS、一致 | 1 | 逐格在文 |
| C-14 六段接口名 / C-9 六段边界 | L30 / L84 | parse / buildCard / execute / reply / dedupe / restore | 2 | 各恰 1 |
| C-14 第六节 | L112 起 | dedupe 字样 | 0 | 无追加节，与 B-12 节不含 restore 同型 |
| C-15 第 7 行 | L34 | adapter.dedupe、前端 dedupe 仍声明态、00_data.js、05j_card_sig.js、pending_tool_calls | 1 | 逐串在文（仅标注对拍） |
| b10 就绪度表 | 全文 | dedupe 字样 | 0 | 无单列槽（见差异 2） |

## 五、差异登记（仅供分发方复核，不代拍板、不改判态）

1. C-9 表仅列 null 侧 vs 实源一切 falsy 均归一 null：一致超集（第二节补充实证），非漂移。
2. b10 零 dedupe 字样：就绪度表以 S1-S4 汇总口径承载，dedupe 归 S2 行六段声明态集合，无独立槽位——口径差异非缺失。
3. C-14 签名行 dedupe(a,b)（无空格）vs C-9 标题 dedupe(a, b)（有空格）：两文档既有形态差异，非本笔新增。
4. C-15 第 7 行把九步第 7 步（服务端 pending_tool_calls 已实交付）与前端 dedupe 声明态并列一行：本片按任务书
   同面判性段只取六段 dedupe 声明态，不取该行第 7 步装配面内容。

## 六、结论

dedupe 段零差异：STATUS 恒 declared-placeholder、KEY 恒 tool_call.id、返回形状恰四键、同 / 异 id 均原样回显
不吞并、null 侧归一不抛错、运行期零调用方、唯一定义恰 1、导出面恰 1、活链旧标记全保留。本片零代码改动、
零实装、零摘除、不翻 STATUS、不建切换开关、不切活链；不构成执行权迁移、不构成新前置、不改 S1-S4 判态、
不自行圈定下一实装面、不预设下发时点。

## 七、复核输入边界

本报告与配套夹具 flask_server/tests/js/test_standard_chain_b14_dedupe_boundary.test.js 为只读取证产物
（夹具 12 条：形状恰四键 / 同 id 不吞并 / 异 id 不排序 / null 归一 / falsy 与 truthy / 幂等 / C-9 / C-14 /
C-15 / b10 对拍 / 运行期零调用方 / 常量作用域）。差异登记仅为分发方复核输入，不代拍板。
