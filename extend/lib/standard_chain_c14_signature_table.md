# C-14 已合入契约面字段签名总表（阶段 3 后续裁定唯一核对基线）

> 性质：只读签名总表。逐文件列导出常量、字段签名、槽位集合、编号体系与实际值，
> 只描述已合入 main 的代码与文档实况，不实装执行下游、不装配运行时 M、
> 不建切换开关、不切活链、不新增运行期探测分支、不摘除任何旧标记、
> 不把 declared-placeholder 翻成已装配、不预设 B-7 总结论与旧标记摘除下发时点。
> 只读基准：A-7 model_reply_hook、C-7 两个 lib、C-8 矩阵、C-9 边界契约、
> C-10 S1-S4、C-11 索引、C-12 M1-M8、B-8 三槽纯函数、B-9 五槽纯函数、C-13 八槽索引。
> 清单/映射层声明态不因纯函数层可实测而翻转：纯函数层只回显 declared-placeholder。

## 一、全局不变量（每条签名均须成立）

- G1 STATUS 恒 declared-placeholder：四个已合入 lib、钩子声明面、协议退役面、
  C-10 四槽判据生效期、C-12 八槽映射、C-13 八槽索引均为声明态。
- G2 唯一键恒标准 tool_call.id（call_<nonce>）与 tool 消息三键
  role / tool_call_id / content，不含消息指纹。
- G3 八槽集合恰为 M1-M8：B-8 三槽 {M3,M4,M5} 与 B-9 五槽 {M1,M2,M6,M7,M8}
  互斥且并集为八槽，两片纯函数文件独立命名、无文件交集。
- G4 编号体系封闭：S1-S4 四槽、矩阵 #4 / #7 / #13 / #14，无悬空编号。
- G5 本总表只读引用，不 import 任何未合入模块，不改写既有源码与 .md。

## 二、逐文件导出常量与字段签名

### standard_chain_adapter.js（C-7）

| 签名项 | 所在文件 | 实际值 | 是否一致 | STATUS |
| --- | --- | --- | --- | --- |
| STATUS | standard_chain_adapter.js | declared-placeholder | 一致 | declared-placeholder |
| KEY | standard_chain_adapter.js | tool_call.id | 一致 | declared-placeholder |
| 六段接口名 | standard_chain_adapter.js | parse / buildCard / execute / reply / dedupe / restore | 一致 | declared-placeholder |
| parse(block) | standard_chain_adapter.js | 返回 by=KEY、block、status=STATUS | 一致 | declared-placeholder |
| buildCard(call) | standard_chain_adapter.js | 返回 by=KEY、id、status=STATUS | 一致 | declared-placeholder |
| execute(card) | standard_chain_adapter.js | 返回 by=KEY、card、status=STATUS | 一致 | declared-placeholder |
| reply(msg) | standard_chain_adapter.js | 返回 by=KEY、role=tool、tool_call_id、status=STATUS | 一致 | declared-placeholder |
| dedupe(a,b) | standard_chain_adapter.js | 返回 by=KEY、a、b、status=STATUS | 一致 | declared-placeholder |
| restore(sessionId,call) | standard_chain_adapter.js | 返回 by=KEY、sessionId、id、noMessageFingerprint=true、status=STATUS | 一致 | declared-placeholder |

### standard_chain_contract.js（C-7）

