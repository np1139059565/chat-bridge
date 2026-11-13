# 文档总线 · AI-A 消息流（只追加，勿删历史）

> 身份 a ｜ 文件 docs/bus/a.md ｜ 消息提交到 origin/main ｜ 由 scripts/doc_bus.py send --me a 写入。
> 新会话第一步：python scripts/doc_bus.py read --me a

（尚无消息）

### [a-20261113T030544-535d41] 2026-11-13 03:05:44 a -> dispatcher . report
更新 git，A-5 完成，提交 e25b23e77cba08143a8b9fbe0ba710f47577bb93。交付四件：1) routes/chat_api.py 新增 L10 契约入口 register_pre_dispatch_hook / clear_pre_dispatch_hooks / _run_pre_dispatch_hooks，唯一点位在历史合并后、_execute_pending 前，既有链路语义零改动；2) tests/test_chat_l10_contract.py 契约测试 9 条（夹具从 tests.test_chat_api 导入复用，dup 基线零新增，未动基线文件）；3) docs/a5-standard-chain-inventory.md 盘点报告：三文件「只为网页 AI 写的字段与分支」逐条 + 调用方地图（/v1/chat/completions 当前仅验收脚本与测试调用，网页侧尚走 remote_bridge 旧链路；/v1/system_prompt 由 translator.js 消费）+ 摘除前置；4) work-ai-a.md 第五节完成记录（只追加）。自测：定向 pytest 41 passed；pre-commit 七道全过（js-tests 本机实跑，请分发方环境复验）；quality_rules exit 0。

### [a-20261114T002340-6bd238] 2026-11-14 00:23:40 a -> dispatcher . report
更新 git，A-7 完成，提交 6b2be25c7a19fc40be6a6187453db78fabaa929c（一次提交，61b8adf→6b2be25 为 amend 收口后 force-with-lease 更新）。交付四件：1) core/chat_completions.py 新增 model_reply_hook(fetch_model_reply) 工厂 + _as_assistant_reply 规范化辅助——「history 送真实模型」包装为 L10 可注册钩子，fetcher 返回 None/str/dict（dict 为 assistant 轮，可带 tool_calls，模型声明的调用意图交服务端标准管线执行），回复经 _normalize_item 规范化追加，分发/落盘/响应 messages 三步一致，违约或 fetcher 异常上抛且无部分副作用；本模块不做网络请求、不读凭证，代码侧只到入口。2) routes/chat_api.py 仅补装配指引注释，链路本体零改动。3) tests/test_chat_l10_contract.py 追加契约 9-17 共 9 条（None 不代签 / str 回复落盘回声 / fetcher 见合并后完整历史 / tool_calls 进执行管线 / 两轮循环闭合 / 网页附加字段随规范化清洗 / 违约 TypeError / 异常上抛无副作用 / 用例间不泄漏）。4) docs/work-ai-a.md 完成记录 + 逐项判定三项：_sanitize_tool_calls 保留为防御（复验 translator.js L124-133 toToolCalls 只发标准 tool_calls，清洗当前无实际丢弃对象，但 POST body 可直写 history 不受信，唯一入口防篡改层不动）；_build_response 的 messages/site_key 扩展字段不可摘（决策 14 明文设计，摘除需分发方修订决策并下发，本笔只出评估）；_response_to_body 管线兼容与 system_prompt 四段式保留不纳入摘除。自测：定向三文件 50 passed；全量 1073 passed；check_chat_api.py 六场景 PASS；quality_rules 无新增违规（model_reply_hook 初版 39 行触发 pyfunc，拆出 _as_assistant_reply 后 23/20 行归零，未动基线）；pre-commit 七道全过。完成后回监听，不自找活。
