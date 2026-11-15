# C-13 B-8 × B-9 方案 A 纯函数层八槽交叉一致性总索引

> 性质：只读索引。逐槽固化 M1-M8 在两片纯函数层的归属、文件名、STATUS、
> 唯一键与 C-10 S 槽 / C-12 M 槽 / C-8 矩阵编号映射；只描述编号与落点形态，
> 不实装执行下游、不装配运行时 M、不建切换开关、不切活链、不新增运行期探测分支。
> 只读基准（均已合入 main）：
> - B-8 extend/lib/standard_slot_m345.js：M3 / M4 / M5
> - B-9 extend/lib/standard_chain_b9_slot_resolver.js：M1 / M2 / M6 / M7 / M8
> - C-8 standard_chain_field_matrix.md、C-9 standard_chain_boundary_contract.md
> - C-10 standard_chain_pending_criteria.md、C-11 standard_chain_crossref_index.md
> - C-12 standard_chain_replacement_map.md
> - 代码侧 standard_chain_adapter.js、standard_chain_contract.js
> 两片纯函数文件各自独立命名，槽位集合互不相交，无文件交集。
> 不预设 B-7 总结论、不预设旧标记摘除结论。

## 一、全局不变量

- G1 STATUS 恒 declared-placeholder：两片纯函数导出的 STATUS 与全部映射层文档一致。
- G2 唯一键恒标准 tool_call.id（call_<nonce>）与 tool 消息三键 role / tool_call_id / content，不含消息指纹。
- G3 两片纯函数层只做可实测的落点转换/拒绝，运行时装配状态保持声明态；活链文件零改动。
- G4 编号集合封闭：M1-M8 八槽、S1-S4 四槽、#4 / #7 / #13 / #14 四个矩阵编号，无悬空编号。

## 二、逐槽交叉索引（8 槽）

表头 M 槽列即 C-12 M 槽编号；S 槽列来自 C-10；矩阵编号列来自 C-8 与 C-11。

| M 槽 | 归属片 | 纯函数文件名 | STATUS | 唯一键 | C-10 S 槽 | C-8 矩阵编号 |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | B-9 | standard_chain_b9_slot_resolver.js | declared-placeholder | tool_call.id + 三键 | S3 | #13 |
| M2 | B-9 | standard_chain_b9_slot_resolver.js | declared-placeholder | tool_call.id + 三键 | S3 | #13 |
| M3 | B-8 | standard_slot_m345.js | declared-placeholder | tool_call.id + 三键 | S2 / S3 | #7 / #13 |
| M4 | B-8 | standard_slot_m345.js | declared-placeholder | tool_call.id + 三键 | S2 / S3 | #7 / #13 |
| M5 | B-8 | standard_slot_m345.js | declared-placeholder | tool_call.id + 三键 | S2 / S3 | #7 / #13 |
| M6 | B-9 | standard_chain_b9_slot_resolver.js | declared-placeholder | tool_call.id + 三键 | S3 | #13 |
| M7 | B-9 | standard_chain_b9_slot_resolver.js | declared-placeholder | tool_call.id + 三键 | S1 / S2 / S3 | #4 / #7 / #13 |
| M8 | B-9 | standard_chain_b9_slot_resolver.js | declared-placeholder | tool_call.id + 三键 | S4 | #14 |

「唯一键」列 tool_call.id + 三键 的含义见第一节 G2；八行均为同一组标准键。

## 三、逐槽旧位所在层与替换位落点类型（对齐 C-12 第二节）

- M1：前端消息信封与工具指令包装层；信封字段→标准 tool_calls 意图位。
- M2：前端回执信封与结果合并层；信封字段→tool 消息三键位。
- M3：命令执行桥接层；指令类型位→标准 tool_call.id 执行位。
- M4：外部调用包装层；包装字段→标准 tool_calls 意图位。
- M5：结果识别标记层；标记字段→tool 消息 role 位。
- M6：三网关信封包装层；包装层→标准信封字段位。
- M7：公共层解析与分发面；解析层→标准 tool_calls / tool 消息三键位。
- M8：刷新恢复与签名兼容层；兼容位→标准 call_<nonce> 优先键。

以上八条逐条与 C-12 第二节同名槽位的「旧位所在层」「替换位落点类型」一致，
本索引只读引用，不改写 C-12 正文。

## 四、两片归属与文件独立性

- B-8：extend/lib/standard_slot_m345.js，导出 m3 / m4 / m5 三组共 6 个转换函数；
  槽位集合 {M3, M4, M5}。
- B-9：extend/lib/standard_chain_b9_slot_resolver.js，导出 SLOTS / findSlot / resolveReplacement；
  槽位集合 {M1, M2, M6, M7, M8}。
- 两集合并集为 {M1..M8}、交集为空；两份源码文件名不同、互不 require、无文件交集。
- 两片均导出 STATUS = declared-placeholder、KEY = tool_call.id；B-9 另导出冻结的
  TOOL_MESSAGE_KEYS = role / tool_call_id / content。

## 五、编号封闭与 C-12 只读引用

- M1-M8 八槽在 C-12 第二节、本索引第二/三节、两片纯函数声明中三方齐全，无悬空编号。
- S1-S4 四槽在 C-10 四节标题、C-11 第一/四节、本索引第二节齐全。
- 矩阵 #4 / #7 / #13 / #14 在 C-8 14 条矩阵、C-11 第四节、C-12 第三节、
  本索引第二节齐全。
- C-12 standard_chain_replacement_map.md 为只读映射底稿；本索引只引用其槽位编号与落点类型，
  不改写正文、不预设 B-7 结论。旧标记摘除对应 S4 / #14 / M8，仍以后续逐项对拍为准。

## 六、边界与只追加记录

- 范围：只新增本索引（extend/lib/ 下 .md）与 flask_server/tests/js/ 下 1 份反查夹具；
  两片纯函数源码、C-8 / C-9 / C-10 / C-11 / C-12 五份 .md、两个已合入 lib 均只读引用、零改动。
- 不碰活链、不装配运行时 M、不建切换开关、不新增运行期探测分支、
  不碰 b 收口片与 docs/bus 他人消息。
- 夹具全文规避反斜杠与正则，按字符码 10 切行、普通 indexOf / split 反查。
- 新增被测 JS 源文件数为 0：本笔不新增 lib 纯函数源码，夹具只读 require 已合入的两片纯函数，
  它们由各自 B-8 / B-9 夹具加载、已在覆盖率报告内，不引入新的覆盖率分母。
- 本机 node v24 报告前缀差异导致的打印不作达标依据，
  不改钩子脚本 / 90-70 阈值 / js_coverage_baseline.json、不用 --update-baseline。
- docs 只追加：交付回执由 send report 追加到 docs/bus/c.md。
- 提交：基于实时 origin/main 新建提交、勿 amend 已合入历史、勿 force-with-lease 回退已发消息；
  一次提交收口，更新 origin/work/ai-c，send report 回 hash 与实测。
