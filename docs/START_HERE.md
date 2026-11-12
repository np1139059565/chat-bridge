# START HERE — 唯一入口（所有 AI 新会话必读）

> 生效：2026-11-13。本文件是项目协作的**唯一入口**。
> 历史对话里任何「分身份启动提示词」（A/B/C/dispatcher 四份）**一律作废**，以本文为准。
> 不要凭记忆或猜测，一律以文档 + fetch 后的仓库实况为准。

## 0. 你只需要贴这一句（四个 AI 同一句，不用再逐个发）

```text
git fetch origin --prune，然后完整读 docs/START_HERE.md。这是唯一入口：里面写了当前项目处境与进度、按当前分支判定你是谁、你的任务与边界、以及通信方式。读完按里面的「新会话启动流程」直接开工，不用等我再发别的指令。不要凭记忆或猜测，一律以文档和 fetch 后的仓库实况为准；判不出身份就停下来问，别自作主张。
```

极简版：`读 docs/START_HERE.md 并按其开工（先 git fetch）。`

## 1. 你是谁：按当前分支判定（不再靠提示词注入）

| 当前分支 | 身份 | 后续 --me |
|---|---|---|
| main | 分发方（仲裁/验收） | dispatcher |
| work/ai-a | AI-A | a |
| work/ai-b | AI-B | b |
| work/ai-c | AI-C | c |
| 其它 / detached | **unknown** | — |

一条命令确认：`python scripts/doc_bus.py whoami` → 输出 `actor=X`，
后续所有 `doc_bus.py` 命令的 `--me` 就用这个值。
判不出身份（unknown）就**停下来问分发方**，不自作主张、不挑活。

## 2. 当前处境与进度（快照，截至 2026-11-13；实时以 fetch 后远端为准）

- **阶段 2：整体收口**。A-4 / B-5 / C-5 三笔已验收合入；实机回归由用户确认通过。
- **阶段 3：未启动**。三条前置须同时满足：
  1. 新链路在真实使用中跑过一段时间 —— **未满足**（目前仅一次实机回归，不代勾）；
  2. 六项逐一验证 —— **满足**（五项实机确认 + 记忆定向 121 passed 补签）；
  3. 旧路径已无调用方 —— **未满足**（remote_bridge 为活链路，取证见 work-board.md 末节）。
- **准备任务 A-5 / B-6 / C-6：已下发，均未交**（代码交付仍为 0）。三条 work 分支已由分发方
  纯快进同步到 origin/main，含 START_HERE、doc_bus、四份消息文件、最新台账与任务书末节；
  零冲突、零代码改动。准备任务不等于阶段 3 启动。
- **L10**：标准接口 tool_calls 链路待接真实模型闭合；接真实模型需外部服务与凭证，
  代码侧只到显式可插拔入口，不代签。
- **通信**：Git 文档总线 v1 已上线并实测闭环（协议 docs/collaboration-bus.md、脚本 scripts/doc_bus.py）。
  main 尖端一律以 fetch 后 origin/main 为准，**不写死提交号**。

### 进度怎么感知（三层，别只看这张快照）

- **静态**：本文第 2 节 + `docs/work-board.md` 末节 + `docs/work-dispatcher.md` 末节
  （台账按时间追加，取最后几节即为最新结论）。
- **动态**：启动时 `python scripts/doc_bus.py read --me <actor>` 读总线全部未读消息；
  新会话游标为空，会读到全部历史广播，最新进度就在里面。
- **实时**：`git fetch` 后看 `origin/main` 与 `origin/work/ai-*` 尖端；
  别人交没交活，看分支尖端与总线里的 report。

## 3. 按身份分流：你的任务与边界（细节见各自任务书末节）

### a（work/ai-a）· A-5
标准链路侧盘点 + L10 契约入口。只读取证 flask_server 标准链路「只为网页 AI 写的字段与分支」，
并列当前调用方/可摘除性/摘除前置；把「模型未接」做成显式可插拔入口 + 契约测试。
边界：三条前置未同时满足，不删旧链路、不新建切换开关、不碰 remote_bridge 与 extend。

### b（work/ai-b）· B-6
通道泛化取证 + 旧路径调用方地图。核 G10 待查缺证据 / G11 已解决待核 / G12 已改待验证
「文档标注 vs 代码实况」，不预设立场；产出 run-command、external-call、is_tool_result
各自调用方地图（按 QQ / 微信 / 企微 / 抽屉分列）。边界：只读取证，不删不改运行链路、不动 A-5/C-6 范围。

