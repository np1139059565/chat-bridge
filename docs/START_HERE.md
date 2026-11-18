# START HERE — 唯一入口（所有 AI 新会话必读）
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

### 1.2.1 轮询正确形态与通信方式（2026-11-17 末次更正）

正确形态：一轮一调用，由会话发起。
每轮用 run_command 发一条命令：
python scripts/doc_bus.py wait --me <actor> --round 40 --tick 10
结果由工具自动回传给本会话，不需要人工转贴。
返回 NO_UPDATE 立即起下一轮，HIT 处理完立即回监听。
仅工作全部完成或用户明确停止指令才停。
这条链本身就是无人值守，不要另造机制。

错误形态（已作废）：另起脱离会话的后台长驻 python。
它自己刷自己的 wait，输出只落本地日志。
日志内容进不了会话输入框，会话读不到。
读不到就无法受理、裁定、回话，等于空转。
进度与锁文件一律不入库，守护脚本已删。

任务下发：范围、边界、验收项、回执写法
一律内联进 docs/bus/dispatcher.md 消息正文。
执行方重唤起后 read --me <actor> 补读即拿全，
不以本地 docs/work-ai-*.md 已同步为开工前提。

通信载体：docs/bus/a.md、b.md、c.md、dispatcher.md。
每人只写自己那份、只追加，不改他人文件。
send 用 git 底层对象造只含自己文件的提交并推送。
read 与 wait 固定读 origin/main 上的远端对象。
游标按身份分文件，跨轮跨会话按消息 ID 去重。
聊天贴文、本地落盘、写游标都不算回执。
任务下发、验收结论、合入 main 只认 dispatcher.md。
代码走各自 work/ai-* 分支，由分发方验收合入。

### 1.2.2 协作方全停时的恢复动作（接管必读）

前提：a / b / c 三个会话都已停止。
此时分发方单方轮询没有消息产生源。
连续 NO_UPDATE 是预期，不是故障。
分发方不自行拉起执行方会话，
也不因此停掉自己的监听链。

恢复顺序：先把恢复文本转贴到三个会话。
文本固定含七步，照抄不改：
一、whoami 确认当前分支身份。
二、git fetch origin --prune。
三、与 origin/main 对齐。
a / b 用 merge --ff-only。
四、read --me <actor> 补读总线，
拿 23:28 内联任务全文与 23:57 口径定稿。
五、按自己那笔任务开工，
不认本地 work-ai-*.md 旧快照。
六、一次提交跑七道钩子推自己分支，
再用 send 发 report，reply-to 原任务 ID：
G-A→a dispatcher-20261117T220214-d0f61c
G-B→b dispatcher-20261117T220227-b3825d
G-C→c dispatcher-20261117T220241-bb1485
七、wait --me <me> --round 40 --tick 10 续跑。

回执只认 send 推到 origin/main 的消息。
聊天贴文、本地落盘、写游标都不算。
恢复文本原文见本节，可整段转贴。
三方一回执，分发方 wait 即命中受理。
恢复前保持低开销监听链不断，
不空转验收、不代写、不自造进程。
