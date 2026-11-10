# 工作对话 · AI-C

> 本文件是本对话的唯一任务来源与工作记录。每次开工前从头读一遍。
> 收到「更新 git」指令时，先读本文件最后一节，再执行。

## 一、工作约定（硬约束）

### 1.1 路径写法

- **只用工程内相对路径**，形如 `.\flask_server\routes\custom_tools.py`、`.\docs\split-mirror-and-tools-service.md`
- **禁止出现任何绝对路径**。各 AI 的工作区根目录不同，绝对路径必然对不上
- 文档里提到文件、目录、命令，一律按这个写法

### 1.2 分支

- 在分支 `work/ai-c` 上工作
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

### 1.6 与其他 AI 的边界

| AI | 负责 | 你不得触碰 |
|---|---|---|
| AI-A | 标准对话接口、System Prompt、会话历史 | `/v1/chat/completions` 相关文件 |
| AI-B | 投递队列、语音接口 | `card_bus` / 投递队列相关文件 |
| AI-C（你） | 客户端注册、指令收归 | — |

有交叉嫌疑时先提问。

---

## 二、当前任务

### 任务 C-3a：语言包寄存通道（C-3 第一刀，后端）

**目标**：按 `.\docs\split-mirror-and-tools-service.md` 1.2、4.2 节，语言包（站点元素选择器与容器特征）由翻译员所有、**寄存在工具服务的客户端注册信息里，服务端不解释其内容**。本任务把这条寄存/取回通道在后端做实，不涉及前端界面。

> 拆分说明：原 C-3「站点档案迁移到客户端注册信息」涉及前端界面改造，Q-3 答复要求先拆清范围。现拆为 C-3a（后端寄存通道，本任务）与 C-3b（前端 `08g_site_profiles.js` 等读写迁移 + 真源切换）。C-3b 待本任务定稿后按 2.5 节预下发。

**做什么**：

1. 先读 `.\flask_server\routes\clients.py`、`.\flask_server\core\client_registry.py` 与 `.\docs\api-reference.md` 第十一节：现有 `POST/GET/DELETE /api/clients` 已支持 `custom_config` 任意嵌套 JSON **原样保管、逐字段一致取回**
2. 判断语言包寄存是否需要新增独立入口：倾向**复用现有 `custom_config`，不新增路由**；若论证必须新增（例如按 site_key 单独取回语言包），则在 `.\flask_server\routes\clients.py` 增加 GET/PUT 并在任务书外先提问确认，不得擅自改接口契约
3. 取回时逐字段原样返回，不校验、不清洗、不解释字段（与 C-1「逐字节一致」同口径）
4. 未注册的 `site_key` 返回 404 与明确错误，**不静默兜底到默认站点档案**——历史事故「千问站点档案缺失被按 GLM 解析」即由静默兜底引起
5. 新建 `.\flask_server\tests\test_client_language_pack.py`：含中文、嵌套、null、特殊字符的语言包存一遍取一遍深比较；不同 `site_key` 互不串；未注册不兜底；重复注册整条覆盖
6. 在 `.\docs\api-reference.md` **新增一个顶层章节**记录语言包寄存与取回方式：章节号按合入时实际末节顺延，A-2 已预定第十五节，本任务用**第十六节**；若 A-2 尚未落地，合入时由分发方按「保留双方新增」重排。只追加新章节，不改既有章节编号

**不做什么**：

