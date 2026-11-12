# Git 文档总线 v1（四方协作通信协议）

> 生效：2026-11-12。适用：AI-A / AI-B / AI-C / 分发方，全部新开会话后按本协议通信。
> 本文件替代「由分发方人工转贴回话」的旧方式；脚本与四份启动提示词同源同版。

## 一、目标与载体

- 四方通过 git + 文档互相对话，不再依赖人工搬运消息。
- 消息载体：docs/bus/a.md、docs/bus/b.md、docs/bus/c.md、docs/bus/dispatcher.md，
  每人**只写自己那份、只追加**，不改写、不删历史、不改他人文件 → 文件级零冲突。
- 单一真源：四份消息文件统一落在 origin/main；脚本一律读远端对象，不 checkout、不 merge、
  不 rebase，不碰任何人的工作区或代码分支。
- 代码提交仍走各自工作分支，分发方负责验收与合入；
  **消息提交是三方唯一允许触及 main 的例外，且仅限自己那份消息文件**。

## 二、消息格式

每条消息一个块，由脚本 send 生成，勿手写：

    ### [ID] 时间戳 发送方 -> 接收方 . 类型 (reply-to: 原ID)
    正文

- ID：身份 + 秒级时间戳 + 6 位随机，全局唯一，用于去重。
- to：a / b / c / dispatcher / all。
- kind：question / answer / report / task / broadcast。
- reply-to：可选，串起同一话题。

## 三、共用脚本

scripts/doc_bus.py，四个子命令（四方同版同参）：

| 子命令 | 用途 |
|---|---|
| init --me X | 校验游标与四份消息文件是否齐全 |
| read --me X | 一次性打印所有未读消息并推进游标 |
| wait --me X [--round 60] [--tick 10] | 单轮监听 |
| send --me X --to Y --kind K --text T [--reply-to ID] | 发消息 |

wait 节奏：单轮统一 40 秒（`--round 40 --tick 10`），立即探测一次、之后每 10 秒探测一次；
**有更新立即打印并返回（HIT）**；满一轮无更新打印 NO_UPDATE 后退出本轮。
单轮返回后立即由下一轮调用续跑，严禁因 NO_UPDATE 或轮询次数停止；仅工作全部完成或明确停止指令可停（见 START_HERE 6.1）。
桥接会话重唤起先 read 补读再续跑；不在单个进程里一次傻等超过 60 秒上限。

