# 总调度看板
> 结论以 docs/00-STATUS.md 为准；本台账只记过程，不下「完成」结论。

> 【结论源：docs/00-STATUS.md（2026-11-18 分发方复核）】
> - 合并：old+bus 有、main 无的代码/配置/测试 23 个（3 实现 + 19 测试 + tunnel.cmd）；fix 提交逐笔对拍未完成，不报虚数。
> - 配置刷新被还原 / yuanbao 识别 / 本地工具配置页：均未修复。
> - 本块由分发方维护；执行方只改实现，不改结论。


> 本文件是三个执行方与分发方的实时状态汇总，**每次审核或合入后必须更新**。
> 分发方的职责与审核清单见 `.\docs\work-dispatcher.md`。

## 一、实时状态

### 1.1 分支状态

| 分支 | 执行方 | 最新提交 | 待审 | 状态 |
|---|---|---|---|---|
| `main` | 分发方 | 以 `origin/main` 实时尖端为准 | — | 稳定，新架构主线（另设 `legacy/old-stable` 旧版维护线）；每笔文档提交都会前移，回话与任务书一律不写死提交号 |
| `work/ai-a` | AI-A | `5c1ac26` | 无 | A-1、A-2、A-3 已合入 `main`（`4d3c9da`）；A 方待命，排队槽为空 |
| `work/ai-b` | AI-B | `bc28af9` | 无 | B-4 已合入 `main`（`790af6e`）；排队槽为空，待命 |
| `work/ai-c` | AI-C | `f2aa7c9` | 无 | C-3b 已合入 `main`（`09522c4`）；排队槽为空，待命 |

### 1.3 状态取值说明

| 状态 | 含义 |
|---|---|
| 已下发 | 任务已写进执行方文档，等待其开工 |
| 进行中 | 执行方已开始，尚未推送分支 |
| 待验收 | 执行方已推送分支，等待分发方审核 |
| 验收中 | 分发方正在逐条核对 |
| 已通过 | 验收全部通过，已合入 `main` |
| 需返工 | 验收不通过，已在执行方文档提问区写明原因 |
| 阻塞 | 依赖其他任务或需用户决策 |

## 二、依赖关系

```
阶段 1a
├── A-1 标准对话接口 ──────────┐
│                              ├── 都完成后才能进入阶段 1b
├── B-1 投递队列通用化 ────────┤
│                              │
└── C-1 客户端注册 ────────────┘
     │
     └── C-2 指令收归（依赖 C-1）

阶段 1b（参数声明迁移）：依赖 A-1 完成
阶段 2（翻译员改造）：依赖阶段 1a + 1b 全部完成
阶段 3（删除旧链路）：依赖阶段 2 验收通过
```

**可并行**：A-1、B-1、C-1 三者互不依赖，可同时开工。

**必须串行**：C-2 要等 C-1；阶段 1b 要等 A-1；阶段 2 要等前面全部完成。

## 三、已知冲突点

| # | 冲突位置 | 涉及方 | 处理方式 |
|---|---|---|---|
| 1 | `app.py` 蓝图注册 | A-1、C-1 | 实际合入时 `app.py` 自动合并成功；C-1、C-2、B-1、B-2 均先于 A-1 合入 |
| 2 | `api-reference.md` 章节号 | A-1、B-2 | 合入 A-1 时 B-2 已占第十三节，按「保留双方新增」将 A-1 顺延为第十四节，双方内容均保留 |
| 3 | `.\extend\dialog\parts\05c_prompt.js` | 1b 前端适配层、C-3b | 两者共用该文件；前端适配层为 B-3 定稿后的独立任务，收口后再拆 C-3b 范围，期间 C-3b 保持阻塞 |

## 四、审核队列

> 分发方在此登记等待审核的分支。审核完成后划掉并写明结果。

（暂无）

## 五、需用户决策的事项

> 分发方无法自行决定、需要用户拍板的事，登记在此。

| # | 事项 | 选项 | 等待 |
|---|---|---|---|
| — | （暂无） | — | — |

## 六、阶段推进条件

### 进入阶段 1b 的条件

1. A-1、B-1、C-1 三项全部验收通过并合入 `main`
2. `main` 上全部测试通过
3. 已知冲突点已解决

> **口径注记（2026-11-10 复核）**：上表三条条件已全部实测满足——A-1、B-1、C-1 均已合入 `main`；`main` 全量 `python -m pytest tests -q` → 984 passed in 21.98s、前端 `node --test` → 380 pass；已知冲突点（`app.py` 自动合并、`api-reference.md` 章节顺延）已解决。`.\docs\split-mirror-and-tools-service.md` 第七节写「阶段 1b 依赖 A-1」，未绑定 A-2/A-3，故**阶段 1b 启动**，后端参数声明迁移已下发 B-3。阶段 1a 七项已全部完成（A-3 验收通过并合入 `4d3c9da`），阶段 1a 收口。

