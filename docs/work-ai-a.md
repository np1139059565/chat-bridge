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

### 任务 A-1：标准对话接口

**目标**：让工具服务能以标准格式接收一次对话请求，并返回标准格式的回复（含工具调用）。

**做什么**：

1. 新增路由 `POST /v1/chat/completions`
2. 接收标准 `messages` 数组（`role` + `content`）
3. 接收标准 `tools` 参数（JSON Schema 格式的工具声明）
4. 返回标准 `choices` 结构，`message` 里可含 `tool_calls`
5. 接收 `tool` 角色消息并回灌给 AI，形成下一轮
6. 请求携带 `stream: true` 时返回明确错误，不静默降级
7. 会话历史落盘，支持多轮延续

**不做什么**：

- 不做流式输出
- 不做鉴权
- 不改造翻译员（那是阶段 2）
- 不改参数声明格式（那是阶段 1b）
- 不做工具列表的对外输出改造（现有 `/tools/all` 先保持原样）

**可以碰的文件**：

| 文件 | 说明 |
|---|---|
| `.\flask_server\routes\` 下新建一个路由文件 | 承载新接口 |
| `.\flask_server\app.py` | 注册蓝图 |
| `.\flask_server\core\` 下新建模块 | 存放标准消息格式转换、会话存储 |
| `.\flask_server\tests\` 下新建测试文件 | 覆盖新接口 |
| `.\flask_server\scripts\` 下新建验收脚本 | 承载 `check_chat_api.py` |
| `.\docs\api-reference.md` | 补 `/v1/chat/completions` 接口说明 |

**不要碰**：

- `.\flask_server\tools\` 下的任何文件（工具执行链路复用即可，不改）
- `.\extend\` 下的任何文件（翻译员是阶段 2）
- `.\flask_server\routes\tools.py`（现有工具路由不动）
- `.\flask_server\routes\cards.py`（投递队列归 AI-B）

**实现原则**：

1. 工具执行复用现有链路，不新建执行器。看懂 `.\flask_server\tools\tools_impl.py` 的派发方式后直接调用。
2. 工具结果放进 `tool` 角色的 `content` 里，按 `.\docs\split-mirror-and-tools-service.md` 第 6.1 节：整套错误结构以 JSON 字符串形式放入，不加额外布尔字段。
3. 会话标识用请求里携带的 `site_key` 字段（字段名已定，见规格文档决策 6）。若请求未携带，自行生成并返回。
4. 工具列表在 `tools` 参数里按标准 JSON Schema 传（容器是对象、必填是顶层数组）。阶段 1b 会改造内部声明格式，**本任务不依赖那个改造**——你只需要能接收并原样使用外部传进来的标准 schema。

**验收标准**：

写一个脚本 `.\flask_server\scripts\check_chat_api.py`，覆盖以下六类场景，全部通过：

| 场景 | 期望 |
|---|---|
| 单轮纯文本对话 | 返回一条 `assistant` 消息，无 `tool_calls` |
| 单轮带一个工具调用 | 返回含 `tool_calls` 的 `assistant` 消息 |
| 工具结果回灌 | 传入 `tool` 角色消息后能继续生成下一轮 |
| 多轮延续 | 同一 `site_key` 连续请求，历史被正确累加 |
| `stream: true` | 返回明确错误，不是 200 |
| 工具执行出错 | `tool` 消息的 `content` 是 JSON 字符串，含错误分类字段 |

脚本跑通后，把输出摘要贴进本文件第五节。

**完成后**：

1. 在本文件第五节追加完成记录
2. 推送 `work/ai-a` 分支
3. 若第三节已有标注「可开工」的排队任务，直接开工；否则等「更新 git」指令

> 第三节的排队任务可提前开工；当前任务 A-1 的范围、可碰文件、验收标准不受影响。

---

## 三、排队任务（可提前开工）

> 本节的语义：当前任务收尾并推送后，无需等待指令，直接开工本节标注「可开工」的任务。
> 分发方会在开始审核你的分支时，把下一个任务写进来并标注。未标注的不得动手。

| 编号 | 任务 | 状态 |
|---|---|---|
| A-2 | 标准 System Prompt 生成 | 待分发方预下发，届时标注「可开工」 |
| A-3 | 标准会话历史存储细化 | 待定，A-1 与 A-2 完成后再拆 |

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

---

## 五、完成记录

> 每个任务完成后在此追加：任务编号、改了什么、验收结果、提交哈希。

### 任务 A-1：标准对话接口（已完成）

**改了什么**：routes/chat_api.py（新：路由层，stream=true 400 拒绝不静默降级）；core/chat_completions.py（新：规范化/占位/复用现有工具管线/会话按 site_key 落盘）；tests/test_chat_api.py（新：六场景+请求校验共 10 用例）；scripts/check_chat_api.py（新：验收脚本）；app.py（注册蓝图，与 C-2 并存）；docs/api-reference.md（第十三节，C-2 已占十二故顺延）

**验收**：check_chat_api.py 六场景全过——单轮纯文本 / 单轮带工具调用 / 工具结果回灌 / 多轮延续 / stream 拒绝 / 工具执行出错信封

**测试与闸门**：python -m pytest tests -q 实测 972 passed in 17.46s（rebase 到 ff83941 后）；质量扫描无新增违规；doc-sync 通过；提交钩子全过、未用 SKIP。

**提交哈希**：功能 ffc69309b6ff09f3d3d8daa90c7077d359147acf；核验报告落档 fdd5f20fc9737607687279f958edf3a6009ee4a2；本记录随其后 docs 提交入库；origin/work/ai-a 尖端 fdd5f20fc9737607687279f958edf3a6009ee4a2。
