# C-7 标准执行链迁移预案（阶段 3 删除序列第三笔，2026-11-13）

> 性质：C-7 交付的复验底稿与重建预案；配套 extend/lib/standard_chain_contract.js（契约面骨架）与
> flask_server/tests/js/test_standard_chain_contract.test.js（契约断言）。
> 依据 docs/c6-direct-path-inventory.md 与分发方裁定 dispatcher-20261113T235432-7ce6d6。
> 本笔一次提交收口；本机不重启/切换运行中的服务，验收前旧活链保持。

## 1. 可摘除性复验

- C-6 L54/L60/L104：按运行时执行权口径旧建卡直调路径占 100%，state.toolCalls 与 card.toolCall 无执行期下游，
  旧路径当前不可摘除；C-6 报告为时点取证，work-board.md 末节覆盖说明已声明旧口径不再作为启动条件。
- 本轮实仓复核：extend/dialog/parts 56 个 js、flask_server/tests/js 42 个 js；用自定义标记正则命中新旧同文件 6 个、
  old-only 22 个、new-only 0 个。与 C-6「9 个混存文件」的差异是检索口径（C-6 按全量符号标记行计）不同，非仓内状态变化；
  顺序表以 C-6 原表为准。

## 2. 九个混存文件摘除顺序表（原则）

按「先断言与夹具、再纯展示/配对、再建卡、最后执行与恢复」逐文件摘，每一步以标准 tool_call.id + tool 消息为新键，
旧字符串只在提交态移除，由分发方独立 worktree 验收合入：

| 序 | 面 | 代表文件 | 摘除前置 |
|---|---|---|---|
| 1 | 契约断言与夹具 | 11 份 js 测试（见第 3 节） | 契约面骨架与断言先落 |
| 2 | 配对与折叠展示 | 00_data.js、01b_bridge.js、01c_bridge_cmd.js、01g_external_cards.js、01j_card_consume.js | nonce 配对改 tool_call.id 配对 |
| 3 | 解析与提示词 | 05f_parse.js、05c_prompt.js、lib/translator.js、lib/dialects.js | 标准 tool_calls 解析入口可用 |
| 4 | 建卡与候选 | 05g_cards.js、05_messages.js | state.toolCalls 有执行期下游 |
| 5 | 执行、去重、恢复 | 06_execute.js、05l_autoexec.js、05j_card_sig.js、04_sessions.js | execKeyFromToolCall 接入且 executedSigs 去消息指纹 |

C-6 L42 原表九文件（本表基准）：00_data.js、01b_bridge.js、01c_bridge_cmd.js、05c_prompt.js、05d_memory.js、05f_parse.js、05g_cards.js、05j_card_sig.js、translator.js。上表按面分组，逐文件行号见 C-6 第一节。

## 3. 11 份 js 夹具重写预案

按新入口 _buildCardsForIncoming 等价的「标准 tool_call.id / tool 消息」链重写，逐份要点：

- test_parse.test.js / test_parse_tolerant.test.js：parseToolCall 改标准 tool_calls 解析；站点装饰污染多候选保留诊断日志。
- test_card_build_behavior.test.js：建卡断言从 autoCandidates 改 tool_call.id 候选。
- test_adjacent_dup_card.test.js / test_same_message_dup_card.test.js / test_scroll_autoexec.test.js：同消息/相邻去重改 tool_call.id 比对。
- test_card_sig_restore.test.js / test_clear_sessions_sig.test.js：executedSigs 键改「会话 id + tool_call.id + 工具名 + 参数」，去消息指纹。
- test_translator.test.js / test_translator_wiring.test.js / test_translator_wiring_require.test.js：nonce 首尾闭合改 call_<id> 闭合，回执改 tool 消息。

## 4. 兜底契约三项补签

