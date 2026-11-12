# C-6 翻译员旧直调路径盘点（阶段 3 准备取证）

> 取证范围：extend/ 下前端运行链路；flask_server/ 下 .py 只读参照，不纳入改动。
> 取证方式：全仓符号检索 + 关键区间逐行精读 + 测试夹具依赖面核对。
> 本文件为只读盘点结论，不含删除清单；阶段 3 删除动作以分发方裁定为准。

## 一、两条路径的落点

### 1.1 新标准链路（阶段 2 翻译员本体与接线）

| 环节 | 落点 | 职责 |
|---|---|---|
| 本体 | extend/lib/translator.js（173 行） | 标准 tool_calls / tool 消息双向翻译、提示词拼装、语言包与指令取回、call_<nonce> 与 nonce 互换 |
| 方言层 | extend/lib/dialects.js（90 行） | 按站点分派语言包与四支方言处理函数，出厂兜底选择器 |
| 挂载 | extend/dialog/dialog.html L23-25、extend/manifest.json L27-28 | 先 dialects 后 translator（tool-schema-adapter 同批挂载） |
| 上下文取回 | extend/dialog/parts/01b_bridge.js L127-151 | 启动取 /v1/system_prompt、/api/clients 语言包、/api/commands，写入 T.state 并重建提示词 |
| 指令定义刷新 | extend/dialog/parts/01b_bridge.js L158-171 | refreshCommandDefinitions 只登记定义，不改执行通道 |
| 语言包应用 | extend/content/05_index.js L38-51 | applyLanguagePack 把 /profiles 聚合的 custom_config 交给方言层 |
| 提示词拼装 | extend/dialog/parts/05c_prompt.js L39-45 | generateSystemPrompt = 取回标准四段 + 追加方言说明；本体未挂载时逐字退回原模板 |
| 解析接线 | extend/dialog/parts/05g_cards.js L102-143 | 建卡末尾 _translateToolCalls：本轮工具卡片产出 card.toolCall 与 state.toolCalls，多调用产出 multiple_tool_calls 告警 |
| 回执接线 | extend/dialog/parts/05c_prompt.js L208-259、L271-288 | resultText / screenshotMark 把执行信封经 toToolMessage 到 fromToolMessage 转成 bridge-chat-res；本体缺失时逐字退回原 payload |
| 字段适配 | extend/lib/tool-schema-adapter.js（37 行） | 标准 JSON Schema 还原为旧扁平参数项，设置页与提示词复用（C-4 收口，C-6 禁区） |

新链路在 extend/ 下的标记命中合计 95 行 / 12 文件；其中本体与方言层两个新增文件共 263 行，05g_cards.js 18 行、05c_prompt.js 15 行、01b_bridge.js 10 行、05_index.js 8 行为主要接线面。

### 1.2 旧建卡直调路径（阶段 2 之前既有运行主链）

| 环节 | 落点 | 职责 |
|---|---|---|
| 调用解析 | extend/dialog/parts/05f_parse.js L205-253 | parseToolCall：站点装饰容错、原生单键形态兼容、只认 bridge-chat-call |
| 消息来源 | extend/dialog/parts/05f_parse.js L381-393 | msgSource：含 bridge-chat-res 的 user 消息判为 tool |
| 建卡与候选 | extend/dialog/parts/05g_cards.js L33-259 | _buildCardsForIncoming 到 _buildCardForBlock / _makeCard / _markDuplicateCard / collectAutoCandidate，产出 autoCandidates、armedLast、rerunCard |
| 执行 | extend/dialog/parts/06_execute.js L40 起 | executeCard：preIssue 接管、幽灵卡片拦截、调后端 /tool、失败归因与堆栈 |
| 自动执行收尾 | extend/dialog/parts/05l_autoexec.js L22-147 | _collectAutoExecCandidates / _finalizeAutoExec / _maybeAutoExecOnScroll，只消费 autoCandidates、rerunCard、armedLast |
| 回传 | extend/dialog/parts/06_execute.js L294 起、05c_prompt.js L208 起 | postCardResult：截图、文件附件、文本三分支，经统一发送队列回传网页 AI |
| 去重与恢复 | extend/dialog/parts/05j_card_sig.js L24-118、04_sessions.js L279-282 | executedSigs 落盘，_executedSig / _markExecutedSig / _restoreExecutedCards / cardMatchesBySig |
| 会话装配 | extend/dialog/parts/00_data.js L57-79、L110 起 | cardHasMessage 按 nonce 配对 external-call 与 bridge-chat-res，buildTimeline 去重外部卡片 |
| 镜像渲染 | extend/dialog/parts/07_cards.js L246 起、05d_memory.js L52-70 | 工具结果独立第三类角色、不误触记忆窗口 |
| 用户指令旁支 | extend/dialog/parts/01b_bridge.js L396-404 | runBridgeCommand 走 /api/bridge/run-command，与 QQ 指令同链；回执不进 AI 对话流 |
| 外部卡片 | extend/dialog/parts/01g_external_cards.js L239、01j_card_consume.js | external-call 信封与卡片消费，网关投递链仍在用 |

