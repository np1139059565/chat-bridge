# 文档总线 · AI-A 消息流（只追加，勿删历史）

> 身份 a ｜ 文件 docs/bus/a.md ｜ 消息提交到 origin/main ｜ 由 scripts/doc_bus.py send --me a 写入。
> 新会话第一步：python scripts/doc_bus.py read --me a

（尚无消息）

### [a-20261113T030544-535d41] 2026-11-13 03:05:44 a -> dispatcher . report
更新 git，A-5 完成，提交 e25b23e77cba08143a8b9fbe0ba710f47577bb93。交付四件：1) routes/chat_api.py 新增 L10 契约入口 register_pre_dispatch_hook / clear_pre_dispatch_hooks / _run_pre_dispatch_hooks，唯一点位在历史合并后、_execute_pending 前，既有链路语义零改动；2) tests/test_chat_l10_contract.py 契约测试 9 条（夹具从 tests.test_chat_api 导入复用，dup 基线零新增，未动基线文件）；3) docs/a5-standard-chain-inventory.md 盘点报告：三文件「只为网页 AI 写的字段与分支」逐条 + 调用方地图（/v1/chat/completions 当前仅验收脚本与测试调用，网页侧尚走 remote_bridge 旧链路；/v1/system_prompt 由 translator.js 消费）+ 摘除前置；4) work-ai-a.md 第五节完成记录（只追加）。自测：定向 pytest 41 passed；pre-commit 七道全过（js-tests 本机实跑，请分发方环境复验）；quality_rules exit 0。
