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

### [b-20261115T103533-c6bb66] 2026-11-15 10:35:33 b -> dispatcher . report
B-10 完成，提交 76ebb08（origin/work/ai-b，已 force-with-lease 推送；变基自实时 origin/main df8067a，落后零、领先一，提交点即基点后首笔）。交付物：docs/b10-removal-readiness-report.md（66 行，只读取证）。三件交付：①S1-S4 逐槽就绪度表，每槽含当前态/缺口/触发表更的具体条件/分发方裁定点，S1 区分契约侧已对拍一致与 L10 外部凭证另行排期，S2 写明装配面九步第 5 步仍 declared-placeholder，S3 替换位列全且分发方判一致，S4 运行时执行权未迁移、摘除任务书未下发、九文件顺序表未执行；②c6 九文件摘除顺序表逐行复核，路径存在性/活链状态/调用方/摘除前置/影响面全列；③显式结论五条：旧标记摘除当前不下发、前置未满足，只描述判据不实装、不预设下发时点。范围核对：仅新增 2 文档、零代码零测试改动、未碰 extend/dialog/parts/ 与 remote_bridge/ 活链、未摘除任何标记、未装配运行时 M、docs 只追加。验收实测（2026-11-15 收口轮）：pre-commit 七道逐个 Passed（不 --no-verify）、quality 零[新增]、diff --check rc=0、全量 pytest 1078 passed / 1 failed（既有波动：test_weixin_protocol.py::test_production_cl 环境凭证缺失，收口轮如实标注不掩盖；分发方环境 1079 全绿）、check_js_tests.py rc=0 / 545 pass / 覆盖率达标（分发方环境直跑）。边界声明：未跟踪文件 extend/dialog/AUDIT.md 非本笔产物，未纳入提交未改动。完成后回监听等续派，不自找活、不自填 [答复]。

### [b-20261115T114413-2a04ed] 2026-11-15 11:44:13 b -> dispatcher . report
report [B-11 完成] 提交 537e66fdbb465aaa1185c20a977a1f517ecf2f87（work/ai-b 已推送，基点实时 origin/main cdbcf96）。交付：docs/b11-order-table-reconciliation.md 新增 1 份（68 行）+ docs/work-ai-b.md 第五节只追加（9 行），零代码零测试改动。三件交付：①01c_bridge_cmd.js 宽口径协议标记（bridge-chat-call/res、external-call、run-command、is_tool_result、toolCalls/toolCallId/toolCall、TOOL_RESULT）实测零命中，唯一远程面 /api/bridge/commands 属桥接指令管理面，调用方 dialog.html L42 + 08f_commands.js 四处 UI 调用，夹具仅 test_translator L275-276 文本级 1 份——判「列名、零标记、本轮不可摘」，归并建议登记跳过；②05d_memory.js 仅 2 处注释级命中（L52/L70），运行时真依赖是 05f_parse.msgSource（L390）返回值，自身不构造不解析协议字串，夹具直接+行为级间接引用全零——建议归并步骤 3 分组随 msgSource 语义一并更新；两条建议均仅为分发方复核输入、不代拍板、不改 c6/c7 原文。③九文件影响面夹具清单按 B-10 第三节序逐行落齐：直接夹具数 3/3/1/5/0/6/4/4/2 与 B-10 实测一致；影响集中在 05f（test_parse 类 6 份、msgSource 8 处断言）、05c（信封构造与兜底三项）、05g（建卡/toolCalls/恢复键绑定）、05j（executedSigs 三夹具 18 处、覆盖率门禁敏感）、translator（双向翻译与挂载断言）；01c/05d 两侧零或近零。显式结论：两处口径差异不构成新前置、不触发摘除动作，硬前置沿用 S4 三项与 10:05 广播判态。实测：七道钩子全 Passed 未用 --no-verify；check_js_tests 554/554 rc=0 覆盖率达标（24 项存量欠账基线内无退化与新增）；quality rc=0 零[新增]；diff --check/--cached --check rc=0；全量 pytest 1078 passed / 1 failed，唯一失败 test_weixin_protocol.py::test_production_client_gets_ctx_path（本机凭证缺失类存量波动、与 B-10 同项，单文件复跑 20 passed，非本笔引入，分发方环境复跑为准）。边界：未跟踪 extend/dialog/AUDIT.md 非本任务产物未纳入；不碰活链、不摘除标记、不翻转 declared-placeholder、不动 docs/bus 他人消息、docs 只追加。回监听等验收与续派，不自找活、不自填 [答复]。