旧直调标记命中合计 151 行 / 26 文件；协议标记（bridge-chat-call / bridge-chat-res / TOOL_RESULT）命中 38 行 / 14 文件。9 个文件同时含新旧两类标记：00_data.js、01b_bridge.js、01c_bridge_cmd.js、05c_prompt.js、05d_memory.js、05f_parse.js、05g_cards.js、05j_card_sig.js、translator.js。

## 二、占比口径

| 维度 | 新标准链路 | 旧直调路径 | 说明 |
|---|---|---|---|
| 符号命中行 | 95 | 151 | 约 39% 比 61%，按检索标记行计，含注释 |
| 涉及文件 | 12 | 26 | 9 个文件混存两套逻辑 |
| 新增本体代码 | 263 行（2 文件） | 不适用 | translator.js 加 dialects.js |
| 运行主路径 | 翻译、契约、告警叠加层 | 解析、建卡、执行、回传、恢复全链 | 旧路径承担每一次真实工具执行 |
| 运行时下游消费者 | toolCalls 0 处、card.toolCall 2 处（仅取回执 id） | autoCandidates 等被 05l_autoexec.js 与 05_messages.js 消费 | 新链路不驱动 executeCard |

按标记行口径旧路径约占六成；按运行时执行权口径，旧路径占 100%：state.toolCalls 与 card.toolCall 在 extend/ 运行时没有驱动执行的下游，只有 flask_server/tests/js/test_translator.test.js、test_translator_wiring.test.js、test_translator_wiring_require.test.js 三份接线测试断言它们。05_messages.js L293-294 把 _buildCardsForIncoming 的返回交给 _finalizeAutoExec，后者只读 autoCandidates、rerunCard、armedLast。

## 三、可摘除性评估

### 3.1 当前结论

旧建卡直调路径当前不可摘除。新标准链路是叠加在旧主链上的翻译与契约层：模型仍按 bridge-chat-call 回复，解析仍走 05f_parse.parseToolCall，执行仍由旧卡片候选驱动，回执仍以 bridge-chat-res 贴回网页对话。摘除旧路径等于摘除唯一执行主链，须先由 A-5 把标准 tool_calls 接真实模型闭合（L10），并把解析、执行、回传、恢复整体迁到标准链路之后，才具备评估前提。

### 3.2 摘除会牵动的面

夹具与测试（flask_server/tests/js/，共 42 个 js 测试文件）：

| 面 | 直接依赖的测试 |
|---|---|
| parseToolCall 与 bridge-chat-call 解析 | test_parse.test.js（24 命中）、test_parse_tolerant.test.js（11）、test_card_build_behavior.test.js（17） |
| 建卡候选与去重 | test_adjacent_dup_card.test.js、test_same_message_dup_card.test.js、test_scroll_autoexec.test.js、_dup_card_fixture.js |
| 刷新恢复签名 | test_card_sig_restore.test.js、test_translator_wiring.test.js L329、test_translator_wiring_require.test.js |
| 翻译员接线 | test_translator.test.js（26）、test_translator_wiring.test.js（68）、test_translator_wiring_require.test.js（56） |
| 提示词与适配层 | test_05c_prompt_schema_coverage.test.js、test_tool_schema_adapter.test.js（C-4 收口，C-6 禁区） |

其中 test_translator_wiring 系列以 _buildCardsForIncoming 为真实入口断言 nonce 首尾闭合与 toolCalls 产出；旧建卡链一旦移除，这两份测试的入口与断言基准同步失效，须随标准执行链重建夹具。

兜底与降级：

