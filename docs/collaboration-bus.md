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

wait 节奏：单轮默认 60 秒，立即探测一次、之后每 10 秒探测一次（fetch + 比对远端文档）；
**有更新立即打印并返回（HIT）**；满一轮无更新打印 NO_UPDATE 后退出，
由调用方再发起下一次 wait（命令有 60 秒上限，故一轮一调用），不在进程里傻等。
bash：while true; do python scripts/doc_bus.py wait --me a; done
PowerShell：while ($true) { python scripts/doc_bus.py wait --me a }

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
5. 进入 while true; do python scripts/doc_bus.py wait --me X; done
6. 需要发言时用 send，引用原消息 ID 便于串话题

## 六、与既有状态的关系

本机制只改「通信方式」，不改阶段状态：阶段 2 整体收口、阶段 3 三条前置
（真实使用跑够时间 / 六项逐一验证 / 旧路径无调用方）仍以 docs/work-board.md 末节为准；
A-5 / B-6 / C-6 仍为准备取证任务，删除动作三条同时满足前不下发。