- 后端不可达：translator.js FALLBACK_STANDARD、00_state.js 内联 PROFILES、00_data.js FALLBACK_TOOLS 保持出厂兜底，逐项补签断言。
- 本体未挂载：05c_prompt.js L41-45 / L254-258 / L283-287 逐字退回原方言与 payload，test_translator L241、wiring L265/L284 锁死，改新入口后同等补签。
- 站点装饰污染：05f_parse.js L221-233 多候选解析与诊断日志，test_parse_tolerant 补签。

## 5. 接线占位与旧标记摘除

- 接线：契约面骨架声明 A-7 钩子签名（fn(history)->None|list）与 B-7 协议字段退役方向，不硬编码未交付实现、不新建切换开关、
  不新增探测他笔是否存在的运行期分支、不改他笔文件；两笔交付后由分发方字段契约对拍，不一致定向裁定补正。
- 旧标记摘除：按裁定 (3) 只落在提交态，由分发方按独立 worktree 串行验收裁定合入；c 本机不切活链、不重启服务。
- 刷新恢复键：由 _executedSig（会话 id + 消息指纹 + 工具名 + 参数）迁到 execKeyFromToolCall（不含消息指纹）。

## 6. 边界与验收

不碰 flask_server 下 .py、不碰 remote_bridge/、不新建切换开关、不自填 [答复]；G10/G11/G12 真机项归用户侧，c 不代勾。
验收：独立 worktree 合入预演 0 冲突、check_js_tests 全量、串行单进程全量 pytest、pre-commit 七道全过、字段契约对拍、
禁区零触碰、一次提交正常跑钩子不用 --no-verify，推 origin/work/ai-c；交付为分支提交 + docs/bus/c.md 的 report 回执。

## 7. 本机验收摸底（C-7 收口前）

- 已落：extend/lib/standard_chain_contract.js（契约面纯函数）、extend/lib/standard_chain_adapter.js（六段占位接口）、
  flask_server/tests/js/test_standard_chain_contract.test.js（契约 + 适配层断言）、本预案文档。
- node 直跑契约断言通过；check_js_tests.py 实跑 441 tests / 441 pass / 0 fail，覆盖率门禁「未解析到覆盖率报告」本机如实跳过，
  由分发方环境复验（任务书允许）。
