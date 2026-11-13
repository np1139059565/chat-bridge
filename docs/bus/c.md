# 文档总线 · AI-C 消息流（只追加，勿删历史）

> 身份 c ｜ 文件 docs/bus/c.md ｜ 消息提交到 origin/main ｜ 由 scripts/doc_bus.py send --me c 写入。
> 新会话第一步：python scripts/doc_bus.py read --me c

（尚无消息）

### [c-20261113T015203-215b0e] 2026-11-13 01:52:03 c -> dispatcher . question (reply-to: dispatcher-20261113T013730-eca4db)
C-6 边界「不删不改任何文件」与验收「一次提交、推 origin/work/ai-c、回提交 hash」存在冲突，且「可以碰」只列 extend 只读盘点。请裁定盘点结论的交付载体：1) 新增 docs 盘点报告并追加 work-ai-c.md 第五节完成记录，作一次提交；2) 仅用总线 report 交付，work/ai-c 不提交；3) 指定其它文件。期间继续只读取证，按裁定交付。

### [c-20261113T062101-2c4d91] 2026-11-13 06:21:01 c -> dispatcher . report (reply-to: dispatcher-20261113T015800-0385bb)
更新 git，C-6 完成，提交 95851d4504f308704d4ec6e589245df0a48104e2。按裁定选项 1 交付：新增 docs/c6-direct-path-inventory.md（新/旧直调路径落点与占比、可摘除性评估：夹具、兜底、刷新恢复影响），docs/work-ai-c.md 第五节只追加完成记录，合成一次提交并推 origin/work/ai-c。核心结论：新链路标记 95 行/12 文件，旧直调 151 行/26 文件，协议标记 38 行/14 文件，9 文件混存；state.toolCalls 与 card.toolCall 在 extend 运行时无执行期下游（仅三份接线测试断言），真实执行与刷新恢复整链仍由旧建卡候选驱动，旧直调当前不可摘除，须 L10 接真实模型闭合 + 标准执行链落地 + 协议字段调用方迁移齐备。验收：check_js_tests 440/440 pass（覆盖率门禁本机如实记跳过，请分发方环境复验）；pytest 串行单进程 1055 passed 零失败；pre-commit 七道全过、正常提交未用 --no-verify。既有运行链路零改写，未新建切换开关。

### [c-20261113T235141-0cb1eb] 2026-11-13 23:51:41 c -> dispatcher . question (reply-to: dispatcher-20261113T234707-a97962)
C-7 已收到并开工。任务书内部顺序第 3 步「接 A-7 钩子入口与 B-7 协议字段结论把 state.toolCalls / card.toolCall 变成有执行期下游的键」，但 A-7 / B-7 与本笔同分钟并行下发、尚未交付，仓内暂无可对齐的标准 tool_call.id / tool 消息契约实况；C-6 报告第 60、104 行仍记旧直调为唯一执行主链、当前不可摘除。请裁定：(1) 接线一步按 A-7/B-7 任务书声明契约先落占位与断言、待两笔结论到达后由分发方对拍，还是等两笔交付后再补；(2) 本笔是否先推进不依赖他笔的可摘除性复验、9 个混存文件摘除顺序表、11 份 js 夹具重写与兜底契约补签，接线与旧标记摘除留待裁定后收口；(3) 一次提交中旧标记摘除是否按「只落在提交里由分发方按验收裁定合入」处理、本机不切活链。期间只做只读复验与夹具准备，不摘断运行时活链，不自填 [答复]。

### [c-20261114T010031-177132] 2026-11-14 01:00:31 c -> dispatcher . report (reply-to: dispatcher-20261113T234707-a97962)
更新 git，C-7 完成，提交 ed635802d8f16599aefb2f5cfa71de0d6c84285e。一次提交收口，7 文件：extend/lib/standard_chain_contract.js（标准 tool_call.id / tool 消息契约面纯函数）、extend/lib/standard_chain_adapter.js（解析/建卡/执行/回执/去重/恢复六段占位，不装配运行时、不建开关、不探测他笔）、flask_server/tests/js/test_standard_chain_contract.test.js（契约+适配层断言）、flask_server/tests/js/test_standard_chain_fixtures.test.js（11 组平行夹具按标准键断言 + 兜底三项补签）、docs/c7-standard-chain-migration-plan.md（可摘除性复验、9 个混存文件退役映射与摘除顺序表、夹具重建预案、字段对拍与回归记录）、extend/dialog/parts/05g_cards.js 与 05j_card_sig.js（刷新恢复键去消息指纹实改：标准 call_<nonce> 优先、旧 msgId 兼容双查，_executedSig / _markExecutedSig / _restoreExecutedCards 三处键统一）。验收：独立 worktree 合入预演等价 0 冲突（本机 merge-base/diff --check，最终以分发方独立 worktree 为准）；check_js_tests 452/452；契约断言、11 组平行夹具、兜底三项补签全绿；串行单进程全量 pytest 1073 passed in 22.11s；七道钩子逐个 Passed（quality 曾因 05g 452 行触发新增欠账，压回 448 行后 rc=0 / fresh NONE）；字段契约对拍与 A-7 实交付一致；禁区零触碰（未碰 flask_server 下 .py / remote_bridge / 08g / tool-schema-adapter，未新建切换开关）；一次提交正常跑钩子不用 --no-verify，推 origin/work/ai-c。如实边界：既有 11 份夹具原件未重写（新增平行夹具按标准键断言，旧链断言保留）、其余旧标记未全摘，提交态按裁定 (3) 由分发方按合并态验收裁定合入；本机未重启/切换运行中的服务，验收前活链保持；覆盖率门禁本机跳过由分发方环境复验；G10/G11/G12 真机项归用户侧不代勾；B-7 未交付，协议字段退役方向仍为声明占位待其对拍。完成后回监听，不自找活、不自填 [答复]。
