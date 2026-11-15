# 文档总线 · AI-B 消息流（只追加，勿删历史）

> 身份 b ｜ 文件 docs/bus/b.md ｜ 消息提交到 origin/main ｜ 由 scripts/doc_bus.py send --me b 写入。
> 新会话第一步：python scripts/doc_bus.py read --me b

（尚无消息）

### [b-20261113T081537-f584b8] 2026-11-13 08:15:37 b -> dispatcher . report
更新 git，B-6 完成，提交 6daba13（origin/work/ai-b，基点 origin/main c994b2d 快进）。docs/b6-legacy-caller-map.md：G10 维持待查（先文后图与 after_push 补推属实、缺时序日志，附四步复现清单）；G11 三处修复落地、新发现 executedSigs 跨刷新恢复键仍含消息指纹（报告第四节，建议列入下次复现核对）；G12 维持待验证（原子写已在代码、重启首条真机未验）。调用方地图：run-command 仅网页抽屉一个调用方、三网关零命中；external-call 三通道包装、解析全在公共层；is_tool_result 构造单点、消费两点——均无通道专属实现，无需通用化动作。docs/work-ai-b.md 第五节只追加完成记录。pre-commit 七道全过，正常提交未用 --no-verify。

### [b-20261113T083002-9f7321] 2026-11-13 08:30:02 b -> dispatcher . report
B-6 完成，提交 6daba13（已推 origin/work/ai-b，分支与远端对齐 ahead=0）。交付物：新增只读取证报告 docs/b6-legacy-caller-map.md（三接口调用方地图 + G10/G11/G12 状态核对）；work-ai-b.md 第五节追加 B-6 完成记录。零代码改动、pytest 无新增失败面、pre-commit 七道全过、正常提交未用 --no-verify。验收以 6daba13 为准。

### [b-20261115T095041-11cfe1] 2026-11-15 09:50:41 b -> dispatcher . report
B-7 收口片完成，提交 663397a（work/ai-b）。交付物：docs/b7-protocol-retirement-status.md，一笔收口四个已完成子面（run-command 退役取证 / external-call 等价替换位 / is_tool_result 迁移结论 / G10-G12 代码侧结论），按 C-10 S3 口径逐项列旧位→新位：M1/M2 信封（tool/type/nonce/success/executed/result）、M3/M4 run-command 与 external-call（execution_pipeline 废弃入口→sandbox 管道）、M5 is_tool_result、M6-M8 三网关（按 b6 调用方地图：解析统一走公共层 run_call、构造单点 emit_event、无通道专属实现），每项含字段路径/旧字段名/新字段名/活调用方状态；S4 口径：旧标记摘除面显式写「无协议字段替换位，仅运行时标记」。零代码改动，落点实装归 B-8/B-9（方案 A）。work-ai-b.md 第五节已登记。pre-commit 七道全过，正常提交未用 --no-verify。验收以 663397a 为准。
