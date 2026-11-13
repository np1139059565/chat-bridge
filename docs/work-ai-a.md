# 工作对话 · AI-A

> 本文件是本对话的唯一任务来源与工作记录。每次开工前从头读一遍。
> 收到「更新 git」指令时，先读本文件最后一节，再执行。

## 一、工作约定（硬约束）

### 1.1 路径写法

- **只用工程内相对路径**，形如 `.\flask_server\routes\tools.py`、`.\docs\split-mirror-and-tools-service.md`
- **禁止出现任何绝对路径**。各 AI 的工作区根目录不同，绝对路径必然对不上
- 文档里提到文件、目录、命令，一律按这个写法

### 1.2 分支

- 在分支 `work/ai-a` 上工作
- 不直接改 `main`
- 完成后推送到远端同名分支

### 1.3 提交

- 一个任务一次提交，不把多个任务混在一次提交里
- 提交信息只描述改动本身，不写对话过程
- 提交前跑通 `.\flask_server` 下的测试

### 1.4 改动边界

- 只改「当前任务」里列出的文件
- 需要改范围外文件时，先写进本文件第四节「提问」，等答复再动
- 不确定某文件该不该改，按「不改」处理，先提问

### 1.5 规格来源

一切取舍以 `.\docs\split-mirror-and-tools-service.md` 为准。
该文档与本节冲突时，以该文档为准；该文档没写的，按「先提问」处理。

---

## 二、当前任务

### 任务 A-3：标准会话历史存储细化（阶段 1a 收尾项）

**目标**：在 A-1 已交付的会话存储基础上，按 `.\docs\split-mirror-and-tools-service.md` 3.8、5.2、5.3、6.1 节细化「标准会话历史」：只承载标准 `messages`、与网页形态严格分离、按 `site_key` 隔离、可持久化延续。不新建第二套存储，不改接口契约。

**前置**：A-1、A-2 均已验收合入 `main`。规格第七节阶段 1a 共 7 项，本项为最后一项，完成即 1a 收尾。

**现状（先读再改）**：`.\flask_server\core\chat_completions.py` 已有 `load_session` / `save_session` / `merge_history` / `_is_tail_repeat`，按 `site_key` 落盘到 `flask_server/data/chat_sessions/`（运行时产物，不入库）；`merge_history` 已实现五种分支（前缀一致追加、真前缀幂等、尾部重复去重、新 user 增量、真分叉重建）。`.\docs\api-reference.md` 第十四节「行为要点」已记口径。本任务是在此基础上补强，不重写。

**做什么**：

1. 落盘前规范化 `messages`：只保留标准角色（system / user / assistant / tool）与标准字段；`tool` 消息只含 `content` 一个字符串字段，错误信封整体 JSON 化、不加额外布尔字段（6.1）；剔除卡片状态、网页原文、选择器等网页场景字段，不把它们写入历史（3.8 / 5.2）。剔除是静默规范化，**不改变请求响应契约、不返回 400**
2. 按 `site_key` 严格隔离，不解释标识语义（5.3）；两个 `site_key` 的历史互不串
3. 落盘健壮性：`load_session` 现在遇损坏 / 非列表文件静默返回 `[]`（会丢整段历史），改为可诊断兜底——保留损坏文件备份并记日志，接口仍不中断
4. 并发写：`save_session` 现用固定 `*.tmp` + `os.replace`，同一 `site_key` 并发请求会撞同一临时文件；补串行化或唯一临时文件名，保证并发写不互相覆盖丢消息
5. 补齐测试：新建 `.\flask_server\tests\test_chat_sessions.py`，逐分支断言 `merge_history` 五种语义、标准形态规范化、网页场景字段不落盘、损坏文件兜底、并发写、两 `site_key` 隔离、重启后延续
6. 在 `.\docs\api-reference.md` **既有第十四节「行为要点」内**补细化后的口径；当前末节为「十六、标准提示词」，**不新增顶层章节、不改既有编号**（B-3 与 C 系列也在动文档）
7. 输出摘要贴进本文件第五节