| 签名项 | 所在文件 | 实际值 | 是否一致 | STATUS |
| --- | --- | --- | --- | --- |
| PREFIX | standard_chain_contract.js | call_ | 一致 | declared-placeholder |
| makeToolCallId(nonce) | standard_chain_contract.js | call_<nonce> | 一致 | declared-placeholder |
| nonceFromToolCallId(id) | standard_chain_contract.js | 去 call_ 前缀还原 nonce | 一致 | declared-placeholder |
| standardToolMessage(callId,content) | standard_chain_contract.js | {role:tool,tool_call_id,content} 三键 | 一致 | declared-placeholder |
| execKeyFromToolCall(call,sessionId) | standard_chain_contract.js | 会话 id + call_<nonce> 反解 nonce + 工具名 + 参数摘要，noMessageFingerprint | 一致 | declared-placeholder |
| assertStandardToolCall(item) | standard_chain_contract.js | 校验 id 与 function.name | 一致 | declared-placeholder |
| PRE_DISPATCH_HOOK_CONTRACT.status | standard_chain_contract.js | declared-placeholder | 一致 | declared-placeholder |
| PRE_DISPATCH_HOOK_CONTRACT.signature | standard_chain_contract.js | fn(history) -> None 或 list | 一致 | declared-placeholder |
| PROTOCOL_RETIREMENT_CONTRACT.status | standard_chain_contract.js | declared-placeholder | 一致 | declared-placeholder |
| PROTOCOL_RETIREMENT_CONTRACT.direction | standard_chain_contract.js | standard tool_calls / tool message as the only key | 一致 | declared-placeholder |

### standard_slot_m345.js（B-8，M3/M4/M5 三槽）

| 签名项 | 所在文件 | 实际值 | 是否一致 | STATUS |
| --- | --- | --- | --- | --- |
| STATUS | standard_slot_m345.js | declared-placeholder | 一致 | declared-placeholder |
| KEY | standard_slot_m345.js | tool_call.id | 一致 | declared-placeholder |
| M3 导出函数 | standard_slot_m345.js | m3CommandToToolCall / m3ToolCallToCommand | 一致 | declared-placeholder |
| M4 导出函数 | standard_slot_m345.js | m4EnvelopeToToolCall / m4ToolCallToEnvelope | 一致 | declared-placeholder |
| M5 导出函数 | standard_slot_m345.js | m5FlagToToolMessage / m5ToolMessageToFlag | 一致 | declared-placeholder |
| 槽位集合 | standard_slot_m345.js | M3 / M4 / M5 | 一致 | declared-placeholder |
| 接受形态 | standard_slot_m345.js | {slot,ok:true,status,value} | 一致 | declared-placeholder |
| 拒绝形态 | standard_slot_m345.js | {slot,ok:false,status,reason}，不落盘无副作用 | 一致 | declared-placeholder |

### standard_chain_b9_slot_resolver.js（B-9，M1/M2/M6/M7/M8 五槽）

| 签名项 | 所在文件 | 实际值 | 是否一致 | STATUS |
| --- | --- | --- | --- | --- |
| STATUS | standard_chain_b9_slot_resolver.js | declared-placeholder | 一致 | declared-placeholder |
| KEY | standard_chain_b9_slot_resolver.js | tool_call.id | 一致 | declared-placeholder |
| TOOL_MESSAGE_KEYS | standard_chain_b9_slot_resolver.js | role / tool_call_id / content（冻结） | 一致 | declared-placeholder |
| SLOTS id 集合 | standard_chain_b9_slot_resolver.js | M1 / M2 / M6 / M7 / M8 | 一致 | declared-placeholder |
| findSlot(id) | standard_chain_b9_slot_resolver.js | 按 id 查声明，未命中返回 null | 一致 | declared-placeholder |
| resolveReplacement(request) | standard_chain_b9_slot_resolver.js | 旧位拒绝附转换建议 / 新位规范化 / 异常不落盘拒绝 | 一致 | declared-placeholder |
| 接受形态 | standard_chain_b9_slot_resolver.js | {accepted:true,status,by,keys,slot,oldLayer,target,marker,persisted:false} | 一致 | declared-placeholder |
| 拒绝形态 | standard_chain_b9_slot_resolver.js | {accepted:false,status,by,keys,slot,reason,convertedTo,persisted:false} | 一致 | declared-placeholder |

## 三、文档层签名与编号体系

