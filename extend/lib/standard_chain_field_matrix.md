# C-8 A-7 × C-7 契约面对拍矩阵与端到端装配面只读推演

> 性质：只读对拍底稿。不装配运行时、不注册钩子、不新建切换开关、
> 不新增探测他笔是否存在的运行期分支、不改他笔文件、不切活链、不改阈值与基线。
> 基准：A-7 已合入 main（6b2be25 / 合并 2aaae54）；C-7 已合入 main（20ccf641 / 合并 0897e0a）。
> B-7 未交付（origin/work/ai-b 仍为 B-6 取证 6daba13），协议字段退役方向仍为声明占位。
> 口径依据：分发方 00:43 广播「C-7 占位声明与 A-7 实交付一致、无需改」；
> 分发方 01:17 裁定更正撤回「接线占位与旧标记摘除一并进同一次提交」；
> 分发方 10:24 广播「小片化、主动续派、C-8 不依赖 B-7、不装配运行时」。

## 一、逐项对拍矩阵（A-7 实交付签名 × C-7 占位声明）

状态标签：一致 / 待对拍 / 不一致。
「一致」指字段面或方向一致、无冲突；「待对拍」指跨侧、未装配或依赖 B-7 交付后统一对拍；
「不一致」指字段冲突、需分发方定向裁定补正。

| # | 对拍面 | A-7 实交付 | C-7 占位 / 实交付 | 状态 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 1 | 钩子签名 | register_pre_dispatch_hook(fn) 与 _run_pre_dispatch_hooks(history)，fn(history) 返回 None 或 list | PRE_DISPATCH_HOOK_CONTRACT.signature = fn(history) -> None / list | 一致 | 名称与形状同一面，零调整 |
| 2 | 钩子名字面 | register / clear / _run 三个名字 A-5 原样保留 | PRE_DISPATCH_HOOK_CONTRACT.names 列同一组名字 | 一致 | A-7 补充回执已登记 |
| 3 | 钩子唯一点位 | 历史合并后、_execute_pending 前（chat_api.py L213 调用、L214 执行） | 占位声明不含运行期点位，未装配 | 一致 | C-7 不触碰该点位 |
| 4 | fetcher 契约 | model_reply_hook(fetch_model_reply)：返回 None / str / dict，违约 TypeError，异常上抛无副作用 | 六段占位不含模型回复入口 | 待对拍 | 跨侧；L10 接真实模型需外部服务与凭证，B-7 到达后统一对拍 |
| 5 | tool_calls 标准字段 | _sanitize_tool_calls 只保留 id / type / function（name + arguments） | assertStandardToolCall 校验 id 与 function.name | 一致 | 标准字段面同向 |
| 6 | tool 消息三键 | role / tool_call_id / content 原样保留 | standardToolMessage(callId, content) 产出同三键 | 一致 | 三键字段名未变 |
| 7 | tool_calls 意图执行 | pending_tool_calls 按 tool_call_id 配对防重放，_execute_pending 交服务端标准管线 | adapter.execute 为 declared-placeholder | 待对拍 | 运行时执行权仍在旧建卡直调路径，依赖 B-7 与旧标记摘除 |
| 8 | 规范化追加 | _normalize_item，分发 / 落盘 / 响应 messages 三步一致 | C-7 范围不含服务端 | 一致 | 零交叉、无冲突 |
| 9 | parse 段 | 请求侧 assistant.tool_calls（翻译员把网页代码块翻成标准 tool_calls，规格 3.1 / 4.4） | adapter.parse 占位；contract 的 makeToolCallId / nonceFromToolCallId 为键映射真源 | 一致 | 方向一致，装配仍占位 |
| 10 | buildCard / dedupe 唯一键 | pending_tool_calls 按 tool_call_id 配对 | adapter.KEY = tool_call.id，buildCard / dedupe 以该 id 为唯一键 | 一致 | 同键，不含消息指纹 |
| 11 | reply 段 | tool 消息由 _normalize_item 保留 | adapter.reply 占位 + standardToolMessage 三键 | 一致 | 字段面一致 |
| 12 | restore 段（刷新恢复键） | A-7 无消息指纹面 | 05j / 05g 实改：标准 call_<nonce> 优先、旧 msgId 兼容双查、去消息指纹 | 一致 | C-7 唯一运行时实改，不切活链 |
| 13 | 协议字段退役 | A-7 未动该面 | PROTOCOL_RETIREMENT_CONTRACT 为 declared-placeholder | 待对拍 | B-7 未交付，字段替换位变更面待其 report 显式列出 |
| 14 | 旧标记摘除 | A-7 / C-7 均保留旧标记、活链保持 | 05g / 05j 仅改签名键，旧标记未摘 | 待对拍 | 01:17 裁定：待 B-7 交付与三笔对拍齐备后另行下发，不构成 C-8 验收条件 |