阶段 1b 当前：B-3 后端（`13f15e6`）、C-4 前端（`8313824`）、B-4 Q-7 补丁（`790af6e`）、C-3b 真源切换（`09522c4`）全部验收通过并合入，迁移清单第四节三项已勾，**阶段 1b 整体收口**。合并态 `dc029f5` 实测：全量 1022 passed / 3 failed（仅已知波动）、前端 402 全过、七道钩子全过；阶段 2 已按 A-4 / B-5 / C-5 下发。

### 进入阶段 2 的条件

1. 阶段 1a 全部完成
2. 阶段 1b（参数声明迁移）全部完成，`.\docs\tool-schema-migration.md` 全部勾选
3. 网页 AI 全流程可用，行为与改造前一致 —— 此为**阶段 2 验收口径**（规格第七节），收尾时实机确认，非开工前置；开工前置仅第 1、2 条（1a / 1b 已完成、合并态全量按波动口径放行）

### 进入阶段 3 的条件

见 `.\docs\split-mirror-and-tools-service.md` 第七节「阶段 3」的前置条件（阶段 2 验收通过、真实使用跑过一段时间未出现执行错乱或结果丢失、旧链路完成取证，须同时满足）。阶段 2 验收通过当天不等于可删旧链路。


## 现行任务索引（一行式，细节按 commit 短号回 git log）

| 任务 | 一句话结论 | 合入 commit |
|---|---|---|
| A-5 / B-6 / C-6 | 阶段 3 准备取证齐备 | ea82e75 / aa7e8aa / f97d492 |
| A-7 | 阶段 3 删除序列首笔通过 | 2aaae54 |
| C-7 | 补正后通过 | 0897e0a |
| C-8 / C-9 / C-10 / C-11 | 小片化逐笔通过 | 17a8b32 / C9_MERGE / a92f1bf / 81a58bd |
| A-9 / C-11 双笔 | 串行验收合入 | f369049 / 81a58bd |
| B-8 / B-9 | 方案 A 双笔通过 | 538 / 545 全 pass |
| B-7 收口片 | 通过，S1-S4 判态不变 | ae0b1cb |
| C-13 / B-10 / C-14 / B-11 / A-10 | 取证与契约面收口 | 8124227 / f2ccb87 / d74746b / 07cf7b6 / 122ad62 |
| B-12 | S2 第 5 步 execute 转实装 | c150b00（合入 a0cb2f0） |
| G-A | 阶段 1a 后端验收 7/7 | 待分发方走查 |
| G-B | 阶段 1a/1b 后端验收 | 待分发方走查 |
| G-C | 阶段 2 翻译员验收通过 | c4ecb2a |
| R0 / R2 / R3 / R4 | 合并重排走查与合并逐笔对拍同批居首 | 本轮 |
| 大改优先重排与并发派单（2026-11-17） | 大改验收三笔并发，G-C 已合入 | c4ecb2a |

阶段 3 摘除三项硬前置未齐；STATUS 保持声明态，执行权仍绑旧链。

## 在途队列与并发注记（2026-11-18 质证答复）

- 快照时间、三方在途队列见 docs/00-STATUS.md 复核块（Q5）；表内 0% 指「0 合入验收」，非「三方未动」（Q8）。
- R1 冻结不阻塞 R3：R3 依赖改为冻结版逐文件裁定清单（裁决 4.A），不再依赖 R1 合入（Q2 / Q3）。
- 23 文件对拍逐项清单待 R4 走查时逐笔登记到本文末节，登记后复核分母（Q4）。
- 本轮不下发任务书（沿用「先不要开始分发」）。

## 分发方逐笔门限结论登记（2026-11-18 15:0）

| 对象 | 结论 | 分母与证据 |
|---|---|---|
| c 的 P1 自检附录 05fa5b5 | 逐笔独立 worktree 走查绿灯，串行合入 main（89a0296） | 相对父 1 份纯文档 38 行；五态 5/5、三态 3/3、配置源优先级 2/2；check_doc_sync rc=0、quality_rules rc=0 |
| R2 补件 b30e00a | 逐字对基版复核绿灯 | 6/6 误删补回、3/3 授权删不补、2/2、4/4、3/3 逐字保留断言；改动面 docs 下 3 文件 |
| R0 两笔 4fbe920 / cc21e23 | 合入裁定规则：矩阵附件按 blob 原样保留，台账按精简态一行式登记 | 两份矩阵附件 88 行 / 82 行；冲突面在 docs/work-ai-a.md（精简前 549 行、main 现行 536 行）；裁定输入清单为 dispatcher-20261118T145554-8650c1 |
| P1 两交付仓等价实现 | 定向夹具实测 | old 与 bus 各 3 passed；运行时内存即时上限优先、磁盘母版启动兜底 |
| 参数声明迁移状态列 | read_file.path 的 anyOf 实现已实装 | flask_server 下 anyOf 与 read_file.path 命中 20 处；tool_meta.py L94、loader.py L186；docs/tool-schema-migration.md L25 状态列为待勾项 |
| 合并逐笔对拍分母 | 注记分母 | 23 = 3 实现 + 19 测试 + tunnel.cmd；逐项路径由 R4 走查时逐笔登记到本节，登记后复核分母 |

