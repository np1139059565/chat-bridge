# 00 · 当前状态与文档总纲（唯一结论源）
【2026-11-18 分发方复核 · 进度以本块为准】
> - 大改（翻译员/工具服务剥离）规格 docs/split-mirror-and-tools-service.md 338 行定稿。实仓已落 main 并经 app.py 注册：/v1/chat/completions、/v1/system_prompt、标准会话历史、/api/voice/tts、/api/clients（routes/clients.py + core/client_registry.py）、投递队列、指令收归；参数声明 JSON Schema 迁移清单 18/20 勾选，read_file.path anyOf 与状态列待复核。[高]
> - 当前首批动作：合并逐笔对拍（23 文件：3 实现 + 19 测试 + tunnel.cmd；逐项清单未落、分母待核）与合并重排走查（R0 / R2 / R3 / R4）同批推进；R1 冻结线转《口径对齐说明》重出与 R3 分片，三方不停车。[高]
> - G-A / G-B / G-C 三笔大改验收顺延到对拍与重排走查收口之后（任务书已下发、未开工、回执 0/3），按规格第七节逐项脚本化复核，回执带 pass/fail 分母，不采信自述。[高]
> - 配置刷新 / yuanbao 识别 / 独立工具配置页 0/3 缺口并入 G-B / G-C 验收面。[中]
> - 真机与人工测试 0%（冻结），待脚本化验收通过后解冻。
> - 方案：合并逐笔对拍与合并重排走查（首） → 大改逐项验收与缺口补齐 → 阶段 3 摘除裁定 → 解冻人工测试。
> - 本块由分发方维护；执行方只改实现，不改结论。跨机器定位只认工程名 chat-bridge + 版本号/commit，路径用工程内相对路径。

> - 快照时间：2026-11-18（分发方接管复核）。在途队列：a = R0 已交付待验收（work/ai-a cc21e23，七道钩子全过、未合入 main，已回 wait 续链）；b = R1 冻结，转口径对齐说明与 R3 分片；c = P1 热修补丁已补发待验收（patch 全文在 docs/bus/c.md）。[高]
> - 并发硬约束（Q2）：分发方维持三方在途队列，任一方交付回监听后下一轮立即续派，不把「完成回监听」用成死等；单笔 ≤1 可验收面、自带实测、按文件归属隔离互不冲突；逐笔独立 worktree 串行验收合入。本轮不下发任务书。[高]
>
> 一切进度结论以本文件为准。当前状态：合并逐笔对拍与合并重排走查为当前首批动作，G-A / G-B / G-C 大改验收顺延其后。

## 一、汇报铁律（写死，不可改）

1. **说人话**：简洁、明确。禁止 root、口径、闭环、赋能、颗粒度这类装词；不绕弯、不铺垫、不写长篇。
2. **每条汇报必须带进度百分比**，格式「事项：X%」。
3. **百分比必须附分母**（如 0/4 阶段、24/24 份）。不许拍脑袋；没查清就写「没查清」，不编数。
4. 先给结论，再给证据，一屏说完。
5. 结论只认本文件；其余文档只记过程，不下「完成」结论。
> 6. **禁写死本机路径**：不写 D:、本机路径略 这类绝对路径，换台电脑就不对。
>    跨机器定位只认「工程名 chat-bridge + 版本号/commit」；工程内相对路径（docs/…、extend/…）可以写，它相对工程根，换机器不变。


## 二、当前进度（百分比 + 分母）

| 事项 | 进度 | 分母 |
|---|---|---|
| 协作文档回退 | 100% | 24/24 份已取回并随本笔提交 |
| 汇报铁律写入 | 100% | 2/2 份（本文件、协作规则） |
| 大改规格定稿 | 100% | 338 行 / 15 条决策 / 4 阶段 |
| 大改接口与注册实仓复核 | 100% | 9/9 关键路由与实现文件在 main 且 app.py 已注册 |
| 参数声明迁移清单勾选 | 90% | 18/20 项（2 项为规则行与 read_file.path 状态列） |
| 大改逐项脚本化验收 | 0%（顺延） | 0/3 笔回执；任务书已下发未开工，待对拍与重排收口（0 合入 / 0 待验收） |
| 合并逐笔对拍与合并重排走查 | 0%（当前首批动作） | 0/23 文件（逐项清单未落，见 docs/清理与冻结候选清单.md 第四节）与 R0 / R2 / R3 / R4 |
| 配置刷新 / yuanbao 识别 / 独立工具配置页 | 0% | 0/3 缺口项并入 G-B / G-C 验收面 |
| 人工测试 | 0%（冻结） | 待脚本化验收通过后解冻 |

> 注（Q8）：表内 0% 一律指「0 笔合入验收」，不等于「三方未动」；在途交付按上方复核块快照单列。本轮不下发任务书。

## 三、大改当前情况

工具服务侧标准接口已在 main 并经 app.py 注册：

| 能力 | 接口 / 落点 |
|---|---|
| 标准对话 | POST /v1/chat/completions（routes/chat_api.py、core/chat_completions.py） |
| 标准提示词 | GET /v1/system_prompt（routes/system_prompt.py） |
| 标准会话历史 | core/chat_completions.py 按 site_key 落盘 |
| 语音合成 | POST /api/voice/tts（routes/voice.py） |
| 客户端注册与配置原样保管 | POST/GET/DELETE /api/clients（routes/clients.py、core/client_registry.py） |
| 通用投递队列 | core/delivery_queue.py |
| 指令收归 | core/command_catalog.py、routes/command_catalog.py |
| 参数声明 | 21 个内置工具为标准 JSON Schema，read_file.path 用 anyOf |

翻译员侧：extend/lib/standard_chain_adapter.js 六段中 execute 已实装（EXECUTE_STATUS = implemented-S2-step5），其余五段为 declared-placeholder；extend/dialog/parts/ 仍承担旧建卡直调路径。

当前动作：合并逐笔对拍 23 个文件与合并重排走查（R0 / R2 / R3 / R4）同批推进，逐笔结论写入 docs/work-board.md 末节；收口后按 docs/split-mirror-and-tools-service.md 第七节逐项脚本化复核 G-A / G-B / G-C，产出 pass/fail 分母与缺口清单，再进入阶段 3 摘除裁定。分发方维持三方在途队列，合入即续派，不让 a / b / c 停车（Q2）。

## 四、合并安排

合并逐笔对拍与合并重排走查为当前首批动作。对拍对象记 23 个文件（3 实现 + 19 测试 + tunnel.cmd）；逐项路径清单尚未落盘，分母待核（Q4，见 docs/清理与冻结候选清单.md 第四节），不得与 R0 的「32 文件×3 树」矩阵混为一张表；清单与逐笔结论由分发方验收后写入 docs/work-board.md 末节。
