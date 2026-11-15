# B-7 协议字段退役 · 收口片现状与替换位列全情况说明

> 2026-11-15 AI-B 交付（对应 docs/work-ai-b.md 当前任务 B-7 收口片，按 19:26:29 拆片通知收窄）。
> 性质：只读「现状 + 替换位列全情况说明」，零代码改动、零行为改动、不切活链、不新建切换开关。
> 证据基线：origin/main 7afe584（含 C-12 e9e3844 的 M1-M8 映射清单）；行号为本轮 git grep 实测。
> 交付形态：本文件 + docs/work-ai-b.md 第五节完成记录一次提交，M3/M4/M5 落点实装已由 B-8 接走、M1/M2/M6/M7/M8 已由 B-9 接走（均按 01:07:37 方案 A 纯函数层口径），本笔不写实现面代码。

## 一、总述

按 19:25 拆片决定，B-7 收口片只交付两件：已完成子面的代码侧现状结论（第二节）、协议字段替换位 M1-M8 全量列名（第三节，供分发方对拍 B-8/B-9 的纯函数层落点）。落点实装（旧位不再生效/新位生效的纯函数层断言）不在本笔范围，避免与 B-8/B-9 撞车。

## 二、四个已完成子面的现状结论（服务端 / 网关侧代码实况）

### 2.1 run-command 退役取证（M3）

- 调用方现状：调用方地图（B-6）与本轮复验一致——**网页抽屉唯一调用方**（extend/dialog/parts/01b_bridge.js:400，POST /api/bridge/run-command，:392 注释「与 QQ 里敲指令完全同一条链路」）；Flask 侧唯一入口 flask_server/routes/bridge.py:294；三网关（qq_gateway.py / wecom_gateway.py / weixin_gateway.py）grep `run-command` 零命中（本轮 2026-11-15 复验）。测试覆盖：flask_server/tests/test_bridge_command_routes.py（B-5 交付）。
- 退役方向：旧位 = 抽屉直调 `/api/bridge/run-command` 的 HTTP 入口层；新位 = 标准 tool_call.id（call_<nonce>）执行位（C-12 M3 落点类型：指令类型位→标准 tool_call.id 执行位）。**服务端侧无任何其它调用方需要迁移**，迁移面全部在 extend/ 侧（归 C-7/B-9 侧范围），服务端唯一动作是等待 extend/ 侧迁完后路由本身成为零调用方、按 S4 判定后退役。
- 结论：M3 服务端侧取证完备，当前不可退役（抽屉为活调用方），退役时点归分发方裁定。

### 2.2 external-call 等价替换位（M4）

- 调用方现状：三网关包装层均为活链——qq_gateway.py:331/338/383、wecom_gateway.py:191/343、weixin_gateway.py:122 各自包装成 external-call 卡片投给投递队列；公共解析层 message_parse.py:53/117/126（含嵌套穿透）+ core/envelope.py:23-62（集中解析）+ web_bridge/web_mirror.py:306/379（网页反向投递链）+ core/memory_distill.py:285/317（蒸馏兼容）。
- 替换位方向：旧位 = external-call 信封的 `type` 字段位（三网关各自包装 + 公共层集中解析）；新位 = 标准 tool 消息三键位（C-12 M4 落点类型：包装字段→标准 tool_calls 意图位）。**服务端公共解析层（message_parse/envelope/web_mirror/memory_distill）当前承载 QQ / 微信 / 企微三网关与网页反向投递的真实活链**，旧位当前不可摘除；等价替换位的实装（信封字段→标准三键的转换/拒绝语义）已由 B-9（M6/M7 相关面）与 B-8（M4 面）按方案 A 纯函数层各自承接，服务端活链零改动。
- 结论：M4 取证完备，旧位仍为活链，等价替换位落点已列全（见第三节 M4 行），实装归 B-8/B-9，本笔不预设退役时点。

### 2.3 is_tool_result 迁移结论（M5）