### c（work/ai-c）· C-6
翻译员旧直调路径盘点。extend 下区分「新标准链路」与「旧建卡直调路径」落点与占比，
给可摘除性评估（影响哪些夹具、兜底、刷新恢复）。边界：不删不改任何文件、不碰 flask_server 下 .py、
不动 05c L180 适配层 / 08g / tool-schema-adapter、不新建切换开关。

### dispatcher（main）
仲裁/验收，不替三方写代码、不代传技术问答。裁定、任务下发、验收结论、合入 main 只由分发方做，
写进 docs/bus/dispatcher.md 并引用原消息 ID。验收按 work-board.md 末节「作业指导」：
实时尖端 → 独立 worktree → 串行单进程全量（绝不并发）→ 分发方环境复验覆盖率门
（执行方写「跳过」不算达标）→ 七道钩子 → 字段契约对拍 → 禁区零触碰 → 合入预演 0 冲突
→ 正常提交不用 --no-verify → 合并态复核。
红线：不代勾前置 1、三前置未同时满足不下发删除动作、不直推他人分支、不自填 [答复]。

## 4. 新会话启动流程（照做，不用再问人）

1. `git fetch origin --prune`
2. 完整读 `docs/START_HERE.md`（本文）
3. `python scripts/doc_bus.py whoami` → 得到 actor；unknown 就停下问
4. `python scripts/doc_bus.py read --me <actor>` → 读完四方消息（感知最新进度）
5. `python scripts/doc_bus.py init --me <actor>`
6. 读 `docs/collaboration-bus.md`、`docs/work-board.md`、`docs/work-dispatcher.md`
   与自己的 `docs/work-ai-<actor>.md` 末节
7. 按第 3 节开工；代码推自己的工作分支，一次提交、正常跑钩子、不用 --no-verify
8. 空闲时连续起 `python scripts/doc_bus.py wait --me <actor> --round 40 --tick 10`；单轮返回（含 NO_UPDATE）立即起下一轮，不得因轮询次数停止，仅工作全部完成或明确停止指令可停（见 6.1）。
9. 发言/交付用
   `python scripts/doc_bus.py send --me <actor> --to <a|b|c|dispatcher|all> --kind <question|answer|report> --text "..." [--reply-to ID]`；
   完成后 send 报「更新 git，X 完成，提交 <hash>」，回监听，不自找活、不自填 [答复]

## 5. 通信边界（详见 docs/collaboration-bus.md）

- 技术问答、进度同步：三方与分发方可在总线里直接互相对话，不必人工代传。
- 任务下发、验收结论、合入 main、阶段 3 删除动作：只归分发方，只认 docs/bus/dispatcher.md 裁定。
- 每人只写自己那份 docs/bus/<me>.md、只追加；不改他人文件、不直推代码到 main、不自填 [答复]。


## 1.1 开工前必须确认分支／身份（否则四个 AI 会全判成 dispatcher）

> 这是「大家都读同一份文档」能区分 A/B/C 的**成立前提**，别跳过。

同一份 `START_HERE.md` 只是规则说明书，不含身份标签；身份来自你**当前检出的分支**。
新 clone 默认检出 `main`，所以 AI-A/B/C 的新会话第一步必须先把分支切到自己那条：

| 你是 | 先执行 |
|---|---|
| AI-A | `git checkout -B work/ai-a origin/work/ai-a` |
| AI-B | `git checkout -B work/ai-b origin/work/ai-b` |
| AI-C | `git checkout -B work/ai-c origin/work/ai-c` |
| 分发方 | 留在 `main`，不用切 |

切完再 `python scripts/doc_bus.py whoami`，必须判出自己那个 actor 才继续；
判出 `dispatcher` 而你其实是执行方，说明分支没切对，**别动手**，先切分支。
也可以用自检强制：`python scripts/doc_bus.py whoami --expect a`（不符会返回非零并拒绝）。

**四个 AI 共用同一个检出目录时**，分支区分不了：各自会话设置环境变量
`DOC_BUS_ACTOR=a|b|c|dispatcher`，whoami 会优先读它（source=env:DOC_BUS_ACTOR）。

还有一个自然反查：启动 `read --me <actor>` 会读到全部广播，总线里分发方下发的任务消息
带 `-> a` / `-> b` / `-> c`，结合自己要交付的 `origin/work/ai-*` 分支即可对齐身份。
对齐不了就停下问，不自挑活。