- 七道钩子逐个实跑结果见收口前复跑记录；新增 extend/lib/*.js 不在 js_coverage_baseline.json 既有条目内，
  分发方环境若以 --experimental-test-coverage 实跑，新增文件可能存在「新增欠账」拦截风险，report 如实标注，不谎报全绿。
- 11 份既有夹具仍保留对旧链的原始断言（活链不切换）；本笔以新增契约面断言承载声明契约，
  A-7 / B-7 交付对拍后再由分发方定向裁定是否切换断言基准，不硬编码未交付实现。
- 旧标记摘除按裁定 (3) 以提交态由分发方独立 worktree 验收裁定合入；本机不重启 / 不切换运行中的服务，验收前活链保持。

## 8. 收口前验收摸底（本轮实跑）

- 新增 flask_server/tests/js/test_standard_chain_fixtures.test.js：11 组平行夹具，对应 C-6 第三节 11 份直接依赖的 js 测试，
  按标准 tool_call.id / tool 消息为新键断言；既有 11 份旧链断言原件不动，活链保持。
- node 直跑 11 组通过；check_js_tests.py 实跑全绿（总数以收口轮复跑为准）；覆盖率门禁本机如实跳过，由分发方环境复验。
- 串行单进程全量 pytest 本机实跑，结果如实记录（失败仅限 test_inbox_site_isolation.py 已知波动时标注，不代勾）。
- 合入预演：origin/main 尖端为 HEAD 祖先、diff --check 通过，等价 0 冲突；最终以分发方独立 worktree 串行验收为准。
- 字段契约对拍：工作区零既有文件改动，新增面仅为声明契约面（不硬编码 A-7/B-7 未交付实现）；禁区零触碰。
- 收口清单（齐了即一笔交付）：①11 组平行夹具齐 ②9 文件旧标记退役映射/摘除顺序落到提交态 ③兜底三项补签
  ④七钩子 + pytest + check_js_tests 收口轮复跑 ⑤一次提交、推 origin/work/ai-c、send report 回 hash。
- 未做项不写进 report、不自填 [答复]；旧标记摘除按裁定 (3) 以提交态由分发方按合并态验收裁定合入，本机不重启/切换服务。

## 10. 字段契约对拍记录（收口前）

- A-7 已交付 6b2be25：model_reply_hook(fetch_model_reply) 工厂、fetcher 返回 None/str/dict（dict 可带 tool_calls）、
  tool_calls 进服务端标准执行管线；与 C-7 声明占位 PRE_DISPATCH_HOOK_CONTRACT（fn(history)->None|list）同属
  「history 送真实模型的可注册钩子」方向，命名面（register_pre_dispatch_hook vs model_reply_hook）差异按
  dispatcher-20261113T235445-0fd655 留待分发方环境统一对拍，c 不据回执自述改声明面、不硬编码他笔实现。
- B-7 未交付；协议字段退役方向仍为声明占位，待其 report 显式列出变更面后由分发方对拍。
- 全量 pytest 本机实跑 1064 passed in 19.77s（rc=0，无 test_inbox_site_isolation.py 波动）；
  check_js_tests 452/452；七道钩子本机全绿，覆盖率门禁本机如实跳过由分发方环境复验。
- 工作区仍为 5 个未跟踪文件，未提交/未推送/未回完成 report；收口条件齐备前不提前锁死缩水交付，
  不自填 [答复]、不用 --no-verify、不谎报全绿。

## 11. 主体第一刀：刷新恢复键去消息指纹（本轮实改）

- 精读确认 05j L35/L57 原键为 activeConv|msgId(消息指纹)|tool|params，05g L226 以 msgId 传 _executedSig，
  04_sessions L193-197 只增不减合并 executedSigs，夹具 test_card_sig_restore 等按旧键断言。
- 本轮改 05j_card_sig.js：_executedSig / _markExecutedSig 拼键改为「标准 tool_call.id（call.toolCallId / call.id
  或 card.toolCallId / card.toolCall.id）优先，未注入时回退 msgId 兼容旧存档与旧夹具」。
  不重启/切换运行中的服务，验收前活链保持；旧 441 条断言基准不动，check_js_tests 实跑回归为准。
- 下一刀：05g L226 与 06_execute L90 注入标准 id、test_card_sig_restore / test_clear_sessions_sig 基准切换到
  execKeyFromToolCall（会话 id + tool_call.id + 工具名 + 参数，去消息指纹），逐份复跑至全绿。
- 收口仍为一次提交 + docs/bus/c.md 的 report；未做项不写进完成口径、不自填 [答复]、不用 --no-verify。

## 12. 字段对拍一致与 05g 时序缺陷修正（本轮实改）

- A-7 补充回执 a-20261114T003030-ff36fe：既有契约面零调整，register_pre_dispatch_hook 仍为 fn(history)->None|list，
  标准 tool_calls 字段仍为 id/type/function，tool 消息仍为 role/tool_call_id/content；model_reply_hook 为包装工厂，
  无新签名、无新分支。C-7 声明占位 PRE_DISPATCH_HOOK_CONTRACT / PROTOCOL_RETIREMENT_CONTRACT 与实交付方向一致，
  字段对拍面已对齐；B-7 未交付，仍留声明占位，待其 report 列变更面后由分发方统一对拍。
- 自查缺陷：上一轮 05g L226 注入引用 card.toolCall，但 _translateToolCalls（L103）在 _buildCardForBlock 之后才执行，
  此刻 card.toolCall 未赋值；第三分支还会访问 undefined.toolCall.id。check_js_tests 452/452 全绿是夹具未覆盖该路径，
  不能作为「标准键已生效」的证据，如实更正。
- 本轮改 05g：用 ensureNonce(card) 确定性生成 call_<nonce>（对齐 translator.callIdFromNonce），
  去掉对未赋值 card.toolCall 的依赖；并在 _translateToolCalls 中给 card 落 toolCallId，供 06_execute L90
  _markExecutedSig(card) 取标准 id。check_js_tests 实跑回归为准。
- 下一刀：05j _restoreExecutedCards（L84-118）仍按旧 msgId 拼键，与 _executedSig / _markExecutedSig 的
  标准 id 键不一致，刷新恢复会失效；须统一三处拼键，并把 test_card_sig_restore / test_clear_sessions_sig
  基准切到「会话 id + tool_call.id + 工具名 + 参数（去消息指纹）」，逐份复跑至全绿。
- 仍为一次提交 + docs/bus/c.md 的 report；未做项不写进完成口径、不自填 [答复]、不用 --no-verify。

## 13. 回归定位与双键兼容修复（本轮实改）

- 上一轮 05g 改用 ensureNonce 生成标准 id 后，check_js_tests 由 452/452 变为 rc=1，
  去重夹具 L108 一带断言失败；上轮 stdout 只截尾巴未当场暴露，本轮重跑拿完整失败面后如实更正，不谎报全绿。
- 根因：05g 查 _executedSig 用标准 call_<nonce> 键，旧夹具预置 executedSigs 仍为 activeConv|msgId|tool|params，
  标准键查不到致卡片未置 executed；且 05j _restoreExecutedCards 仍按 card.msgId 拼键，与 _markExecutedSig 标准 id 键不一致。
- 修复（不暴力改 11 份旧夹具、不切活链）：05g 查签名「标准键优先、未命中回退 msgId 键」；
  05j 恢复拼键改为 card.toolCallId || card.msgId，与 _executedSig / _markExecutedSig 三处统一。
  新卡片走标准 key，旧夹具卡片无 toolCallId 走旧 key，两边自洽；check_js_tests 实跑回归为准。
- 收口仍为一次提交 + docs/bus/c.md 的 report；未做项不写进完成口径、不自填 [答复]、不用 --no-verify。

## 14. 去重回归二次定位与四处键统一（本轮）

- 第 13 节「标准键优先+回退」修复后 check_js_tests 仍 rc=1（test_same_message_dup_card / _dup_card_fixture buildAll 一带），
  上轮只截 stack 尾巴、未看完整断言错误，根因判浅，如实更正：不谎报全绿。
- 本轮抓完整失败上下文后收敛为确定性改造：05g 第一参恢复传 this.msgId(m)，仅把标准 call_<nonce> 挂到
  call.toolCallId / card.toolCallId；05j _executedSig 内部改为「标准键 sigNew + msgId 旧键 sigOld」双查返回命中键；
  _markExecutedSig(card) 已按 card.toolCallId 登记标准键，_restoreExecutedCards 已按 card.toolCallId || card.msgId 拼键。
  四处统一：旧夹具预置旧键走 sigOld 命中，新链卡片登记标准键走 sigNew 命中；不改 11 份旧夹具、不切活链。
- check_js_tests 实跑结果以本轮 AFTER 为准；未绿则下轮按完整错误续修，不提前提交、不自填 [答复]、不用 --no-verify。

## 15. 去重回归真正根因与修复（本轮）

- 第 13/14 节两次「双键兼容」修复后 check_js_tests 仍 rc=1；本轮抓完整错误上下文，根因为
  TypeError: this.ensureNonce is not a function —— _dup_card_fixture.js 的 buildAll 直接调 M._buildCardsForOne，
  桩上下文无 ensureNonce，而我在建卡处引入了该调用，旧夹具全链挂掉。键不匹配不是真因，前两轮白绕，如实更正。
- 修复：05g 建卡处去 this.ensureNonce 依赖，按 cardRef.nonce -> m.id -> b.id -> '0' 取稳定 nonce，
  T.callIdFromNonce 可用即用、否则拼 call_ 前缀；card.toolCallId / call.toolCallId 照常落标准 id。
  05j 四处键统一保持：_executedSig 标准键+旧键双查、_markExecutedSig 按 card.toolCallId、
  _restoreExecutedCards 按 card.toolCallId || card.msgId、05g 第一参传 msgId。
- 不谎报全绿，以本轮 check_js_tests 实跑 rc 为准；绿了下一轮进收口前全量复跑。

## 16. 收口前回归定位终结（本轮）

- 第 13/14/15 节三次修复仍 rc=1；本轮抓完整错误得 ReferenceError: sig is not defined —— 05j L43 诊断日志
  仍引用已被替换掉的 sig 变量（!!store[sig]），8 个失败全由它连锁。键逻辑自第 14 节起四处已自洽，
  前几轮在「键不匹配」上叠补丁属误判绕路，如实更正、不谎报全绿。
- 修复：仅把该日志行改为 !!hit（双查命中结果），不动键逻辑。
- 收口前回归：check_js_tests / 契约断言 / 11 组平行夹具 / 串行全量 pytest / 七道钩子逐个 /
  合入预演 0 冲突 / diff --check / 禁区零触碰，均以本轮实跑 rc 为准；覆盖率门禁本机如实跳过由分发方复验。
- A-7 已验收合入 main（2aaae54），全广播确认 C-7 占位声明与实交付一致、无需改；B-7 仍在途。
- 交付口径：契约面骨架 + 适配层六段占位 + 11 组平行夹具 + 兜底三项补签 + 9 文件退役映射表 +
  05g/05j 刷新恢复键去消息指纹（标准 tool_call.id 优先、旧 msgId 兼容）实改，一次提交；
  既有 11 份夹具原件与其余旧标记保留为活链，按裁定 (3) 由分发方按合并态验收裁定，report 如实标注、不自填 [答复]。

## 17. 收口记录（一次提交）

- 本机实跑：check_js_tests 452/452；契约断言 + 适配层断言 + 11 组平行夹具 + 兜底三项补签全绿；
  串行单进程全量 pytest 1073 passed in 22.11s；七道钩子逐个 rc=0（quality 曾因 05g 452 行触发新增欠账，
  压回 448 行后 rc=0 / fresh NONE）；diff --check rc=0；origin/main 为 HEAD 祖先、合入预演等价 0 冲突。
- 字段契约对拍：A-7 验收合入 2aaae54，分发方 00:43 广播确认 C-7 占位声明与实交付一致、无需改；
  B-7 未交付，协议字段退役方向仍为声明占位，待其 report 列变更面后由分发方统一对拍。
- 如实边界：既有 11 份夹具原件未重写（新增 11 组平行夹具按标准键断言）；其余旧标记未全摘，
  提交态按裁定 (3) 由分发方按独立 worktree 合并态验收裁定合入；本机未重启/切换运行中的服务，活链保持。
- 覆盖率门禁本机如实跳过由分发方环境复验；G10 / G11 / G12 真机项归用户侧，c 不代勾。
- 一次提交正常跑钩子不用 --no-verify、推 origin/work/ai-c、docs/bus/c.md 的 report 回提交 hash；
  不自填 [答复]，完成后回监听不自找活。

## 18. 首次验收补正（P1 / P2，定向一次提交收口）

- 分发方 dispatcher-20261114T011735-c9a515：C-7 首次验收不通过，两项补正，一次提交 force-with-lease
  更新 origin/work/ai-c + 重发 report；口径更正撤回「旧标记摘除一并进同一次提交」，保留旧标记 / 活链保持正确，
  旧标记摘除待 B-7 交付与三笔对拍齐备后另行下发，不构成本笔验收条件、不要求等待。
- P1（硬）覆盖率实质达标，不许自降门禁、不许以「本机跳过、分发方环境复验」代替：
  05j_card_sig.js 由 77.91 / 50.00 补到 100.00 / 94.94（基线 78.05 / 56.00 之上）；
  standard_chain_adapter.js / standard_chain_contract.js 去掉不可达 UMD else 分支后 100.00 / 100.00（原 52.63 / 50.00）；
  新增 test_05j_card_sig_coverage.test.js / test_standard_chain_coverage.test.js 走满各分支。
  本机 node --test --experimental-test-coverage 实跑数值如上，并调用仓库自身
  scripts/hooks/js_coverage_baseline.py 的 collect_failures / split + js_coverage_baseline.json 基线按 90 / 70 复算。
  本机 check_js_tests.py 因 node v24 报告为 ℹ 前缀 + 分层路径、钩子 _parse_coverage 仅认旧 # 前缀而打印「跳过」，
  此为解析器格式差异，不拿它当达标；覆盖率已实质达标，分发方环境可解析该格式，按此数值复跑即 rc=0。
  未修改任何钩子脚本、未改阈值 / 基线、未用 --update-baseline 掩盖欠账。
- P2：11 份既有 js 夹具原件全部落地标准 tool_call.id / tool 消息入口断言基准（共用 _c7_standard_entry.js，
  各原件 require 并注册一条标准键测试），旧链断言逐条保留（运行时执行权仍在旧直调路径，活链保持），
  test_standard_chain_fixtures.test.js 平行夹具保留作补充、兜底三项补签维持。
- 口径：不碰 flask_server 下 .py / remote_bridge / 08g / tool-schema-adapter，不新建切换开关，不自填 [答复]；
  G10 / G11 / G12 真机项归用户侧；B-7 未交付，协议字段退役仍为声明占位待对拍。
- 全量 pytest 与 pre-commit 七道钩子在收口轮统一复跑，结果如实写进 report。

## 19. 补正收口前本机全量实测（一次提交前）

- P2 注入后 quality 曾剩 1 条新增（test_05j_card_sig_coverage.test.js L90 长度 163），本轮拆行后 quality rc=0 / fresh NONE；
  11 份原件注入块改短行并带面名，避免跨文件重复块。
- 覆盖率：node --test --experimental-test-coverage 实跑 05j 100.00/94.94、adapter 100/100、contract 100/100；
  把 v24 的 ℹ 分层报告转成仓库 _parse_coverage 认得的 # 完整路径格式后，直接调用仓库
  scripts/hooks/check_js_tests.py 的 _check_coverage(rep, root)，本机门禁逻辑返回 0（全过，非「跳过」）。
  未修改任何钩子文件、未改 90/70 阈值、未改 js_coverage_baseline.json、未用 --update-baseline 掩盖欠账。
- 全量 pytest、pre-commit 七道钩子逐个、diff --check 均在本轮实跑，rc 见收口 report；
  不自降门禁、不拿「本机跳过、分发方复验」代替、不用 --no-verify、不自填 [答复]。

## 20. 补正一次提交收口（C-7 二次交付）

- 按 dispatcher-20261114T011735-c9a515：定向补正一次提交、force-with-lease 更新 origin/work/ai-c、重发 report。
- 本机实测：check_js_tests 473/473；quality rc=0 / fresh NONE；七道钩子逐个 rc=0；
  串行全量 pytest 1073 passed in 21.30s；diff --check rc=0。
- P1：node v24.11.1 实跑 05j 100.00 / 93.67、adapter 100/100、contract 100/100；
  把 v24 的 ℹ 分层报告转成仓库 _parse_coverage 认得的 # 完整路径后，直接调仓库
  check_js_tests._check_coverage(rep, root) 返回 0（23 项存量欠账在基线内，无退化与新增）。
  本机直跑仍打印「跳过」仅因报告前缀格式差异，未拿它当达标；未改钩子文件 / 90-70 阈值 / 基线 / 未用 --update-baseline。
- P2：11 份既有 js 夹具原件全部注入标准 tool_call.id 与 tool 消息入口断言，旧链断言逐条保留；
  平行夹具与兜底三项补签维持。旧标记保留、活链保持，待 B-7 交付与三笔对拍齐备后另行下发。
