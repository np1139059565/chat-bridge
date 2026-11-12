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
- **准备任务 A-5 / B-6 / C-6：已下发，均未交、未推送**。三条 work 分支尖端仍停在阶段 2 那笔，
  即三方还没开工；准备任务不等于阶段 3 启动。
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
8. 空闲时**反复调用** `python scripts/doc_bus.py wait --me <actor>`
   （单轮 60 秒 / 内部 10 秒一探 / 有更新立即 HIT 返回 / NO_UPDATE 就再调一次）
9. 发言/交付用
   `python scripts/doc_bus.py send --me <actor> --to <a|b|c|dispatcher|all> --kind <question|answer|report> --text "..." [--reply-to ID]`；
   完成后 send 报「更新 git，X 完成，提交 <hash>」，回监听，不自找活、不自填 [答复]

## 5. 通信边界（详见 docs/collaboration-bus.md）

- 技术问答、进度同步：三方与分发方可在总线里直接互相对话，不必人工代传。
- 任务下发、验收结论、合入 main、阶段 3 删除动作：只归分发方，只认 docs/bus/dispatcher.md 裁定。
- 每人只写自己那份 docs/bus/<me>.md、只追加；不改他人文件、不直推代码到 main、不自填 [答复]。