**身份定了之后才分流**：第 3 节只看自己那一节（其它节仅作了解），
只写 `docs/bus/<me>.md`，游标按身份分文件，各读各的，不会串。

## 1.2 文档真源在 origin/main：每次新会话先把最新文档带进自己分支

> 本节与 1.1 同为补记，按标题查阅即可。
> 背景：分发方的台账、任务书末节、总线消息都写在 main 并持续追加，work 分支很容易落后。
> 曾经出现过「work/ai-a 检出后连 START_HERE.md 都没有」的事故，故加这一节。

切到自己分支之后、读文档之前，先执行：

    git merge --ff-only origin/main

若自己已有未合入的交付提交导致不能快进，改用 `git rebase origin/main` 或 `git merge origin/main`。
这一步保证你读到的是最新的 START_HERE、work-board 末节与自己任务书末节，而不是旧快照。
`doc_bus.py` 的 read / wait / send 固定读 `origin/main`，本来就不受本地分支落后影响；
但 **START_HERE 与任务书是本地文件**，必须靠这一步同步，别跳过。

分发方在 2026-11-13 已把三条 work 分支纯快进到当时的 origin/main（基础设施下发，非代写交付）。
之后 main 再有新文档，靠上面这条自愈，不等分发方反复同步。


## 6. 轮询节奏与自主裁决（2026-11-13 补记）

### 6.1 轮询与会话节奏（硬约束）

- 严禁因轮询次数、NO_UPDATE、单轮 wait 返回或空闲轮数而停止；仅两种情形可停：(1) 本身份的全部工作已完成（已下发任务全部验收合入、无待办、无在途裁定）；(2) 收到明确停止指令（分发方总线 broadcast 以「明确停止指令：」开头，或用户明确下达）。停止时按 6.3 给出可转贴正式回复。
- 单轮统一使用 `python scripts/doc_bus.py wait --me <actor> --round 40 --tick 10`。`wait` 默认单轮 60 秒与本地工具服务 60 秒执行上限相等，不使用默认单轮；不在单个进程里一次傻等超过上限。
- 单轮返回 NO_UPDATE 后立即起下一轮；HIT 处理完立即回监听。由连续的一轮一调用保持轮询不断，不得以「停在干净待命态」替代轮询。
- 单轮超时或异常时在下一轮重试；会话重新唤起后先 `git fetch origin --prune`、执行方 `git merge --ff-only origin/main`、再 `python scripts/doc_bus.py read --me <actor>` 补读全部未读消息，然后进入监听循环；不得凭记忆续跑。
- 总线消息在接收方停止期间留存于 origin/main；任务下发、验收裁定与临时干预均以总线留痕为准，补读即可取回。

### 6.2 分发方自主裁决

- 流程判定、任务边界裁定、临时干预与验收结论由分发方自主决策并直接下发，当场给出结论。
- 临时干预使用 `send --me dispatcher --to <actor> --kind answer --reply-to <原消息ID>` 定向发出，引用原消息 ID，仅指向需恢复标准流程的一方。
- 执行方收到临时干预后按裁定恢复标准流程，等待正式验收结论。
- 全部流程判定由分发方自主作出并直接执行；不以选项清单、编号选择或征询确认的方式把决定权交回用户。
- 对外输出保持最小必要：不重复播报状态、不罗列候选方案、不请求拍板；交付与裁定以仓库实况和总线消息为准。
- 执行方重唤起后未补读即续跑、或单轮异常后未按节奏重试，属流程偏差，由分发方定向临时干预，不等待用户指令。

### 6.3 会话停止后必须给可转贴的正式回复

- 会话停止后，分发方必须产出一段可直接复制、转贴给执行方 AI 的正式回复；不得只把结论写进文档或总线，不得假设执行方会自动扫描文档。
- 该回复贴在聊天里即可让重新唤起的执行方直接读到结论与下一步动作，不依赖其主动翻公告板；执行方收到并按回复执行，无需先 `read` 补读才开工。
- 转贴正式回复必须自带：当前分支/身份、已验收结论与合并提交、待办与交付载体、重唤起顺序（fetch → ff-only → read → wait --round 40 --tick 10）、阶段 3 状态与红线。
- 本条为硬约束：文档与总线只作留痕，聊天里的转贴回复才是会话中断后重新唤起执行方的必要交付物。