- 不改 `.\flask_server\config\definition.yaml` 里 `app.profiles` 站点档案真源（真源切换属 C-3b）
- 不改 `.\extend\` 下任何文件（前端 `08g` 迁移属 C-3b）
- 不改 `.\flask_server\core\config_store.py` 的 `sanitize_profiles` 语义
- 不碰 A 的 `/v1/chat/completions`、`/v1/system_prompt`，不碰 B 正在改的工具参数声明文件（`tool_meta.py` 等）
- 不动 `scripts\quality_baseline.json`

**可以碰的文件**：

| 文件 | 说明 |
|---|---|
| `.\flask_server\core\client_registry.py` | 寄存逻辑（若需） |
| `.\flask_server\routes\clients.py` | 取回入口（若需新增，先提问） |
| `.\flask_server\tests\test_client_language_pack.py` | 新建测试 |
| `.\docs\api-reference.md` | 新增第十六节 |

**不要碰**：

- `.\flask_server\config\definition.yaml`
- `.\extend\` 下任何文件
- `.\flask_server\core\config_store.py`
- `.\flask_server\tools\` 下参数声明文件
- `.\flask_server\routes\chat_api.py`、`.\flask_server\core\chat_completions.py`

**实现原则**：

1. 优先复用不新增：现有 `custom_config` 已满足「任意 JSON 原样保管」时，本任务以测试与文档落档为主，不制造第二套寄存结构
2. 服务端不解释语言包字段含义，不把它并入 `config_store` 的档案解析链
3. 一个任务一次提交；提交前跑通 `.\flask_server` 下测试
4. 规格没写的先提问，按 1.4 处理

**验收标准**：

| # | 项 | 期望 |
|---|---|---|
| 1 | 原样一致 | 含中文、嵌套、null、特殊字符的语言包存一遍取一遍深比较完全一致 |
| 2 | 未注册不兜底 | 未注册 `site_key` 返回 404 与明确错误，不返回默认档案 |
| 3 | 隔离 | 两个 `site_key` 的语言包互不串；重复注册整条覆盖 |
| 4 | 全量测试 | `python -m pytest tests -q` 全绿（当前基线 984） |
| 5 | 质量闸 | `python scripts/quality_rules.py` 无 `[新增]` 违规，`doc-sync` 通过 |
| 6 | 文档 | `api-reference.md` 新增章节说明寄存与取回方式 |

把输出摘要贴进本文件第五节；提交钩子全过、不用 `--no-verify`。

**完成后**：

1. 在本文件第五节追加完成记录
2. 推送 `work/ai-c` 分支
3. 等「更新 git」指令，由分发方逐条验收

> C-3b（前端迁移）待本任务定稿后按 2.5 节预下发，未标注「可开工」不得动手。

---

## 三、排队任务（可提前开工）

> 当前任务收尾并推送后，若本节有标注「可开工」的任务，直接开工，无需等指令。

| 编号 | 任务 | 状态 |
|---|---|---|
| C-3b | 站点档案前端迁移（`08g` 等） | 暂缓：与 1b 前端适配层 `05c_prompt.js` 改动面重叠，待 B-3 定稿与适配层收口后再拆；未标注「可开工」不得动手 |
| C-3a | 语言包寄存通道（后端） | 已下发为当前任务，见第二节 |

---

## 四、提问与答复

> AI 在此登记疑问，每条写明：问题、已尝试什么、卡在哪。
> 答复写在同一编号下，标 `[答复]`。

### Q-1 质量闸存量欠账的处理方式（C-1-Q1）

- 问题：`git commit` 被 pre-commit「结构质量」钩子拦下，43 条 `[新增]` 违规属上游存量，与 C-1 无关。`scripts\quality_baseline.json` 不在本任务可碰清单内，按 1.4 停下提问。
- 已尝试：`python -m pytest tests -q` 956 passed；`python scripts\quality_rules.py` 直接跑，C-1 相关文件零 `[新增]`。

- [答复] 分发方已在 `main` 上完成基线登记（提交 `a493941`），43 条存量欠账记为已知，质量闸现已转绿。
  - 选择理由：基线是全仓共用的一份文件，三个执行方各自改会在合并时冲突，必须由分发方统一登记一次。
  - 你的分支不需要再动 `scripts\quality_baseline.json`。
  - 执行下一步：`git rebase origin/main`（或 merge），确认 `python scripts\quality_rules.py` 返回 0 且无 `[新增]`，然后按正常流程 `git commit`（不加 `--no-verify`）并推送 `work/ai-c`。
  - 提交仍被拦时，先确认已 rebase 到含 `a493941` 的 main，再把实际输出贴回本节。

- [答复·补充] 你提的四个选项一律不采用。正确路径是分发方统一登记基线，执行方 rebase 后正常提交。

### Q-2 C-1 是否已验收、下一步做什么

- [答复] C-1 已验收通过并合入 `main`，验收结论写在第五节。你的提交 `db400db` 基于最新 main，改动 6 个文件全部在可碰清单内，实测通过。
- [答复] 下一步：**当前任务已切换为 C-2**（指令统一收归服务端），任务书见本文件第二节，可直接开工，不需要再等指令。
- [答复] C-1 的任务书已移入「六、历史任务」，仅作存档，不再作为工作依据。

### Q-3 C-2 验收结果与下一步

- [答复] C-2 已验收通过并合入 `main`，提交 `3c7b033`。
- 分发方实测：`python -m pytest tests -q` 962 项全绿；改动 6 个文件全在可碰清单内；自建数据验证三来源合并（builtin 25 条、custom 5 条、client 按 site_key 展开）、两客户端同名指令各成一条、内置表置空不报错、单来源抛异常不影响整体、帮助文本与清单取自同一次读取，全部通过。
- [答复] 你停在 C-3 未标注「可开工」处，处理正确。**C-3 暂不下发**：站点档案迁移涉及前端界面改造，范围还需要拆分清楚，拆完再写任务书。
- [答复] 当前无待办任务，等 C-3 下发即可。
- [答复] C-3 已拆为 C-3a（后端寄存通道）与 C-3b（前端迁移）。**C-3a 已下发为当前任务**，任务书见第二节，可直接开工；C-3b 待 C-3a 定稿后按 2.5 节预下发。
- [答复] C-3a 已验收通过并合入 `main`（`3d81291`），结论见第五节。**C-3b 暂不下发**：`.\docs\config-isolation-and-cache-design.md` 方案 v3 的改动面覆盖 8 个前端文件 + 3 个后端模块，其中 `extend/dialog/parts/05c_prompt.js` 同时是 1b 前端适配层的三处调用方之一；B-3 正在改工具参数声明，适配层待其定稿后另派，两拨人改同一文件必然返工（按 2.5 节判断标准）。等 B-3 与 1b 前端适配层收口后，由分发方拆清范围再下发。当前无待办任务，等指令。

---

## 五、完成记录

> 每个任务完成后在此追加：任务编号、改了什么、验收结果、提交哈希。

### C-1 客户端注册接口与自定义配置保管

- 改动：
  - 新增 `.\flask_server\core\client_registry.py`：注册表登记 / 取回 / 注销与 JSON 落盘。
  - 新增 `.\flask_server\routes\clients.py`：注册、取回、注销三个接口。
  - `.\flask_server\app.py`：注册客户端注册蓝图。
  - 新增 `.\flask_server\tests\test_client_registry.py`：覆盖六个验收场景与重启后取回。
  - `.\docs\api-reference.md`：补客户端注册接口说明。
- 落盘位置选择理由：注册信息写入 `.\flask_server\data\client_registry.json`。该目录是既有运行时数据目录，不入库；采用 JSON 而非 YAML 或 `.\flask_server\config\definition.yaml`，是为原生保留任意嵌套结构、中文、null、空字符串与特殊字符，且不把客户端私有数据混入入库的定义文件；新通道不调用 `sanitize_profiles` 等任何清洗逻辑。
- 验收：`.\flask_server\tests\test_client_registry.py` 7 passed；`.\flask_server` 全量 `pytest tests` 956 passed；`.\scripts\quality_rules.py` 返回 0、零 `[新增]`。
- 提交哈希：`db400db`（完整 `db400db56bddae8ad7bcf731948442e1e7b3ec9f`）。

**分发方验收结论：通过。** 实测 `python -m pytest tests -q` 956 项全绿；改动 6 个文件全部落在可碰清单内；自建含中文、嵌套对象、数组、null、空字符串、emoji 的配置做深比较，deep_equal 与 byte_equal 均为 True；重启后取回、重复注册覆盖、注销幂等、未注册返回 404、缺 `site_key` 返回 400、`OPTIONS` 行为与既有路由一致，七项场景逐一实测通过。已合入 `main`。

### C-2 指令统一收归服务端

**分发方验收结论：通过。** 962 项测试全绿；6 个文件全在可碰清单内；自建数据验证三来源合并、同名指令按 site_key 区分、空来源与异常来源兜底、帮助文本与清单一致，全部实测通过。已合入 `main`。

- 改动：
  - 新增 `.\flask_server\core\command_catalog.py`：三来源指令定义汇总与按来源分组的帮助文本；只读汇总，不改执行通道。
  - 新增 `.\flask_server\routes\command_catalog.py`：`GET /api/commands` 与 `GET /api/commands/help` 两个查询接口。
  - 新增 `.\flask_server\tests\test_command_catalog.py`：覆盖六个验收场景。
  - `.\flask_server\app.py`：注册指令清单蓝图。
  - `.\docs\api-reference.md`：补第十二节接口说明。
- 取数口径：内置读 `command_registry.BUILTIN`（不复制表）；自定义读 `list_external_commands()`（不重写扫描）；客户端读 C-1 注册表的 `commands` 字段。注册表没有公开枚举函数且本任务「不要碰」该文件，故在新建汇总模块里只读复用其整表读取原语，`.\flask_server\core\client_registry.py` 一行未改。
- 验收：六个场景全部通过（三来源合并、无客户端、有客户端、两客户端同名指令按 `site_key` 区分、帮助文本分组且与清单一致、内置表为空不报错）。`.\flask_server\tests\test_command_catalog.py` 6 passed；`.\flask_server` 全量 `pytest tests` 962 passed；`.\scripts\quality_rules.py` 返回 0、零 `[新增]`；`.\scripts\check_doc_sync.py` 通过。
- 提交哈希：本记录随同一次提交入库，以 `git log -1 --format=%H` 为准。

### C-3a 语言包寄存通道（后端）

- 改动：
  - 新增 `.\flask_server\tests\test_client_language_pack.py`：含中文、嵌套、null、特殊字符的语言包深比较与逐字节一致实测，覆盖未注册不兜底、站点隔离、重复覆盖、服务端不解释字段。
  - `.\docs\api-reference.md`：新增「十六、语言包寄存」顶层章节，记录寄存、取回与边界；按任务书指令用第十六节（A-2 预定十五节，合入时由分发方按「保留双方新增」重排），只追加新章节，不改既有编号。
- 复用判定：按「做什么」第 2 条与实现原则 1，现有 `POST/GET /api/clients` 的 `custom_config` 已满足任意嵌套 JSON 原样保管、逐字段一致取回、按 `site_key` 隔离、未注册 404 明确报错，且链路不经过 `.\flask_server\core\config_store.py` 的档案解析链。故**不新增独立入口、不改接口契约、不提问**；`.\flask_server\routes\clients.py` 与 `.\flask_server\core\client_registry.py` 一行未改，未制造第二套寄存结构。
- 输出摘要（验收六项）：
  1. 原样一致：`.\flask_server\tests\test_client_language_pack.py` 5 passed，深比较与同一规则序列化后的 UTF-8 字节串均一致；
  2. 未注册不兜底：未注册 `site_key` 返回 HTTP 404 与明确错误，响应不含 `custom_config` / `profiles`，不返回默认档案；
  3. 隔离：两个 `site_key` 语言包互不串，重复注册整条覆盖；
  4. 全量测试：`.\flask_server` 下 `python -m pytest tests -q` 989 passed（当前基线 984 + 新增 5）；
  5. 质量闸：`.\scripts\quality_rules.py` 返回 0、零 `[新增]`；`.\scripts\check_doc_sync.py` 通过；提交钩子全过，不用 `--no-verify`；
  6. 文档：`.\docs\api-reference.md` 新增第十六节，说明复用 `custom_config` 的寄存与取回方式。
- 提交哈希：本记录随同一次提交入库，以 `git log -1 --format=%H` 为准。

**分发方验收结论（2026-11-10）：通过。** 拉取 `origin/work/ai-c` 至 `272d7ad`，独立工作树逐条实测：`python -m pytest tests -q` → 989 passed in 21.16s；`quality_rules.py` 统一闸门 exit 0、零 `[新增]`；`check_doc_sync.py` 通过。自建含中文、嵌套对象、数组、null、空串、特殊字符与 emoji 的语言包，经 `POST/GET /api/clients` 存一遍取一遍，深比较与同一规则序列化后 UTF-8 逐字节比较均一致；未注册 `site_key` 返回 404 且响应不含 `custom_config` / `profiles`，不兜底默认档案；两个 `site_key` 互不串、重复注册整条覆盖、重建 app 后取回不变。改动 3 文件全在可碰清单内，`clients.py`、`client_registry.py`、`definition.yaml`、`.\extend\`、`config_store.py` 一行未动。合入 `main` 时 `api-reference.md` 按「保留双方新增」把「十六、语言包寄存」重排为「十五」（A-2 尚未落地，保持编号连续），A-2 任务书预期同步改为第十六节。C-3b 保持未标注「可开工」，由分发方拆清范围后下发。

## 六、历史任务（已验收）

### 任务 C-1：客户端注册接口与自定义配置保管

**目标**：让任何客户端（翻译员或标准 API 客户端）能注册到工具服务，并把私有配置寄存在这里，服务端原样保管、原样下发、不解释内容。

**做什么**：

1. 新增注册接口：客户端提交「客户端标识 + 自定义配置 + 可执行指令声明」，服务端登记
2. 新增取回接口：按客户端标识取回注册信息，自定义配置原样返回
3. 新增注销接口：按客户端标识移除登记
4. 自定义配置**不做任何校验与清洗**：存进去什么，取出来就是什么，字段名、结构、值都原样保留
5. 注册信息持久化落盘，重启后仍在
6. 客户端标识使用 `site_key` 字段名（规格文档决策 6）

**不做什么**：

- 不改造现有的 `app.profiles`（站点档案的迁移是后续任务，本任务只建立新通道）
- 不改设置页界面（界面调整是后续任务）
- 不做指令收归（那是下一个任务 C-2）

**可以碰的文件**：

| 文件 | 说明 |
|---|---|
| `.\flask_server\routes\` 下新建路由文件 | 承载注册/取回/注销三个接口 |
| `.\flask_server\core\` 下新建模块 | 注册表存储与读写 |
| `.\flask_server\app.py` | 注册蓝图 |
| `.\flask_server\config\definition.yaml` 或新文件 | 注册信息落盘位置，自行判断放哪合适，**在完成记录里写明选择理由** |
| `.\flask_server\tests\` 下新建测试文件 | 覆盖三个接口 |
| `.\docs\api-reference.md` | 补接口说明 |

**实现要点**：

1. 「不校验」是硬要求。现有 `config_store.py` 里有 `sanitize_profiles` 这类清洗函数，新通道**不得**调用任何同类逻辑。
2. 落盘格式要能保存任意嵌套结构，不要为省事限定成扁平键值。
3. 注册接口要幂等：同一 `site_key` 重复注册时，覆盖旧的自定义配置（不是追加）。
4. 注销不存在的 `site_key` 不报错。

**验收标准**：

写测试覆盖以下场景，全部通过：

| 场景 | 期望 |
|---|---|
| 注册后取回 | 自定义配置与存入时逐字节一致（含嵌套对象、数组、空值、特殊字符） |
| 重复注册 | 后者覆盖前者 |
| 取回未注册的标识 | 返回明确错误 |
| 注销后取回 | 返回明确错误 |
| 注销不存在的标识 | 不报错 |
| 重启后取回 | 内容不变 |

「逐字节一致」这条要实测：构造一个含中文、数组、嵌套对象、空字符串、null 的配置，存进去再取出来做深比较。

---

### 任务 C-2：指令统一收归服务端

**背景**：指令定义现在分散在两处——内置指令写死在 `.\.flask_server\remote_bridge\command_registry.py` 的 `BUILTIN` 表里，各客户端注册时声明的可执行指令又只存在注册表里没有统一出口。规格要求「指令定义全部存于工具服务」，客户端注册时登记自己能执行哪些指令，服务端提供统一的指令清单查询入口。

**做什么**：

1. 新增 `GET /api/commands`：返回全部可用指令的清单，含三个来源——内置指令、自定义指令、已注册客户端声明的指令
2. 新增 `GET /api/commands/help`：返回指令帮助文本，按来源分组
3. 清单每项至少含：指令名、来源（builtin / custom / client）、说明
4. 客户端声明的指令从 C-1 的注册表读取（`commands` 字段），按 `site_key` 归属标注
5. 指令**回执不进 AI 对话流**：本任务只做定义收归与查询，不改执行通道

**不做什么**：

- 不改现有指令的执行路径（`.\.flask_server\remote_bridge\command_dispatch.py` 一行不动）
- 不改 `.\.flask_server\routes\cards.py` 的 `/api/commands/pending` 语义（那是执行侧的取件接口）
- 不改 C-1 的注册表读写逻辑
- 不做指令权限控制（用户指令与 AI 工具的隔离已由通道分离保证）
- 不改 `.\.extend\` 下任何文件

**可以碰的文件**：

| 文件 | 说明 |
|---|---|
| `.\.flask_server\routes\` 下新建路由文件 | 承载两个查询接口 |
| `.\.flask_server\core\` 下新建模块或扩展已有模块 | 指令清单汇总逻辑 |
| `.\.flask_server\app.py` | 注册蓝图 |
| `.\.flask_server\tests\` 下新建测试文件 | 覆盖两个接口 |
| `.\.docs\api-reference.md` | 补接口说明 |

**不要碰**：

- `.\.flask_server\remote_bridge\command_registry.py`（只读它的 `BUILTIN`，不改）
- `.\.flask_server\remote_bridge\command_dispatch.py`
- `.\.flask_server\routes\cards.py`
- `.\.flask_server\core\client_registry.py`（C-1 刚合入，只读不改）
- `.\.extend\` 下任何文件

**实现要点**：

1. 内置指令清单直接从 `command_registry.BUILTIN` 读，不要复制一份表——两处维护必然漂移。
2. 客户端声明的指令从 C-1 注册表读，注册表没有「列出全部客户端」的接口，需要新增一个只读的枚举函数；这是对 `client_registry.py` 的最小扩展，加函数不改已有行为，如判断有风险先在提问区问。
3. 自定义指令用现有的 `.\.flask_server\custom_tools\commands.py` 里的 `list_external_commands()`，不要重新实现扫描逻辑。
4. 三个来源合并时统一字段名，来源用固定枚举值区分。
5. 帮助文本按来源分组，参考 `command_registry.help_text()` 的现有格式。

**验收标准**：

| 场景 | 期望 |
|---|---|
| 查询全部指令 | 返回三个来源的合并清单，每项含名称、来源、说明 |
| 无客户端注册时 | 只返回内置与自定义来源，不报错 |
| 有客户端注册后 | 清单包含该客户端声明的指令，来源标为 client |
| 两个客户端声明同名指令 | 两条都出现，用 `site_key` 区分 |
| 帮助文本 | 按来源分组，内容与清单一致 |
| 内置指令表为空 | 不报错，返回其余来源 |

测试写进 `.\.flask_server\tests\` 下新建的测试文件，跑通后把结果贴进第五节。

**完成后**：

1. 在本文件第五节追加完成记录
2. 推送 `work/ai-c` 分支
3. 若第三节已有标注「可开工」的排队任务，直接开工；否则等「更新 git」指令

---