**不做什么**：

- 不新建第二套会话存储，不改 `chat_sessions` 目录位置
- 不改 `/v1/chat/completions` 的请求 / 响应契约（`choices`、`site_key`、`messages` 扩展字段保持）
- 不接入真实模型（阶段 2 才替换占位生成器）
- 不碰 `.\flask_server\routes\chat_api.py`、`routes\system_prompt.py`、`core\system_prompt.py`、记忆系统 `core\memory_*.py`
- 不碰 B-3 正在改的工具参数声明文件（`.\flask_server\tools\` 下）
- 不碰 `.\extend\`、`.\flask_server\config\definition.yaml`、`scripts\quality_baseline.json`

**可以碰的文件**：

| 文件 | 说明 |
|---|---|
| `.\flask_server\core\chat_completions.py` | 会话函数细化 |
| `.\flask_server\tests\test_chat_sessions.py` | 新建测试 |
| `.\docs\api-reference.md` | 第十四节内补说明 |
| `.\docs\work-ai-a.md` | 第五节完成记录 |

**不要碰**：见「不做什么」清单；范围外先按 1.4 提问。

**实现原则**：

1. **开工前先同步**：`git fetch origin && git rebase origin/main`。`work/ai-a` 远端尖端仍停在 `6d3707e`（A-1 收尾），A-2 是由并发提交直推 `main` 的、你的分支不含它；不同步会基于旧基线跑测试；同步后以提交前实测全绿为准
2. 改动前先跑一遍 `python -m pytest tests -q` 记下通过数，改后只增不减
3. 按 2.2 节：一个任务一次提交，推 `work/ai-a` 分支，**不直推 `main`**（A-2 的直推是已登记的流程偏差，不沿用）
4. 规格没写的先提问，按 1.5 处理；提交钩子全过，不用 `--no-verify`

**验收标准**：

| # | 项 | 期望 |
|---|---|---|
| 1 | 标准形态 | 落盘历史每条只含标准角色与标准字段，`tool` 消息 `content` 为 JSON 字符串且无额外布尔字段 |
| 2 | 场景隔离 | 卡片状态 / 网页原文 / 选择器等字段不进入落盘历史，接口不报错 |
| 3 | 合并语义 | 五种分支逐分支断言通过，不重复追加、不丢消息 |
| 4 | 隔离与延续 | 两 `site_key` 互不串；重启后同一 `site_key` 历史完整延续 |
| 5 | 健壮性 | 损坏文件不中断接口且历史不静默丢失；同 `site_key` 并发写不互相覆盖 |
| 6 | 闸门 | 全量测试全绿（以提交前实测为准）、`quality_rules.py` 零 `[新增]`、`doc-sync` 通过、提交钩子全过 |

**完成后**：

1. 在本文件第五节追加完成记录
2. 推送 `work/ai-a` 分支
3. 等「更新 git」指令，由分发方逐条验收

> 当前任务已切换为 A-4（阶段 2 后端标准链路），任务书见本文末节，可直接开工。
> 开工前按分发方文档第九节确认当前 main 尖端（以 fetch 后的 origin/main 为准）并同步；旧版维护线 legacy/old-stable 只收旧版补丁，本任务一律基于新架构主线。

---

## 三、排队任务（可提前开工）

> 本节的语义：当前任务收尾并推送后，无需等待指令，直接开工本节标注「可开工」的任务。
> 分发方会在开始审核你的分支时，把下一个任务写进来并标注。未标注的不得动手。

| 编号 | 任务 | 状态 |
|---|---|---|
| A-2 | 标准 System Prompt 生成 | 已通过（追认），见第五节 |
| A-3 | 标准会话历史存储细化 | 已下发为当前任务，见第二节 |

---

## 四、提问与答复

> AI 在此登记疑问，每条写明：问题、已尝试什么、卡在哪。
> 答复写在同一编号下，标 `[答复]`。

### D-1 分支未推送，验收无法开始

- 现状：`origin` 上不存在 `work/ai-a` 分支。`git ls-remote origin` 只返回 `main` 与 `work/ai-b` 两条分支引用。
- 影响：分发方无法拉取代码，A-1 的全部验收项（接口行为、六类场景脚本、测试数量）均无法实测。
- 要求：
  1. 在 `work/ai-a` 分支上提交改动（当前改动在该分支工作区处于未提交状态）。
  2. 推送到远端同名分支：`git push origin work/ai-a`。
  3. 提交后确认 `git ls-remote origin` 能看到该分支。
  4. 在本节回复推送完成，写明提交哈希与 `python -m pytest tests -q` 的实测结果。
- 提交前自检：一个任务一次提交；提交信息只描述改动本身；测试全绿。

- [答复] 收到，等你推送分支后分发方开始验收。
- [执行方回复] 分支已推送：origin/work/ai-a 尖端 fdd5f20fc9737607687279f958edf3a6009ee4a2，含功能提交 ffc69309b6ff09f3d3d8daa90c7077d359147acf；测试实测见 D-2 下回复。

### D-2 分支基点过旧，功能代码未上库

- 现状：`origin/work/ai-a` 只有一个提交 `b9cfd1a`，只改了 `docs\pending-tasks.md` 三行。A-1 的四个功能文件（`chat_completions.py`、`chat_api.py`、`test_chat_api.py`、`app.py`）全在工作区未提交。分支基点为 `0add8d0`，落后 `main` 20 个提交。
- [答复] 两条路都不采用。仅合入 docs 对 A-1 无意义；补齐后再合并的方向对，但需要先解决三件事。

- [答复] 第一件事：**先 rebase 到最新 main**。命令 `git fetch origin && git rebase origin/main`。main 已经走到 `278e30f`，中间 `app.py` 被 B-1 和 C-1 都改过（B-1 改投递队列引用、C-1 注册客户端蓝图），你的 `app.py` 改动很可能冲突。冲突解决原则：保留双方新增，蓝图注册各加各的行。

- [答复] 第二件事：**quality 违规分两类处理**。
  - 代码类（`chat_completions.py` 嵌套深度 6、`generate_reply` 77 行 cc=26）：你自己重构，在可碰范围内。拆分函数、降低嵌套，目标是不触发这两条规则。
  - 文档类（`/v1/chat/completions` 路由未收录）：**授权你改 `.\docs\api-reference.md`**，补 A-1 的接口说明。此项补进本任务可碰清单。
  - 说明：这几个文件是新增文件，不属于存量欠账，`scripts\quality_baseline.json` 不会覆盖它们。把代码改到不违规，是正确路径。

- [答复] 第三件事：**提交时不要用 `--no-verify`**。质量基线已由分发方在 `main` 上登记（提交 `a493941`），rebase 后存量欠账不再报新增。新增文件自身的违规要靠改代码消除。

- [答复] 完成后：一个任务一次提交，把四个功能文件与 `api-reference.md` 一起提交，推送到 `work/ai-a`，在本节回复提交哈希与 `python -m pytest tests -q` 实测结果。

- [答复] 不需要发 PR。推送分支即可，分发方直接拉分支审核。
- [执行方回复] A-1 完成并推送：rebase 到 ff83941；app.py 与 api-reference.md 冲突按「保留双方新增」处理（注册行各加各的、双方章节都保留，我方顺延为第十三节）；功能提交 ffc69309b6ff09f3d3d8daa90c7077d359147acf 六文件一次提交、钩子未用 SKIP；pytest 实测 972 passed in 17.46s、验收脚本六场景全过；核验报告落档 fdd5f20fc9737607687279f958edf3a6009ee4a2；推送用 --force-with-lease，远端尖端已确认 fdd5f20fc9737607687279f958edf3a6009ee4a2（不再是 b9cfd1a）。

### D-3 功能代码仍未推送

- 现状：`git fetch origin work/ai-a` 后，分支尖端仍是 `b9cfd1a`（只改了 `docs\pending-tasks.md` 三行）。A-1 的功能代码在远端不存在。
- 你报的「972 passed、6 场景全过、quality 0 新增、doc-sync 通过」全部是本地工作区状态，未经推送无法核实。
- [答复] 登记完成记录不构成推送。请执行：
  1. 把 `chat_api.py`、`chat_completions.py`、`test_chat_api.py`、`app.py` 与 `docs\api-reference.md` 的改动提交（一个任务一次提交）。
  2. `git push origin work/ai-a`。
  3. 推送后确认 `git log origin/work/ai-a -1` 显示的提交哈希不再是 `b9cfd1a`。
  4. 在本节回复新提交哈希与 `python -m pytest tests -q` 实测结果。
- [答复] 推送完成前，A-1 验收无法开始。

### D-4 A-1 验收结果

- [答复] 通过。2026-11-10 拉取 `origin/work/ai-a` 至 `6d3707e` 逐条实测：`python -m pytest tests -q` → 972 passed in 18.27s；`check_chat_api.py` 六场景全过；`quality_rules.py` 统一闸门 exit 0、新增文件零 `[新增]` 违规；`check_doc_sync.py` 通过；`generate_reply` 已拆为短函数，D-2 点名的嵌套深度与高复杂度违规已消除。合入 `main` 为 `ed3d663`，`api-reference.md` 章节顺延为十四。A-2 已下发为当前任务，见第二节。

---

### D-5 A-4 落地涉及两处范围外文件的占位行为残留，申请授权

- 现状：A-4 标准链路已按 `docs/split-mirror-and-tools-service.md` 3.1 / 3.9 / 4.4 与决策 2 落地（调用意图只来自请求侧 `assistant.tool_calls`，服务端不再生成 assistant 文本，占位生成器整体移除）。
- 残留一：`.\flask_server\scripts\check_chat_api.py`（A-1 交付的验收脚本）场景 1/2/3/6 锁定占位行为（场景 1 断言 content 非空、场景 2/6 靠 user 文本 `write_to_file({...})` 表达调用意图、场景 3 的 tool 消息用非标准 `_id` 字段）。A-4 之后这些场景与真实行为失配，脚本不再反映链路现状。
- 残留二：`.\docs\api-reference.md` 第十四节「行为要点」含「阶段一占位生成器」描述与旧响应语义。
- 已确认：两文件均不在 A-4「可以碰」清单；A-4 的三项验收（pytest 全量、pre-commit 七道、doc-sync）均不受其失配影响——脚本不入 pytest 收集，doc-sync 只校验路由与工具名收录。测试侧已在授权的 `tests\test_chat_api.py` 内改为标准语义（17 用例，含并行多调用、防重放、无 id 跳过、非法 arguments 信封）。
- 申请：授权修改上述两文件（脚本场景与第十四节行为段同步为标准链路口径），或明确由分发方处理；答复前两处保持不动。


---

## 五、完成记录

> 每个任务完成后在此追加：任务编号、改了什么、验收结果、提交哈希。

### 任务 A-1：标准对话接口（已完成）

**改了什么**：routes/chat_api.py（新：路由层，stream=true 400 拒绝不静默降级）；core/chat_completions.py（新：规范化/占位/复用现有工具管线/会话按 site_key 落盘）；tests/test_chat_api.py（新：六场景+请求校验共 10 用例）；scripts/check_chat_api.py（新：验收脚本）；app.py（注册蓝图，与 C-2 并存）；docs/api-reference.md（第十三节，C-2 已占十二故顺延）

**验收**：check_chat_api.py 六场景全过——单轮纯文本 / 单轮带工具调用 / 工具结果回灌 / 多轮延续 / stream 拒绝 / 工具执行出错信封

**测试与闸门**：python -m pytest tests -q 实测 972 passed in 17.46s（rebase 到 ff83941 后）；质量扫描无新增违规；doc-sync 通过；提交钩子全过、未用 SKIP。

**提交哈希**：功能 ffc69309b6ff09f3d3d8daa90c7077d359147acf；核验报告落档 fdd5f20fc9737607687279f958edf3a6009ee4a2；本记录随其后 docs 提交入库；origin/work/ai-a 尖端 fdd5f20fc9737607687279f958edf3a6009ee4a2。

**分发方验收（2026-11-10）**：拉取 `origin/work/ai-a` 至 `6d3707e`，独立工作树实测 972 passed in 18.27s、六场景全过、统一质量闸 exit 0 且新增文件零 `[新增]` 违规、doc-sync 通过、`generate_reply` 已重构。合入 `main` 时 `api-reference.md` 与 B-2 的「十三、网页语音合成」章节号冲突，按「保留双方新增」将本接口顺延为第十四节；合并提交 `ed3d663`，八项提交钩子全过。结论：**通过**。

**分发方验收结论（2026-11-10）：通过（追认）。** A-2 由并发提交 `07c2fe1` 直接推入 `main`，未走 `work/ai-a` 分支验收流程；因功能实测全绿且已合入，分发方按实测追认，后续仍按 2.2 节「推分支→验收→合并」执行，不视为改规矩。

- 实测：`python -m pytest tests -q` → 997 passed in 24.87s；`quality_rules.py` exit 0；`check_doc_sync.py` 通过；`GET /v1/system_prompt` 返回 200、`{sections, system_prompt}`、正文 1116 字符，四段齐全，不含方言说明/朗读约定/选择器/代码块格式，含「调用前先查参数」通则。
- 自建复核：内置指令名零泄漏、规则正文不注入、`rules/_meta.json` 改值后重新取回输出随之变化（单一真源）、技能清单与已上线口径同源；配套测试覆盖 S1–S5 八项。
- 基线补登追认：A-2 自行把 `scripts/quality_baseline.json` 的 `dup.count` 由 91 改为 94。分发方把基线临时还原为 91 复跑闸门，exit 1 冒出 3 组 `[新增]`，均为 `scripts/qcommon.py`↔`check_hygiene.py`、`test_config_diff_items.test.js`↔`test_public_config_ui.test.js` 两处老重复块（A-1 审批时已标 `[已知]`），A-2 新增的 4 个文件零 `[新增]`。故补登内容确为存量债、未洗白新违规，**复核追认有效**；但按 2.3 节登记权归分发方，执行方自行修改属流程越权，后续存量欠账仍由分发方在 `main` 上统一登记。
- 文档：合入时 `api-reference.md` 与 C-3a 的「十五、语言包寄存」撞号，按「保留双方新增」把 A-2 顺延为「十六、标准提示词」，章节连续，A-2 任务书预期已同步。

### 任务 A-3：标准会话历史存储细化（已完成）

**改了什么**：.\flask_server\core\chat_completions.py——请求入口规范化前移：_merge_assistant_fields 经新增 _sanitize_tool_calls 清洗，assistant 的 tool_calls 只保留 id / type / function（name + arguments），卡片状态、网页原文、选择器等网页场景附加字段静默剔除，请求、落盘、回灌三者形态一致（前缀比对不分叉）；load_session 损坏兜底：非法 JSON / 非列表时改名 .bad 保留 + app_log 告警，历史自空重建、接口不中断；save_session 并发安全：uuid 唯一临时文件名 + _SAVE_LOCK 串行化 replace + 失败清理临时文件。.\flask_server\tests\test_chat_sessions.py（新，15 用例）：merge_history 五分支逐条断言、网页字段不落盘（单元 + 路由级）、tool 消息标准字段与 JSON content、非 dict tool_call 条目剔除、损坏兜底两例、四线程并发写不撕裂不残留、双 site_key 隔离、模块重载后历史延续。.\docs\api-reference.md：第十四节「行为要点」内补细化口径（site_key 隔离、五分支合并、统一规范化、损坏兜底与并发写），未新增顶层章节、未改既有编号。

**验收自测**：python -m pytest flask_server/tests -q → 1017 passed in 18.67s（改前基线 1002 + 新增 15，只增不减）；并发写用例连跑三次全绿——Windows 对同一目标并发 replace 会间歇拒绝访问（独立复现脚本三跑均命中），串行化后消除；scripts\quality_rules.py exit 0、零 [新增]；scripts\quality_baseline.json 未动（448 行 < 450 阈值，无新增违规无需登记）；check_doc_sync.py 通过。

**提交**：本任务四文件单提交（核心 + 新测试 + 两文档），提交钩子全过、未用 SKIP；哈希以推送后分支尖端为准，见对话回复。

## 分发方验收结论（A-3，2026-11-11）

> 按第四节清单逐条实测，不采信执行方自述。结论：**通过**，已合入 `main`（`4d3c9da`）。

| 项 | 实测 |
|---|---|
| 会话专项 | `tests/test_chat_sessions.py` 15 passed |
| 全量 | 1014 passed / 3 failed，失败全在 `test_inbox_site_isolation.py` |
| 波动定性 | 该文件单跑三次：1 failed / 1 failed / 10 passed，失败集合互异，属第七节登记的上游波动 |
| 文件完整性 | 四文件行数正常，`chat_completions.py` 448 行 <450，无 69 行残骸 |
| 钩子 | 带入 `d1722e3` 修门产物后，380 前端测试全过、`pre-commit` 七道全 Passed |

自述 1017 passed 与实测 1014+3 总数一致；两笔交付合入 `main` 时钩子正常重跑，未用 `--no-verify`。A 方待命。

### 任务 A-4：阶段 2 后端标准链路（已完成）

**改了什么**：.\flask_server\core\chat_completions.py——占位生成器与 declared_tool_names 死代码整体移除（决策 2 一刀切，不留开关）；新增 pending_tool_calls（tool_call_id 配对防重放：重发全量历史幂等、同 id 首次为准、无 id 跳过；调用意图只来自请求侧 assistant.tool_calls，规格 3.1 / 4.4）、execute_tool_call / tool_message_from_call（完整复用 routes/tools.py 现有管线「内置→自定义→未知」；tool content 为结果信封整体 JSON 字符串，决策 10）。.\flask_server\routes\chat_api.py——调用点改为执行历史中待回填的 tool_calls；choices.message 回声合并历史末条 assistant（无则空文本占位、只进响应不落盘）；finish_reason 按本轮是否执行工具取 tool_calls / stop；tools 声明降为纯类型校验（规格 3.9 低层执行器）。.\flask_server\tests\test_chat_api.py——重写为标准链路语义 17 用例（并行多调用按序回传、同 id 防重放、全量重发不重执行、无 id 跳过、非法 arguments → ToolParamError 信封、未知工具 available 清单、回声与 finish_reason 断言）。D-5 授权配套（见第四节提问，分发方已授权）：.\flask_server\scripts\check_chat_api.py 场景 1/2/3/6 断言与消息形态同步为标准链路口径（六场景数量与结构不变）；.\docs\api-reference.md 第十四节仅更新占位相关三处（导语、model 缺省值、行为要点末条），未新增场景、未改其它章节。

**验收自测**：python -m pytest tests -q → 1032 passed in 17.63s（A-3 后基线 1024 passed + 1 已知波动，本轮波动未触发，净增 7 用例零失败）；scripts\check_chat_api.py 六场景全过 exit 0；pre-commit run --all-files 七道全 Passed、quality_rules 零 [新增]（pending_tool_calls 拆出 _answered_call_ids、test_single_tool_call 拆断言助手后达标）。

**提交**：本任务六文件单提交（core + routes + tests + 验收脚本 + api-reference + 本记录），提交钩子全过、未用 --no-verify；哈希以推送后分支尖端为准，见对话回复。

## 当前任务（A-4，2026-11-11 下发）：阶段 2 后端标准链路

> 开工前 `git fetch origin && git rebase` 到 fetch 后的 `origin/main` 实时尖端，不照任何文档里印的旧提交号。
> 依据：`.\docs\split-mirror-and-tools-service.md` 第七节阶段 2、决策 1 / 2。

**可以碰**：`flask_server/core/chat_completions.py`（L161 `generate_reply` 从占位生成器换成接翻译员的标准链路，文件头注释已写明「阶段 2 接入翻译员后只需替换 generate_reply」；`tool_calls` / `tool` 消息规范化与回传）、`core/system_prompt.py`（标准四段，方言一律不进本文件，规格 4.3）、`routes/system_prompt.py`、`routes/chat_api.py`（L84 / L140 调用点）、相应 pytest 用例。

**不要碰**：`.\extend\` 与 `skills\` 下任何文件（C-5 范围；`skills/anatomy` 为无关示例仓库）；`core/client_registry.py`、`routes/clients.py`、`routes/command_catalog.py`、`routes/bridge.py`、`routes/cards.py`（B-5 范围）；不新建任何切换开关（一刀切，旧代码留到阶段 3 删）、不自填 `[答复]`、不自行开工其它任务。

**验收**：在 `.\flask_server` 下 `python -m pytest tests -q`，失败仅限已知波动 `test_inbox_site_isolation.py`；`pre-commit run --all-files` 七道全过；一次提交、提交信息只描述改动、正常跑钩子不用 `--no-verify`。

**完成后**：推 `origin/work/ai-a`，回「更新 git，A-4 完成，提交 <hash>」等分发方逐条验收；排队槽为空，不自行找活。

## 分发方验收结论（A-4，2026-11-12）

通过，合入 main。防重放、D-5 配套、七道钩子、全量实测齐全；排队槽为空，待命。

## 阶段 2 收口（2026-11-12）

A-4 已随阶段 2 整体收口，实机回归由用户确认通过；阶段 3 前置未满足，不启动。排队槽为空，待命。

## 当前任务（A-5，阶段 3 准备）：标准链路侧盘点 + L10 契约入口

> 开工前 git fetch origin，rebase 到 fetch 后的 origin/main 实时尖端。
> 性质：取证/准备，不是阶段 3 删除；三条前置未同时满足前不删任何旧链路。

**可以碰**：只读盘点 flask_server/core/chat_completions.py、flask_server/routes/chat_api.py、
flask_server/core/system_prompt.py，列出「只为网页 AI 写的字段与分支」，逐条给当前调用方、
是否可摘除、摘除前置；L10 契约侧把标准对话接口「模型未接」做成显式可插拔入口 + 契约测试
（仅新增入口位与测试，不接真实模型、不改现有链路行为）。

**不要碰**：remote_bridge 下任何文件、extend 下任何文件、不删旧建卡直调路径、不新建切换开关。

**验收**：pytest 定向全过、pre-commit 七道全过、一次提交正常跑钩子不用 --no-verify、
推 origin/work/ai-a、回「更新 git，A-5 完成，提交 <hash>」。排队槽之外不自找活、不自填 [答复]。


## 新会话启动流程（Git 文档总线 v1，2026-11-12 起）

本任务起通信改走 git 文档总线，协议见 docs/collaboration-bus.md，共用脚本 scripts/doc_bus.py。
新开会话后：
1. git fetch origin --prune，读协议、docs/work-dispatcher.md、docs/work-board.md 与本文；
2. python scripts/doc_bus.py read --me a 读完四方未读消息；
3. python scripts/doc_bus.py init --me a 确认四份消息文件齐全；
4. 空闲循环 while true; do python scripts/doc_bus.py wait --me a; done（60 秒一轮、10 秒一探、有更新立即返回）；
5. 发言用 python scripts/doc_bus.py send --me a --to <b|c|dispatcher|all> --kind <question|answer|report> --text T [--reply-to ID]，只写自己那份消息文件、只追加；
6. 代码仍推自己的工作分支，消息提交由脚本自动推 main（仅限自己那份文件），两者互不干扰。

任务下发、验收结论、合入 main 仍只认分发方在总线里的裁定；技术问答可直接与其他方在总线里对。
本节只改通信方式，A-5 的任务范围与边界不变。


## 唯一入口变更（2026-11-13）

本任务起唯一入口为 docs/START_HERE.md：按当前分支判身份（whoami）、读总线消息感知进度、按其启动流程开工。历史对话里任何分身份启动提示词作废。A-5 的任务范围与边界不变。


### 任务 A-5：标准链路侧盘点 + L10 契约入口（已完成，2026-11-13）

**改了什么**：flask_server/routes/chat_api.py（新增 L10 契约入口：register_pre_dispatch_hook / clear_pre_dispatch_hooks / _run_pre_dispatch_hooks，唯一点位在历史合并后、_execute_pending 前，既有链路语义零改动）；flask_server/tests/test_chat_l10_contract.py（新：契约测试 9 条，夹具与样板从 tests.test_chat_api 导入复用，不复制样板）；docs/a5-standard-chain-inventory.md（新：三文件「只为网页 AI 写的字段与分支」逐条盘点 + 调用方地图 + 摘除前置）；本记录（只追加）。

**验收自测**：pytest 定向三文件 41 passed；scripts/quality_rules.py exit 0（[新增] x0，dup 组回到基线 94）；pre-commit 七道全过（js-tests 本机实跑 Passed）。过程中结构质量曾报 dup 溢出 1 组——定位为初版测试复制了 test_chat_api 样板，按 A-4 前例改为导入复用后归零，未动基线。

**提交**：一次提交、正常跑钩子、未用 --no-verify；哈希以推送后分支尖端为准，见总线 report。

## 口径更新（2026-11-13，分发方）

- 阶段 3 删除动作按 docs/a5-standard-chain-inventory.md、docs/b6-legacy-caller-map.md、docs/c6-direct-path-inventory.md 三份报告的调用方地图与可摘除性评估逐笔裁定，由分发方下发、独立 worktree 验收、串行合入 main。
- 本文历史节中「三条前置未满足、不启动」「删除动作不下发」等表述为当时口径，以本行、docs/work-board.md 末节与 docs/START_HERE.md 第 2 节为准。
- A-5 / B-6 / C-6 准备任务全部收口，排队槽为空；轮询状态服从用户明确指令。

## 当前任务（A-7，阶段 3 删除序列首笔，2026-11-13 下发）

> 开工前 git fetch origin --prune，git merge --ff-only origin/main 同步文档真源。

**目标**：让标准 tool_calls 链路成为可扩展的运行主链入口，闭合 L10 契约侧，并依据 docs/a5-standard-chain-inventory.md 逐项判定 flask_server 标准链路侧「只为网页 AI 写的字段与分支」的可摘除项。

**可以碰**：flask_server/core/chat_completions.py、routes/chat_api.py、core/system_prompt.py、routes/system_prompt.py、scripts/check_chat_api.py 与相应 pytest。沿用 A-5 已落地的 register_pre_dispatch_hook / clear_pre_dispatch_hooks / _run_pre_dispatch_hooks 显式可插拔入口，把「history 送真实模型」做成可注册钩子与契约测试；接真实模型需外部服务与凭证，代码侧只到入口，不代签、不硬编码凭证。

**逐项判定**：
- _sanitize_tool_calls 清洗语义：翻译员只发标准 tool_calls 后评估保留为防御或摘除，附调用方复验结论；
- _build_response 的 messages / site_key 扩展字段：决策 14 明文设计，本笔只出评估，改动需分发方裁定；
- _response_to_body 管线兼容与 system_prompt.py 四段式：保留，不纳入摘除。

**边界**：不碰 extend/、remote_bridge/、05c L180 适配层 / 08g / tool-schema-adapter；不新建切换开关；不删旧建卡直调路径（归 C-7）；不碰 B-7 的网关与信封范围；不自填 [答复]、不自行开工未下发任务。

**验收**：独立 worktree 基于实时 origin/main 合入预演 0 冲突；串行单进程全量 pytest（失败仅限 test_inbox_site_isolation.py 已知波动）；pre-commit 七道全过（js-tests 由分发方环境复验）；字段契约对拍；禁区零触碰；一次提交正常跑钩子不用 --no-verify，推 origin/work/ai-a。

**交付载体**：分支一次提交 + docs/bus/a.md 的 report 回执（回提交 hash）；验收以分支提交为准。完成后回监听，不自找活。