send 的实现：用 git 底层对象（临时 index + commit-tree）构造只含自己那份文件的提交并推送，
全程不依赖当前 HEAD 与工作区状态；并发 push 被拒时自动基于最新 main 重建重试最多 3 次，
不丢他人消息。游标按身份分文件存于 git 内部目录、不入库（同一克隆里四方各读各的，不互相吞消息），跨轮跨会话按 ID 去重；发消息成功后，仅当当前检出分支就是 main 时，脚本用标准 git merge --ff-only 把本地 main 快进到刚推送的提交（index 与工作树一起同步）；本地有未提交改动无法快进时打印 SYNC_SKIPPED、不强行改动。仓库 .gitattributes 固定 docs/bus/*.md 与脚本为 eol=lf，消除 Windows autocrlf 行尾噪声。在 work/ai-* 等工作分支上脚本不动本地任何东西，消息由下次 fetch/rebase 自然带入。

## 四、规则边界

- 技术问答、进度同步：三方与分发方可在总线里直接互相对话，不必经分发方代传。
- 任务下发、验收结论、合入 main、阶段 3 删除动作：**只归分发方**，
  只认 docs/bus/dispatcher.md 里的裁定。
- 三方不直推代码到 main、不自填 [答复]、不改他人文件、不自行开工未下发任务。
- 分发方不替三方写代码、不代传技术问答。

## 五、新会话启动流程（四方通用）

1. git fetch origin --prune
2. 读 docs/collaboration-bus.md、docs/work-dispatcher.md、docs/work-board.md 与自己的任务书
3. python scripts/doc_bus.py read --me X   （读完四方未读消息）
4. python scripts/doc_bus.py init --me X   （确认四份消息文件齐全）
5. 连续起 `python scripts/doc_bus.py wait --me X --round 40 --tick 10`；单轮返回立即起下一轮，不因 NO_UPDATE 停止（见 START_HERE 6.1）
6. 需要发言时用 send，引用原消息 ID 便于串话题

## 六、与既有状态的关系

本机制只改「通信方式」，不改阶段状态：阶段 2 整体收口、阶段 3 三条前置
（真实使用跑够时间 / 六项逐一验证 / 旧路径无调用方）仍以 docs/work-board.md 末节为准；
A-5 / B-6 / C-6 仍为准备取证任务，删除动作三条同时满足前不下发。


## 补记：行尾根因与 bytes stdin（2026-11-13）

三层逐字节诊断确认：HEAD 与 index 中的消息文件 blob 曾为 CRLF、工作树为 LF，
git status 因此持续判 modified。根因不在 ff-only 同步，也不在 .gitattributes，
而在脚本 git() 封装以 text=True 向 git hash-object -w --stdin 传内容时，
Windows 下 Python 把 LF 转成 CRLF 写进 blob —— 每次 send 都在生成 CRLF 对象。
修复：git() 改用 bytes stdin 与 bytes 捕获（输出手动 utf-8 decode），
show_remote 只读 stdout 并归一换行；既有四份消息文件经 git add --renormalize 统一为 LF。
此后 send 生成的 blob、index、工作树三者同为 LF，status 保持干净。


## 补记：单一入口与身份判定（2026-11-13）

- **唯一入口改为 docs/START_HERE.md**：历史对话里四份分身份启动提示词一律作废；
  所有 AI 新会话只贴一句通用引导语（见 START_HERE 第 0 节）即可开工。
- 身份不再靠提示词注入：按当前分支判定，用 `python scripts/doc_bus.py whoami` 确认；
  main→dispatcher、work/ai-a→a、work/ai-b→b、work/ai-c→c，其它→unknown（停下问）。
- 「感知处境与进度」= START_HERE 第 2 节快照 + 启动时 read 全部总线消息 +
  work-board / work-dispatcher 末节台账 + fetch 后实时分支尖端，不写死提交号。
- 本协议其余规则不变：技术问答直接对，任务/验收/合入只归分发方。


## 补记：同一份入口文档如何区分 A/B/C（2026-11-13）

- 四方读同一份 docs/START_HERE.md；身份**不靠提示词、不靠文件**，靠各自会话当前检出的 git 分支
  （whoami：main→dispatcher、work/ai-a→a、work/ai-b→b、work/ai-c→c）。
- 成立前提：新 clone 默认在 main，执行方必须先按 START_HERE 第 1.1 节切到自己分支再 whoami；
  判出 dispatcher 而自己是执行方即停下，不以错身份开工。
- 共用同一检出目录时分支区分失效：用环境变量 DOC_BUS_ACTOR 显式指定，whoami 优先读它；
  也支持 --expect 自检（不符返回非零）。
- 通用引导语不变，仍是一句；协议其余规则不变。


## 补记：入口文档必须出现在 work 分支（2026-11-13）

- 事故：START_HERE / doc_bus / 四份消息文件 / 最新台账 / A-5-B-6-C-6 任务书末节全在 main 上新增，
  三条 work 分支尖端仍停在阶段 2 那笔，执行方切过去读不到入口文档，也读不到自己的新任务。
- 修复：三条 work 分支本就是 origin/main 的祖先（其提交已合入 main），由分发方纯快进到 origin/main；
  零冲突、零代码改动、不动三方已有文件，性质是通信基础设施下发而非代写交付。
- 长期自愈：START_HERE 第 1.2 节规定新会话切分支后先 `git merge --ff-only origin/main`
  （或 rebase/merge），保证本地文档真源不落后；doc_bus 固定读 origin/main 不受影响。
- 通用引导语不变，仍是一句。