- 调用方现状：构造单点 outbound.py:28/46/109/130（上报统一打标）；消费两点 message_flow.py:219、message_router.py:306（kind=ai 且非工具结果的公共判定）。
- 替换位方向：旧位 = 上报信封的 `is_tool_result` 布尔标记位；新位 = tool 消息 role 位（C-12 M5 落点类型：标记字段→tool 消息 role 位）。迁移语义：`is_tool_result: True` 与 `role: "tool"` 等价、False 与 assistant 判定等价；消费两点的公共判定条件可直接改读标准三键中的 role 键。**构造成单点、消费面两点、无通道专属实现**，迁移是纯服务端侧动作，但迁移时点依赖 extend/ 侧卡片与回执文本先迁到标准键（bridge-chat-res 回执文本归 M2），服务端侧单独迁移会造成判定层新旧并存的双轨期——按 C-10 S2/S3 判据属「待对拍」，不预设结论。
- 结论：M5 运行时仍是活链（构造单点/消费两点均为当前生产判定面），迁移结论为「无通道专属实现、判定语义可等价映射、但依赖 M2 消费侧先行，双轨期处理归分发方裁定」。

### 2.4 G10 / G11 / G12 代码侧结论（随片收口）

| 项 | 代码侧结论（本轮实测） | 遗留归真机/用户侧 |
|---|---|---|
| G10 消息顺序疑似乱序 | push_pipeline.py:247-260 先文后图（send_text :249 → push_media :260）与 :121-122 after_push 锁外补推语音两条结构性事实**仍在代码**，时序日志钩子仍未落（G4 通道名日志已可佐证部分时序但非专用时序日志）。切片顺序是否等于真实时序仍无证据。| 截图与实机复现归用户侧，不代勾
| G11 卡片执行状态异常 | 三处修复均落地：幽灵卡判据 cardMatchesBySig 版本二（05j_card_sig.js，只按工具名+参数）、入池硬门槛 isTreeTail（05l_autoexec.js）、状态文件原子写（bridge_store.py:256-270）。B-6 报告第四节登记的 executedSigs 跨刷新恢复键核对项已由 C-7 实改闭合——05j_card_sig.js 现为标准 call_<nonce> 优先 + 旧 msgId 兼容双查（_executedSig / _markExecutedSig / _restoreExecutedCards 三处键统一，toolCallId 优先、msgId 兜底），版本二已覆盖恢复键构型；登记侧签名诊断日志（:65 「[签名诊断] 登记 sig=」）亦已在码，重判时可直接比对两侧键。| 扩展重载确认与签名匹配失败诊断日志（重判「恢复=0 而签名库>0」时比对登记/查询两侧键）归真机
| G12 企微推送重复 | 原子写已在代码（bridge_store.py:270 os.replace + :256 注释点名 os._exit(0) 强退场景）；补推缓存 set_pending 为内存 dict + 失败撤回占用兜底（push_pipeline.py:_save_pending 整体替换语义），重启后缓存丢失由撤回占用机制自然重试。| /rall 重启后首条真机验证未做，不代勾

> 三项均维持 B-6 取证结论，本轮复验无变化；G10 时序日志钩子按 B-7 任务书原列项「补服务端发送与到达顺序的时序日志钩子」——该动作属实现面代码；按 19:25 拆片与 01:07 方案 A 裁定（活链文件零改动），本笔与 B-8/B-9 纯函数层口径下均未含该钩子，是否仍实装不预设、归分发方裁定。

## 三、协议字段替换位 M1-M8 全量列表（供分发方对拍）

> 格式按 C-10 S3 判据要求：每项含字段路径、旧字段名、新字段名、活调用方状态。
> 对拍基准：C-12 映射清单（extend/lib/standard_chain_replacement_map.md，e9e3844）与 b6 调用方地图。