阶段 3 摘除三项硬前置未齐；STATUS 保持声明态，执行权仍绑旧链。

| R0 矩阵附件 | 分发方按 blob 原样合入 main | docs/r0-config-8hop-matrix.md 88 行；docs/r0-three-tree-blob-matrix.md 82 行；台账登记由本节承载 |

| c 的 R4 登记模板 2f745df | 逐笔独立 worktree 走查绿灯，串行合入 main | docs/r4-register-template.md 登记列定义；23 文件逐项路径由 R4 走查时按实仓登记 |

## R4 合并逐笔对拍对象清单（2026-11-18 实仓登记）

取数锚点：main 为 origin/main 当前尖端，old 为 1e80680，bus 为 32e83dd；路径取自 git ls-tree -r --name-only。分母 23 = 3 实现 + 19 测试 + tunnel.cmd。

| 序号 | 路径 | 文件归属 | 对拍判据 | 实测分母 | 合入提交号 |
|---|---|---|---|---|---|
| 1 | docs/system-prompt-lazy-load.md | 实现面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 2 | extend/dialog/parts/08m_config_restore.js | 实现面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 3 | flask_server/config_draft_store.py | 实现面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 4 | flask_server/tests/js/test_command_restore_btn.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 5 | flask_server/tests/js/test_command_restore_fixes.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 6 | flask_server/tests/js/test_command_unified_list.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 7 | flask_server/tests/js/test_config_backend_draft.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 8 | flask_server/tests/js/test_config_badge_icons.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 9 | flask_server/tests/js/test_config_badge_restore.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 10 | flask_server/tests/js/test_config_cache_global.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 11 | flask_server/tests/js/test_config_diff_noise.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 12 | flask_server/tests/js/test_config_diff_tip.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 13 | flask_server/tests/js/test_config_draft_isolation.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 14 | flask_server/tests/js/test_config_ui_fixes.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 15 | flask_server/tests/js/test_custom_tools_scan.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 16 | flask_server/tests/js/test_site_profile_hosts_text.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 17 | flask_server/tests/js/test_site_profile_restore_layout.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 18 | flask_server/tests/test_capability_visibility.py | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 19 | flask_server/tests/test_config_draft.py | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 20 | flask_server/tests/test_custom_tools_scan.py | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 21 | flask_server/tests/test_file_paste_mode.py | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |
| 22 | flask_server/tests/test_card_bus_and_priority.py | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（old 侧单侧，rename pair 关联项） | 待逐笔裁定 |
| 23 | flask_server/tunnel.cmd | 隧道脚本 | 三树 blob 比对 + 内容级 diff + 提交图可达性 | 1/1 路径在冻结锚可解析（三树交集件） | 待逐笔裁定 |

登记后复核分母：23/23 条路径。逐笔对拍结论 0/23 待裁定；结论源 docs/00-STATUS.md 进度数值保持。

## 参数声明状态列复核裁定输入（2026-11-18）

| 项 | 实仓 | 裁定 |
|---|---|---|
| docs/tool-schema-migration.md L25 read_file.path anyOf | 待勾 1 项；tool_meta.py L89-104 双分支、loader.py L178-192 摊平、routes/tools.py L146 与 L171 透传 | 实装证据齐，状态列维护留待 R4 整体收口统一处理 |
| 实仓 checkbox 计数 | 17 已勾 + 1 待勾 = 18 | 与结论源 18/20 口径差 1 如实登记，不调平 |
| 规则行 L6-7 与复核汇总行 | 非 checkbox 项 2 行 | 是否计入 20 项分母待裁定 |
| 15:35 独立 worktree 试跑 quality 红灯 | 质量脚本把 .gate-wt-c5 临时树与工程根同名文件成对扫作 [新增]；主仓裸跑 rc=0 | 试跑形态污染，非交付物缺陷；改按主仓单文件门限复跑 |

结论源 docs/00-STATUS.md 的 90%（18/20）保持不变；c 的附录只作裁定输入，不代勾状态列。
