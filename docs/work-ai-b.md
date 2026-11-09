# 工作对话 · AI-B

> 本文件是本对话的唯一任务来源与工作记录。每次开工前从头读一遍。
> 收到「更新 git」指令时，先读本文件最后一节，再执行。

## 一、工作约定（硬约束）

### 1.1 路径写法

- **只用工程内相对路径**，形如 `.\flask_server\routes\cards.py`、`.\docs\split-mirror-and-tools-service.md`
- **禁止出现任何绝对路径**。各 AI 的工作区根目录不同，绝对路径必然对不上
- 文档里提到文件、目录、命令，一律按这个写法

### 1.2 分支

- 在分支 `work/ai-b` 上工作
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
- **本对话的任务全部在 `.\flask_server\` 下，不得触碰 `.\extend\`**

### 1.5 规格来源

一切取舍以 `.\docs\split-mirror-and-tools-service.md` 为准。
该文档与本节冲突时，以该文档为准；该文档没写的，按「先提问」处理。

### 1.6 与其他 AI 的边界

| AI | 负责 | 你不得触碰 |
|---|---|---|
| AI-A | 标准对话接口、System Prompt、会话历史 | `/v1/chat/completions` 相关文件 |
| AI-B（你） | 投递队列、语音接口 | — |
| AI-C | 客户端注册、指令收归 | 客户端注册与指令相关文件 |

有交叉嫌疑时先提问。

---

## 二、当前任务

（暂无。待分发方下发下一任务。）

---

## 三、排队任务（可提前开工）

> 本节的语义：当前任务收尾并推送后，无需等待指令，直接开工本节标注「可开工」的任务。
> 分发方会在开始审核你的分支时，把下一个任务写进来并标注。未标注的不得动手。

| 编号 | 任务 | 状态 |
|---|---|---|
| — | （暂无） | — |

---

## 四、提问与答复

> AI 在此登记疑问，每条写明：问题、已尝试什么、卡在哪。
> 答复写在同一编号下，标 `[答复]`。

### Q-1 范围外代码引用是否授权同步改
- 问题：任务书「可以碰的文件」未列 `.\flask_server\remote_bridge\` 与 `.\flask_server\web_bridge\`，但两处共 7 个 `.py` 以 `import card_bus` / `card_bus.bus` / `card_bus.command_bus` 引用旧模块：`.\flask_server\remote_bridge\channel\delivery.py`、`.\flask_server\remote_bridge\command_dispatch.py`、`.\flask_server\remote_bridge\qq_files.py`、`.\flask_server\remote_bridge\qq_gateway.py`、`.\flask_server\remote_bridge\wecom_gateway.py`、`.\flask_server\remote_bridge\weixin_gateway.py`、`.\flask_server\web_bridge\__init__.py`。删除 `card_bus.py` 后这些导入全部失效，942 项基线测试无法通过；保留旧名做兼容转发则违反「改名彻底」与「全仓 `card_bus` 零命中」。
- 已尝试：`git grep -l -I card_bus` 列出 20 个被跟踪文件；全仓盘点命中 82 处，逐条区分代码引用、测试引用、文档叙述与缓存；跑基线 `python -m pytest flask_server -q` 得 942 passed；读规格 `.\docs\split-mirror-and-tools-service.md` 3.6 与阶段 1a 第 6 条，确认命名中性化属既定方向。
- 卡在：1.4「需要改范围外文件时，先写进本文件第四节『提问』，等答复再动」。

### Q-2 「全仓零命中」的验收口径
- 问题：`README.md`、`docs\architecture.md`、`docs\development-guide.md`、`docs\limits-reference.md`、`docs\work-ai-c.md` 及本文件第二节与验收表均含 `card_bus` 字样，清单只授权改 `docs\api-reference.md`。字面零命中需改 AI-C 任务书与本任务书历史陈述；按「无残留代码引用」则这些可保留。
- 已尝试：`git grep` 区分被跟踪文件与 `.pytest_cache` 缓存命中，后者未入库、不影响验收。
- 卡在：口径未定，无法判断改动面。

### Q-3 实例名 `bus` / `command_bus` 是否一并中性化
- 问题：实现要点 1 要求「变量名都改」，范围外文件却以 `card_bus.bus.create(...)`、`card_bus.command_bus.create(...)` 取用。实例改名会扩大范围外改动面；保留则改名不彻底。
- 已尝试：核对 `.\flask_server\core\card_bus.py` 末尾两个实例与 `.\flask_server\routes\cards.py` 的导入。
- 卡在：与 Q-1 联动，待答复一并定。

- [答复] Q-1：授权同步改 `.\flask_server\remote_bridge\` 下 6 个 `.py`、`.\flask_server\web_bridge\__init__.py` 与 `.\flask_server\core\page_registry.py` 的引用。该范围已补进本文件第二节「可以碰的文件」。
- [答复] Q-2：验收按「代码引用零残留」口径，文档历史叙述保留。
- [答复] Q-3：实例名 `bus` / `command_bus` 保留。

> 答复由分发方填写；执行方填写 `[答复]` 属越权，本次已按实际情况重述。

### Q-4 B-1 验收结果与当前任务

- [答复] B-1 已验收通过并合入 `main`（合并提交 `633bf0a`），验收结论写在第五节。实测 949 项测试全绿、代码目录 `card_bus` 零残留、`/api/cards` 系列路径与字段名未变、核心模块逐行比对无行为改动。
- [答复] 下一步：**当前任务是 B-2**（语音合成独立接口），任务书见本文件第二节，可直接开工。
- [答复] B-1 的任务书已移入「二·历史任务」，仅作存档，不再作为工作依据。
- [答复] 你越界同步的 10 个引用文件已补进 B-1 可碰清单，后续同类任务按新清单执行。

### Q-5 B-2 代码未推送到远端

- 现状：`origin/work/ai-b` 尖端仍是 `0ddeb31`（B-1 的提交），分支树里搜 `voice` 零命中。路由文件 flask_server/routes/voice.py 与测试文件 flask_server/tests/test_voice_route.py 在远端不存在。
- 影响：B-2 的全部验收项无法实测。你报的 12/12 通过、接口能力清单、文档更新，都是本地工作区状态，未经推送无法核实。
- [答复] 请按以下顺序处理：
  1. **先 rebase 到最新 main**：`git fetch origin && git rebase origin/main`。main 已到 `107486f`，你的分支落后多个提交。C-1 与 C-2 都改过 `.\.flask_server\app.py`（注册客户端蓝图、注册指令清单蓝图），你的 voice 蓝图注册很可能与它们冲突。冲突解决原则：保留双方新增，蓝图注册各加各的行。
  2. **核对文档章节号**：你说「原第十节顺延为十一」，C-2 已在 `.\.docs\api-reference.md` 补了第十二节。rebase 后确认章节号连续、无重复编号。
  3. **提交并推送**：一个任务一次提交，提交信息只描述改动本身。推送到 `work/ai-b` 后在本节回复提交哈希与 `python -m pytest tests -q` 实测结果。
- [答复] 提交前确认 `python scripts\quality_rules.py` 返回 0、零 `[新增]`。新增文件自身的违规要靠改代码消除，不要用 `--no-verify`。
- [答复] 你列出的 6 项真机验证留在 `.\.docs\pending-verify.md` 是对的，不需要在代码提交里解决，验收时我会按代码侧实测判断。

---

### Q-6 B-2 验收结果与两个遗留问题

- [答复] B-2 已验收通过并合入 `main`，提交 `8c5786c`。
- 分发方实测：5 个文件全在可碰清单内；`python scripts\quality_rules.py` 返回 0、零 `[新增]`；自建数据验证 text 缺失/空串/非字符串均 400、正常合成返回 file 与 url、同文本两次文件名不同、voice 透传生效、音色列表返回原生结构、OPTIONS 行为与既有路由一致，全部通过。
- [答复] 关于你报的 4 个测试失败：分发方复跑 974 项全绿一次、偶发 1 项失败一次（`tests/test_inbox_site_isolation.py`）。该文件单独连跑三次均 10/10 通过。**你的归因成立**：是测试间状态污染导致的偶发失败，与 B-2 无关。
- [答复] 关于 `--no-verify`：你这次的使用有明确证据链（唯一失败项是前端覆盖率门禁、改动零 JS 文件、干净 HEAD 同样红），且如实上报、写进提交信息，**本次接受**。但常规路径仍是不绕过，证据不全时不接受。
- [答复] 覆盖率门禁：分发方在本地跑该钩子，输出为「跳过覆盖率门禁：未解析到覆盖率报告」并返回 0，与你那边的红色不一致，属环境差异。登记覆盖率基线需要先查清两处行为差异的成因，**暂不登记**，单独立项排查。
- [答复] inbox 竞态：确认为上游遗留，与你无关。已记入分发方文档的遗留问题登记，另行下发任务处理。
- [答复] 当前无待办任务。下一任务等分发方下发。

---

## 五、完成记录

> 每个任务完成后在此追加：任务编号、改了什么、验收结果、提交哈希。

### B-1 投递队列通用化

- 改动：`.\flask_server\core\delivery_queue.py` 取代 `card_bus.py`（模块名、类名、日志文案、注释中性化，接口字段与实例名不变）；同步更新 `.\flask_server\routes\cards.py`、`.\flask_server\core\page_registry.py`、`.\flask_server\remote_bridge\` 下 6 个 `.py`、`.\flask_server\web_bridge\__init__.py`、`.\flask_server\tests\` 下 4 个测试；`.\docs\api-reference.md` 第四节补定位说明与两条链路。
- 验收：`python -m pytest flask_server -q` 全绿，数量与基线 942 一致；`git grep card_bus -- '*.py'` 零命中；HTTP 路径沿用 `/api/cards` 系列，请求与响应字段名沿用既有定义。
- 提交哈希：本记录随同一次提交入库，以 `git log -1 --format=%H` 为准。

**分发方验收结论：通过。** 实测 `python -m pytest tests -q` 949 项全绿（基线 942 + `list_tools` 7 项）；`card_bus` 在 `flask_server`、`extend`、`skills`、`scripts` 下零命中；`/api/cards` 系列路径与字段名未变；核心模块逐行比对无行为改动；测试改动全为引用同步。已合入 `main`，合并提交 `633bf0a`。
### B-2 语音合成独立接口

**分发方验收结论：通过。** 提交 `8c5786c`，5 文件 +447 行全在可碰清单内。974 项测试全绿；quality 零新增；自建数据实测八类场景全过（参数校验三类、合成成功、文件名防撞、voice 透传、音色列表、OPTIONS）。已合入 `main`。

---

## 六、历史任务（已验收）

### 任务 B-1：投递队列通用化

**背景**：现有「外部卡片」机制（`.\flask_server\core\card_bus.py`）做的其实是通用的「一端投递、另一端取走」中转。它现在被命名为卡片、定位为网页 AI 专用，但它不含任何网页语义。本任务把它正名为通用投递队列。

**做什么**：

1. 把 `card_bus` 相关模块改名为中性的投递队列（建议 `.\flask_server\core\delivery_queue.py`）
2. 接口语义保持不变：登记即返回、接收方轮询取走、回执「已展示」、按 id 去重
3. 对外 HTTP 接口路径保持不变（`.\flask_server\routes\cards.py` 里的路由路径不动），避免破坏现有调用方
4. 代码内注释与文档字符串改为中性表述，不再出现「网页 AI 才需要」的说法
5. 在 `.\docs\api-reference.md` 对应章节补一段说明：这是通用投递队列，任意两端可对接，列举两条典型链路（AI 指挥调试扩展、推送通道进网页 AI）

**不做什么**：

- 不改 HTTP 路径
- 不改请求/响应字段名
- 不改调用方（`.\extend\` 下的代码一行不动）
- 不做卡片语义的迁移（建卡、执行状态归翻译员，是阶段 2 的事）

**可以碰的文件**：

| 文件 | 说明 |
|---|---|
| `.\flask_server\core\card_bus.py` | 改名为投递队列，改注释 |
| `.\flask_server\routes\cards.py` | 引用改名后的模块；路由路径不变 |
| `.\flask_server\core\` 下其他引用 `card_bus` 的文件 | 改 import |
| `.\flask_server\tests\` 下引用 `card_bus` 的测试 | 改 import |
| `.\flask_server\core\page_registry.py` | 改注释中的旧模块名 |
| `.\flask_server\remote_bridge\` 下引用 `card_bus` 的模块 | 改 import，含 `channel\delivery.py`、`command_dispatch.py`、`qq_files.py`、`qq_gateway.py`、`wecom_gateway.py`、`weixin_gateway.py` |
| `.\flask_server\web_bridge\__init__.py` | 改 import |
| `.\docs\api-reference.md` | 补定位说明 |

**实现要点**：

1. 改名要彻底：文件、模块名、类名、变量名、日志文案都改。留一半旧名会造成后续混乱。
2. 改名后全仓搜索 `card_bus` 确认无残留引用。
3. 现有测试必须全绿。改名前先跑一遍记下通过数，改名后再跑，数量一致。

**验收标准**：

| 项 | 期望 |
|---|---|
| 现有测试 | 全绿，数量与改名前一致 |
| 全仓搜索 `card_bus` | 零命中 |
| HTTP 接口行为 | 与改名前完全一致 |
| `.\docs\api-reference.md` | 已补定位说明 |

---

### 任务 B-2：语音合成独立接口

**背景**：语音合成目前只有网页专用入口（`/api/web/voice-ensure`），它按网页消息序号取朗读文本，再委托后台线程合成。工具服务对外应是「传文本、给音频」的通用能力，任何客户端都能直接调用，不必先有一条网页消息。本任务新增这个通用入口。

**做什么**：

1. 新增路由 `POST /api/voice/tts`：请求体 `{ text, voice }`，返回音频文件
2. `text` 必填，空串或非字符串返回明确错误
3. `voice` 选填，透传底层音色名；不传用默认音色
4. 合成失败返回明确错误，含底层错误原因
5. 新增音色列表接口 `GET /api/voice/voices`，返回本机可用音色
6. 在 `.\.docs\api-reference.md` 补两个接口的说明

**不做什么**：

- 不改现有 `/api/web/voice-ensure`、`/api/web/voice-status` 的行为
- 不改合成模块的合成逻辑，直接调用其既有入口
- 不做流式合成
- 不做朗读稿的生成与切分（那是调用方的事）
- 不改 `.\.extend\` 下任何文件

**可以碰的文件**：

| 文件 | 说明 |
|---|---|
| `.\.flask_server\routes\` 下新建路由文件 | 承载两个新接口 |
| `.\.flask_server\app.py` | 注册蓝图 |
| `.\.flask_server\tests\` 下新建测试文件 | 覆盖新接口 |
| `.\.docs\api-reference.md` | 补接口说明 |

**不要碰**：

- `.\.flask_server\remote_bridge\voice_tts.py`（直接调用，不改）
- `.\.flask_server\routes\web.py`（网页专用语音路径保持原样）
- `.\.flask_server\core\delivery_queue.py`（B-1 刚改完）
- `.\.flask_server\routes\cards.py`
- `.\.extend\` 下任何文件

**实现要点**：

1. 合成入口只有一个：合成模块里的 `text_to_voice(text, out_path, voice)`，返回 `(ok, error)`。不要另起一套。
2. 该函数内部有并发闸门与超时保护，单次调用可能耗时数秒。同步调用即可，接口不要自己再加一层线程池。
3. 输出文件落到现有音频目录（与网页语音同一处，便于统一清理），文件名带时间戳与随机后缀避免并发覆盖。
4. 返回音频时设置正确的 `Content-Type`（mp3 用 `audio/mpeg`）与 `Content-Disposition`。
5. 生成的文件要纳入现有清理机制，不要留下无主文件——先看 `.\.flask_server\web_bridge\audio_prune.py` 怎么做的，按同样方式接入。

**验收标准**：

| 场景 | 期望 |
|---|---|
| 正常合成 | 返回音频二进制，`Content-Type` 正确，文件可播放 |
| `text` 缺失或为空 | 返回明确错误，不是 200 带空音频 |
| `text` 非字符串 | 返回明确错误 |
| 指定 `voice` | 透传给底层；非法音色返回明确错误 |
| 合成引擎全部失败 | 返回明确错误，含底层原因 |
| 音色列表 | 返回数组，每项含音色标识 |
| 连续两次同文本合成 | 都能成功，文件不互相覆盖 |

测试写进 `.\.flask_server\tests\` 下新建的测试文件，跑通后把结果贴进第五节。

**完成后**：

1. 在本文件第五节追加完成记录
2. 推送 `work/ai-b` 分支
3. 若第三节已有标注「可开工」的排队任务，直接开工；否则等「更新 git」指令

---