汇总：一致 10 条、待对拍 4 条、不一致：0 条。

## 二、端到端装配面只读推演

每步标：落在哪个已合入文件 / 哪步仍是占位 / 哪步依赖 B-7。
「仍占位」一律指 declared-placeholder、未装配到运行时 M；不代表字段面冲突。

| # | 步骤 | 落点（已合入文件） | 状态 | 依赖 B-7 |
| --- | --- | --- | --- | --- |
| 1 | 模型回复 fetcher 返回 None / str / dict | core/chat_completions.py：model_reply_hook / _as_assistant_reply | 已实交付（代码侧只到入口，L10 需外部服务与凭证） | 否 |
| 2 | 规范化追加 _normalize_item，三步一致 | core/chat_completions.py L95 | 已实交付 | 否 |
| 3 | 分发前钩子 _run_pre_dispatch_hooks(history) | routes/chat_api.py L36 / L60 / L213；chat_completions.py L356 为装配指引注释 | 已实交付；装配仍占位（chat_api.py L78 注释指引、无代码调用） | 否 |
| 4 | 标准 tool_call.id 建卡 | extend/lib/standard_chain_adapter.js buildCard；standard_chain_contract.js makeToolCallId | 仍占位；运行时建卡仍在 extend/dialog/parts/05g_cards.js，旧标记保留 | 否 |
| 5 | 执行 | standard_chain_adapter.js execute | 仍占位；运行时执行权在 05g_cards.js / 06_execute.js 旧直调路径 | 是 |
| 6 | tool 消息回执 | standard_chain_contract.js standardToolMessage；standard_chain_adapter.js reply | 字段面一致；装配仍占位 | 否 |
| 7 | 去重 | standard_chain_adapter.js dedupe；服务端 core/chat_completions.py pending_tool_calls | 服务端已实交付；前端去重仍占位 | 否 |
| 8 | 刷新恢复 call_<nonce> 键 | extend/dialog/parts/05j_card_sig.js 与 05g_cards.js（C-7 实改） | 已实改（标准键优先、旧 msgId 兼容双查、去消息指纹），不切活链 | 否 |
| 9 | 协议字段退役 | B-7 范围：服务端 / 网关 / remote_bridge 信封 | 未交付 | 是 |

## 三、边界与验证口径

- 范围：只新增本文件（extend/lib/ 下对拍矩阵文档）与 flask_server/tests/js/ 下断言夹具；
  不改 05g_cards.js / 05j_card_sig.js / 05c_prompt.js 等运行时文件，
  不改 core/chat_completions.py 与 routes/chat_api.py，不碰 B-7 协议字段退役面。
- 不把 adapter 装配到运行时 M、不建切换开关、不新增探测他笔是否存在的运行期分支、不切活链。
- 覆盖率：本笔不新增被测 JS 源文件（矩阵为 Markdown 文档），故不引入新的覆盖率分母；
  夹具只 require 已合入的两个 lib，其 line / branch 仍为 100 / 100，无退化与新增欠账。
- 本机 node v24 的「ℹ 前缀 / 分层路径」报告差异不作为达标依据；
  check_js_tests.py 直跑 rc 与覆盖率判定以分发方环境实测为准，
  未改钩子脚本 / 90-70 阈值 / js_coverage_baseline.json、未用 --update-baseline。
- 提交：基于实时 origin/main 新建提交，勿 amend 已合入历史；一次提交收口，
  force-with-lease 更新 origin/work/ai-c，send report 回 hash 与实测。