| 签名项 | 所在文件 | 实际值 | 是否一致 | STATUS |
| --- | --- | --- | --- | --- |
| C-8 矩阵 | standard_chain_field_matrix.md | 14 条，一致 10 / 待对拍 4 / 不一致 0 | 一致 | declared-placeholder |
| C-9 六段边界 | standard_chain_boundary_contract.md | parse / buildCard / execute / reply / dedupe / restore | 一致 | declared-placeholder |
| C-10 四槽 | standard_chain_pending_criteria.md | S1 / S2 / S3 / S4 | 一致 | declared-placeholder |
| C-11 交叉索引 | standard_chain_crossref_index.md | 14 / 6 / 4 条目集合与 STATUS 集合 | 一致 | declared-placeholder |
| C-12 八槽映射 | standard_chain_replacement_map.md | M1-M8 八槽，每槽旧位层 / 落点类型 / 是否仍占位 | 一致 | declared-placeholder |
| C-13 八槽索引 | standard_chain_c13_crossref_index.md | 八槽归属片 / 文件名 / STATUS / 唯一键 / S 槽 / 矩阵编号 | 一致 | declared-placeholder |
| 矩阵编号 | C-8 / C-11 / C-12 / C-13 | #4 / #7 / #13 / #14 | 一致 | declared-placeholder |
| call_<nonce> 唯一键 | 四个 lib 与 C-12 / C-13 | 标准 tool_call.id，不含消息指纹 | 一致 | declared-placeholder |
| declaration 语义 | 本总表 | 清单/映射层声明态不因纯函数层可实测而翻转 | 一致 | declared-placeholder |

## 四、两片互斥与编号封闭

- B-8 槽位集合 {M3,M4,M5} 与 B-9 槽位集合 {M1,M2,M6,M7,M8} 交集为空，
  并集恰为 {M1..M8}；两片源码互不 require、文件名不同、无文件交集。
- S1-S4 与 #4 / #7 / #13 / #14 在 C-10 / C-11 / C-12 / C-13 四处齐全，无悬空值。
- 四个 lib 的 STATUS 全部相等、KEY 全部相等，三键在 B-9 导出与 C-7 标准消息中一致。

## 五、覆盖率形态与边界

- 本笔只新增 1 份 .md 签名总表与 1 份反查夹具，不新增 lib 源码，新增被测 JS 源 0；
  夹具只读 require 四个已合入 lib，它们由各自夹具加载、已在覆盖率报告内，不引入新分母。
- 夹具不 import 任何未合入模块；不改 hooks / 90-70 阈值 / js_coverage_baseline.json、
  不用 --update-baseline；本机 node v24 报告前缀差异打印不作达标依据。
- 不改既有源码与 .md 内容，docs 只追加（交付回执由 send report 追加到 docs/bus/c.md），
  不动 docs/bus 他人消息，不碰 b 收口片与活链文件。
- 夹具全文规避反斜杠与正则，按字符码 10 切行、普通 indexOf / split 反查。
- 提交：基于实时 origin/main 新建提交，勿 amend 已合入历史、勿 force-with-lease 回退已发消息；
  一次提交收口，更新 origin/work/ai-c，send report 回 hash 与实测。


## 六、execute 段实装登记（B-12，2026-11-15 追加）

> 只追加登记，不改上方历史表格；模块 STATUS 恒 declared-placeholder，
> 实装态由 adapter 独立导出 EXECUTE_STATUS 表达，declaration 语义不变。

| 签名项 | 所在文件 | 实际值 | 是否一致 | STATUS |
| --- | --- | --- | --- | --- |
| execute 段实装 | standard_chain_adapter.js | execute(card, deps) 双参持执行编排骨架，06_execute 注入 _callTool；单参回显不变 | 一致 | declared-placeholder |
| EXECUTE_STATUS 导出 | standard_chain_adapter.js | implemented-S2-step5，独立于 STATUS，不进 C-14 六段断言面 | 一致 | declared-placeholder |
| 执行权迁移落点 | 06_execute.js / dialog.html | executeCard 中段委托 adapter.execute，_resetCardDiagnostics 并入骨架；lib 区末尾追加装载行 | 一致 | declared-placeholder |

- 新增夹具：test_standard_chain_adapter_execute.test.js 七断言（单参回显 / 双参
  成功 / 失败 / 异常 / 诊断复位 / deps 边界 / 导出面），只读 require adapter；
- 53 份 JS 夹具全跑 rc=0 零破坏；新夹具不引入新分母（adapter 已在库、
  不在 js_coverage_baseline.json 欠账清单）；
- 详细登记见 standard_chain_boundary_contract.md 第四节。
