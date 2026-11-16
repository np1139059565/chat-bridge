# A-14 六段声明函数边界反查·reply 单段逐行取证报告

> 性质：只读取证报告（零代码改动）。对 extend/lib/standard_chain_adapter.js 内
> reply 纯声明函数做单段边界反查与四锚逐行对拍；差异登记供分发方复核输入，
> 不代拍板、不改 S1-S4 判态、不自行圈定下一实装面、不预设下发时点。
> 任务书：dispatcher-20261116T232427-ee3d1f（并行续派·六段声明函数边界反查·reply 单段）。
> 基点：实时 origin/main c163e0a（开工前 fetch --prune + merge --ff-only 同步、
> 工作区 clean；C-17 合入 a25fc98、B-14 合入 4ce0fd1、A-13 合入 425cf80 与
> 本任务书登记均已在链）。
> 判态锚：19:45 dispatcher-20261115T194511-c92792 口径不变——S2 第 5 步 execute
> 单点已闭合、整体未齐备 / 待对拍；S4 三项硬前置仍未全满足，阶段 3 不进入摘除步。

## 一、取证范围与方法

- 代码对象：extend/lib/standard_chain_adapter.js 的 reply 段——L59 唯一定义
  （function reply( 全 extend/ .js 恰 1 次）、L72 六段导出面成员。模块级常量
  STATUS = 'declared-placeholder'、KEY = 'tool_call.id'、EXECUTE_STATUS =
  'implemented-S2-step5' 独立导出，作用域限 execute 段。
- 文档对象（四锚）：C-9 extend/lib/standard_chain_boundary_contract.md
  （第一节 ### 4 reply(msg) 边界表三行 + G1 / G3 全局不变量 + 第二节状态行）、
  C-14 extend/lib/standard_chain_c14_signature_table.md（第二节 reply(msg) 行
  与六段总表行）、C-15 docs/c15-s2-remaining-surface-inventory.md
  （第一节 reply 行与第二节第 6 步行）、b10 docs/b10-removal-readiness-report.md
  （S4 #14 槽「摘除任务书未下发」断语）。
- 方法：夹具只读 require 已合入 adapter 一个 lib（UMD node 分支）；四锚 .md 与
  活链文件按字符码 10 切行、普通 indexOf / split 反查（零反斜杠零正则）；
  无 fs 写 / shell / 网络；新增被测 JS 源 0。
- 运行期取证：活链九文件（06_execute.js / 05f_parse.js / 00_data.js / 05g_cards.js /
  05j_card_sig.js / 05c_prompt.js / 01b_bridge.js / translator.js / dialog.html）
  四精确串 .reply( / adapter.reply / AIMirrorStandardChainAdapter.reply /
  function reply( 逐文件计数；git grep 佐证 standardToolMessage 与
  bridge-chat-res 全仓分布。

## 二、代码实况：adapter.reply 逐项钉死

源码定义（standard_chain_adapter.js L59，全仓唯一，逐字引用）：

    function reply(msg) { return { by: KEY, role: 'tool', tool_call_id: (msg && msg.tool_call_id) || null, status: STATUS }; }

十二项语义实测（test_standard_chain_a14_reply_segment.test.js A14-01 至 A14-12
逐条断言；另 A14-13 四锚对拍、A14-14 报告自反，共 14 用例）：

1. **唯一定义与导出**：function reply( 全 extend/ .js 恰 1 次（adapter L59）、
   L72 六段导出面成员；EXECUTE_STATUS 在 adapter 源内 6 处（定义、头注释推演行、
   导出行键值两处、execute 骨架两态）。
2. **返回形状恰四键**：by / role / tool_call_id / status；by 恒 'tool_call.id'、
   status 恒 'declared-placeholder'，无第五键。
3. **role 硬编码常量**：入参 role 取 assistant / user / function / 空串 / 42 / null，
   输出 role 恒 'tool'，不回显入参 role。
4. **content 不回显**：完整三键入参，返回对象无 content 键。
5. **tool_call_id 原样回显不吞**：truthy id 原样保留（含长串）。
6. **缺键归一 null**：null / undefined / {} / { role: 'tool' } 四类残缺入参，
   tool_call_id 一律 null，返回深等于 { by: 'tool_call.id', role: 'tool',
   tool_call_id: null, status: 'declared-placeholder' }。
7. **不抛错**：非对象入参（字符串 / 42 / true / 数组）doesNotThrow，归一同上。
8. **truthy 不比较不排序**：'call_b' / 'call_a' 各自回显，无比较、无排序、
   无判重决策（占位期留给后续实装）。
9. **幂等且每次新对象**：同参两次调用深相等、不共享引用。
10. **falsy 归一与 truthy 直通**：空串 / 0 / false 归一 null；'call_n1' 直通。
11. **常量作用域**：STATUS / KEY / EXECUTE_STATUS 三常量导出面同值实测；
    reply 返回 status 为 STATUS、不扩用 EXECUTE_STATUS（限 execute 段）。
12. **运行期四精确串零调用方**：活链九文件 .reply( / adapter.reply /
    AIMirrorStandardChainAdapter.reply / function reply( 四串逐文件 0 命中；
    function reply( 全 extend/ .js 仅 adapter 1 处。

## 三、四锚逐行对拍

| 锚 | 标注 | 代码实况 | 结论 |
| --- | --- | --- | --- |
| C-9 第一节 ### 4 三行 | 缺键归一 null、role 强制归一 'tool' 不回显不抛错、完整三键不回显 content | 实测一致（第 2-7 项） | 一致 |
| C-9 G1 / G3 | STATUS 恒 declared-placeholder、异常输入不抛错 | 实测一致（第 2 / 7 / 11 项） | 一致 |
| C-9 第二节状态行 | reply 行 declared-placeholder、tool_call.id + tool 三键、实装下游否 | 实测一致（第 2 / 11 / 12 项） | 一致 |
| C-14 六段总表行 + reply(msg) 行 | 返回 by=KEY、role=tool、tool_call_id、status=STATUS；declared-placeholder | 实测一致（第 2 / 5 / 6 项） | 一致 |
| C-15 第一节 reply 行与第二节第 6 步行 | role 硬编码常量、content 不回显；adapter.reply 装配仍占位、无运行期下游 | 实测一致（第 3 / 4 / 12 项） | 一致 |
| b10 S4 #14 槽 | 摘除任务书未下发、三项缺一不可、阶段 3 不进入摘除步 | 实况一致：本片零摘除、STATUS 不翻、执行权迁移硬前置未全满足 | 一致 |

## 四、差异登记（供分发方复核，不代拍板）

1. **a11 与本片同面复核关系**：A-11（dispatcher-20261115T203520-749f39，基线
   e87642d）已做 reply 单段两锚（C-9 / C-14）反查并合入。本片任务书明示沿用
   「同一词、不同面、先后各自验收通过」先例，按 B-14 四锚口径（增 C-15
   reply 行与第 6 步行、b10 S4 断语、truthy 不比较不排序、falsy 归一与
   truthy 直通、四精确串零调用方）在实时基线 c163e0a 复核。两片结论一致
   （零差异）；差异面在锚点覆盖、falsy / truthy 边界、truthy 不比较语义、
   运行期取证口径（a11 扫 extend/ 全目录两串，本片钉活链九文件四精确串）。
   不动 a11 本体、不重做 a11 已消费面。

2. **b10 报告无 adapter.reply 字样**：b10 以「S1-S4 槽位 + c6 九文件表」组织，
   无 reply 独立行（adapter.reply 计数 0 实测）；本片以 S4 #14 槽「摘除任务书
   未下发」（2 处）、「三项缺一不可」（1 处）断语对拍 S4 前置未变，且全仓
   bridge-chat-res 旧链仍在活链。此为对拍方法差异、非语义冲突，登记不改写。

3. **计数漂移登记（基线间）**：本片基线 c163e0a 实测 git grep -c：
   standardToolMessage 31 文件 / 70 命中、bridge-chat-res 51 文件 / 152 命中
   （A-13 在 b3c7d97 登记 bridge-chat-res 47 文件 / 126 命中）；差量为 B-14 /
   C-17 / A-13 各片报告与总线消息的登记增长，非运行期装配变化（运行期回执
   仍全量走旧链，见第二节第 12 项）。

4. **06_picker.js const reply 局部函数**：06_picker.js L333 起
   const reply = function (ok, text) 为选择器测试工具的局部回调（8 处
   reply( 调用），非 adapter.reply 调用方；function reply( 精确串在该文件
   零命中。05g_cards.js 的 no_reply 参数（1 处）、05e_quality.js 的
   code_only_reply 串（1 处）同属非调用方命中，逐文件登记，不改写。

## 五、结论

adapter.reply 为全仓唯一纯声明函数（L59 定义 / L72 导出），返回形状恰四键
（by / role / tool_call_id / status），STATUS 恒 declared-placeholder、KEY 恒
tool_call.id，role 硬编码 'tool' 不回显入参、content 不回显、tool_call_id
truthy 原样回显不吞、falsy 归一 null、不抛错、不比较不排序、幂等新对象；
C-9 / C-14 / C-15 / b10 四锚逐行对拍一致；活链九文件四精确串零命中，运行期
零调用方，运行期回执仍全量走 bridge-chat-res 旧链（extend 前端 13 文件落点，
A-13 已钉）；S4 三项硬前置未全满足，阶段 3 不进入摘除步，本片
不构成执行权迁移、不构成新前置、不构成实装授权。19:45 判态锚不变。

## 六、边界与只追加记录

- 范围：只新增本报告、flask_server/tests/js/test_standard_chain_a14_reply_segment.test.js
  与 docs/work-ai-a.md 第五节只追加完成记录；零代码改动。
- 活链九文件零改动；旧标记全部保留；STATUS 保持 declared-placeholder；
  EXECUTE_STATUS 保持独立导出、作用域不变；c6 九文件顺序表保持未执行状态。
- 运行时 M 保持未装配；钩子注册数量为零；切换开关数量为零；运行期探测分支
  数量为零；docs/bus 他人消息零触碰；docs 只追加（0 删除）；hooks / 90-70
  阈值 / js_coverage_baseline.json 零改动，--update-baseline 未使用。
- 判态：S2 第 5 步单点已闭合、整体未齐备 / 待对拍；S4 三项硬前置未全满足。
- 本报告所有结论仅为分发方复核输入：不代拍板、不改 S1-S4 判态、不预设下发时点。

## 七、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| 反查夹具 | node --test flask_server/tests/js/test_standard_chain_a14_reply_segment.test.js | rc=0，14 tests / 14 pass / 0 fail（以收口轮实跑为准） |
| 前端全量 | python scripts/hooks/check_js_tests.py | rc=0（基线 645 + 本片 14；覆盖率门禁本机 node v24 前缀差异打印「跳过覆盖率门禁」、不作达标依据，分发方环境复验；分母以届时实时 main 实测为准） |
| 结构质量 | python scripts/quality_rules.py | rc=0，零 [新增]（收口轮实测） |
| 文档同步 | python scripts/check_doc_sync.py | rc=0（提交轮实测） |
| 全量 pytest | python -m pytest tests -q -p no:cacheprovider（flask_server 下串行单进程） | rc=0，1085 passed（基线不变，本片无 py 用例） |
| 七道钩子 | pre-commit run --all-files | 七道逐个 Passed（提交轮实测） |
| 差异检查 | git diff --check / git diff --cached --check | rc=0（提交轮实测） |

> 实测结果以收口轮实跑为准；覆盖率门禁本机跳过口径与 A-12 / A-13 同。
