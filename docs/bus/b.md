# 文档总线 · AI-B 消息流（只追加，勿删历史）

> 身份 b ｜ 文件 docs/bus/b.md ｜ 消息提交到 origin/main ｜ 由 scripts/doc_bus.py send --me b 写入。
> 新会话第一步：python scripts/doc_bus.py read --me b

（尚无消息）

### [b-20261113T081537-f584b8] 2026-11-13 08:15:37 b -> dispatcher . report
更新 git，B-6 完成，提交 6daba13（origin/work/ai-b，基点 origin/main c994b2d 快进）。docs/b6-legacy-caller-map.md：G10 维持待查（先文后图与 after_push 补推属实、缺时序日志，附四步复现清单）；G11 三处修复落地、新发现 executedSigs 跨刷新恢复键仍含消息指纹（报告第四节，建议列入下次复现核对）；G12 维持待验证（原子写已在代码、重启首条真机未验）。调用方地图：run-command 仅网页抽屉一个调用方、三网关零命中；external-call 三通道包装、解析全在公共层；is_tool_result 构造单点、消费两点——均无通道专属实现，无需通用化动作。docs/work-ai-b.md 第五节只追加完成记录。pre-commit 七道全过，正常提交未用 --no-verify。