- translator.js L25-36：FALLBACK_STANDARD 在 /v1/system_prompt 不可达时保底；fetchStandard / fetchLanguagePack / fetchCommands 失败均返回空值不阻断。
- 05c_prompt.js L41-45：本体未挂载（旧夹具、异常环境）时逐字退回原方言模板；test_translator.test.js L241 与 test_translator_wiring.test.js L265、L284 锁死这一行为。
- 05c_prompt.js L254-258、L283-287：resultText 与 screenshotMark 在本体缺失时逐字退回原 payload。
- dialects.js L11-17：语言包缺键回退出厂选择器；00_state.js 内联 PROFILES 为后端不可达时出厂兜底；00_data.js L88-97 FALLBACK_TOOLS 为占位工具目录。
- 05f_parse.js L221-233：站点装饰污染时多候选解析加诊断日志；原生单键形态守卫依赖 this.tools 注册表。

上述兜底全部挂在旧链路的对象与协议字段上；标准链路本体自身也以本体缺失回退旧行为为设计前提。摘除旧路径须连同这些降级契约一并重写，否则后端不可达、本体未挂载、站点装饰污染三类场景会直接断链。

刷新恢复与去重：

- _executedSig 以会话 id 加消息指纹加工具名加参数拼键，_markExecutedSig 在卡片执行后登记，executedSigs 随 04_sessions.js L282 落盘。
- 05g_cards.js L226-231：建卡时命中签名即置 executed / done / restoredFromSig；05j_card_sig.js L79-118 在会话加载完成后 _restoreExecutedCards 补判，纠正签名库异步取回晚于建卡的时序差。
- cardMatchesBySig（05j_card_sig.js L140-158）按工具名加参数在镜像里复核幽灵卡片；06_execute.js L20-33 据此拦截不可见卡片。
- _collectAutoExecCandidates（05l_autoexec.js L41-42）排除 executed、duplicate、running；_finalizeAutoExec L84-99 要求会话加载完成、isTreeTail 命中、自动开关开启。
- _markDuplicateCard（05g_cards.js L166-191）按同消息与相邻消息比对签名；cardHasMessage（00_data.js L57-79）按 nonce 配对 external-call 与 bridge-chat-res 防镜像区重复渲染。

整条恢复链绑定在旧卡片对象、bridge-chat-call 解析结果、bridge-chat-res 回执文本三者上。card.toolCall 只用于给回执补 call_<nonce> 前缀，没有替代的持久化键；标准 tool_calls 当前无独立存档与恢复语义。

### 3.3 摘除前置（供分发方判定，非本任务动作）

1. L10 闭合：/v1/chat/completions 的标准 tool_calls 链路接真实模型，代码侧可插拔入口由 A-5 提供，真实接入需外部模型服务与凭证。
2. 标准执行链落地：解析、建卡候选、执行、回执、去重、刷新恢复整体以标准 tool_call.id 与 tool 消息为键重建，且 toolCalls 出现真实运行期消费者。
3. 协议字段退役取证：B-6 产出 run-command、external-call、is_tool_result 调用方地图，确认网关投递链、信封解析、记忆蒸馏对 bridge-chat-res 与 external-call 的依赖已迁移。
4. 夹具重建：上表 11 份相关 js 测试按新入口重写，兜底契约逐项补签。
5. 三条阶段 3 前置同时满足（真实使用跑够时间、六项逐一验证、旧路径已无调用方），由分发方下发删除动作。

当前状态：前置 1 未满足（真实模型未接）、前置 3 未满足（remote_bridge 为活链路，run-command 与 external-call 仍有调用方）。C-6 只出盘点结论，不下发、不执行任何删除。

## 四、验收实测（本机）

| 项 | 命令 | 结果 |
|---|---|---|
| 前端逻辑 | python scripts/hooks/check_js_tests.py | 440 tests / 440 pass / 0 fail；覆盖率门禁本机输出「跳过覆盖率门禁：未解析到覆盖率报告」，如实记为跳过，由分发方环境统一复验 |
| 后端串行全量 | python -m pytest tests -q -p no:cacheprovider（flask_server/ 下，单进程） | 1055 passed in 18.65s，零失败 |
| 七道钩子 | pre-commit run --all-files | 语法、卫生、结构质量、文档同步、前端逻辑、主题副本、依赖漂移 7 项全 Passed |
| 边界 | git status 与改动面核对 | 既有运行链路零改写；新增本报告 1 份，docs/work-ai-c.md 第五节只追加 1 段 |