| 槽位 | 旧位（字段路径 + 旧字段名） | 新位（字段路径 + 新字段名） | 活调用方状态 |
|---|---|---|---|
| M1 bridge-chat-call | 网页消息文本块内 `JSON.type == "bridge-chat-call"`（05f_parse.js 解析、service 侧 chat_completions.py 文档串提及） | assistant 消息 `tool_calls[]`（标准意图位：`tool_calls[].id` = call_<nonce>、`tool_calls[].function.name/arguments`） | 活：05f_parse.js 运行时解析链 + 刷新恢复链绑定（c6 报告：恢复链绑定旧卡片对象、bridge-chat-call 解析结果、bridge-chat-res 回执文本三者）
| M2 bridge-chat-res | 回执文本块内 `JSON.type == "bridge-chat-res"`（message_parse.py:134/144 识别） | tool 消息三键：`role: "tool"` + `tool_call_id`（=call_<nonce>）+ `content` | 活：message_parse.py:144 运行时识别 + 记忆蒸馏消费 + 刷新恢复绑定
| M3 run-command | HTTP 入口 `POST /api/bridge/run-command` 请求体字段（routes/bridge.py:294） | 标准 tool_call.id 执行位：tool_calls 意图经服务端标准管线执行（tool_call_id 配对防重放） | 活：抽屉 01b_bridge.js:400 唯一调用方，三网关零命中
| M4 external-call | 信封 `type: "external-call"` 字段位（三网关包装：qq_gateway.py:383 等） | 标准 tool_calls 意图位（tool_calls[].id + function.name/arguments） | 活：三网关包装 + 公共层解析（message_parse.py:53/117、envelope.py:23-62）+ 网页反向投递（web_mirror.py:306/379）+ 记忆蒸馏（memory_distill.py:285/317）
| M5 is_tool_result | 上报信封 `is_tool_result` 布尔标记位（outbound.py:28/46/109/130 构造） | tool 消息 role 位：`is_tool_result: true ↔ role: "tool"`（message_flow.py:219、message_router.py:306 消费） | 活：构造单点 + 消费两点均为当前生产判定面
| M6 三网关包装 | 三网关各自把消息包装成信封的 `type` 字段位（qq_gateway.py:383、wecom_gateway.py:343 区段、weixin_gateway.py:122） | 标准信封字段位（协议字段退役后的统一信封格式） | 活：三网关均为活链路（b6 地图：三网关 grep 零命中 run-command、通道侧指令走 command_dispatch 独立链路；external-call 包装为真实生产动作）
| M7 公共层解析 | 公共解析层对 `external-call` / `bridge-chat-res` 的 type 识别位（message_parse.py:53/117/134/144、envelope.py:23-62） | 标准 tool_calls / tool 消息三键位（解析层判读标准键而非信封 type） | 活：全链路活——三网关解析 + 网页反向投递 + 记忆蒸馏 + 刷新恢复绑定
| M8 旧标记兼容位 | executedSigs / msgId 兼容双查键（05j_card_sig.js：标准 call_<nonce> 优先、旧 msgId 兜底） | 标准 call_<nonce> 优先键（工具执行签名的唯一键） | 活：C-7 已实改为双查构型，兼容位保留中；摘除待 B-8/B-9 验收+对拍+b 现状说明收口后由分发方另行下发

## 四、无协议字段替换位的面（S4 口径显式声明）

按 C-10 S4 判据要求显式声明：**旧标记摘除面（矩阵 #14 / S4）无协议字段替换位，仅运行时标记**。S4 相关的运行时标记（executedSigs 双查构型、card.msgId 字段等）均属运行时执行权标记，不涉及协议信封字段；其摘除由分发方另行下发，c 侧未自行摘除、本笔也未动任何标记。

## 五、边界与只追加记录

- 范围：本笔只新增本文件与 docs/work-ai-b.md 第五节完成记录，零代码改动、零测试文件改动；未触碰 flask_server / remote_bridge / extend / skills / scripts 下任何源码与配置；未碰 B-8/B-9 文件族；不动 docs/bus 他人消息。
- 依据：19:25 拆片广播 + 19:26:29 致 b 定向通知 + 01:07:37 方案 A 广播 + 09:28:37 B-8 正式裁定（对 b 收口片无影响确认）。
- 判定时点沿用 C-10 S1-S4 / C-12 M1-M8：替换位列全 + 逐片验收合入 + 逐项对拍完毕为齐备；不以本笔提交落地为齐备标志、不预设 B-7 总结论、不代分发方裁定退役时点。
- 遗留真机项不代勾：G10 截图/复现、G11 扩展重载/签名诊断、G12 重启首条。
- docs 只追加：本笔不删改历史台账与总线消息；记录由 send report 追加到 docs/bus/b.md。
