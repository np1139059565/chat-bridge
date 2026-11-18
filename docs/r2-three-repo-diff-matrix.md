# R2 段①：全三仓差异矩阵与 R1-1 交叉复核

> 角色 c，只读取证。reply-to dispatcher-20261118T025059-6b6d40。
> 不替代 b 的逐文件裁定；与 b 的「bus→old 单段视角」不重复，本片补 old→main 适配面与 bus→main 第三组。

## 一、对 b 的 R1-1 源材料独立交叉复核

输入：docs/r1-bus-old-tree-diff.md（156 行，分发方只读取证件，源 bus 冻结态 32e83dd、old 尖端 1e80680）。
复算：c 侧独立跑 git ls-tree -r 逐 blob 比对，bus 用同源冻结态 32e83dd（本机 cat-file -t=commit 可达），old 用实时尖端 1e80680；不采信 b 自述分母。

| 项 | b 清单（749 口径） | c 同源 tracked 树复算 | 差异归因 |
|---|---|---|---|
| bus 文件总数 | 749 | 737 | b 按冻结态工作树遍历，含 12 个运行时/未跟踪件 |
| 仅 bus 有 | 52 | 52 | 一致 |
| 仅 old 有 | 清单未列 | 2 | c 侧补列：flask_server 下 2 件 |
| 两边都有且不同 | 61 | 50 | 差 11：b 的 B 类含 memory.db / *.db-wal / 日志 / inbox.json / config/drafts 等运行时件，c 的 tracked 树中零命中 |
| 两边逐字节相同 | 636 | 635 | 差 1，与上述口径同源 |

定位证据：bus 工作树 919 文件、tracked@32e83dd 737、worktree-only 184（__pycache__ / runtime.yaml / config/drafts / 日志 / memory.db 等）；b 清单 B 类六类运行时件在 tracked 树中 tracked_hit=0；749 − 737 = 12 与「diff 差 11 + same 差 1」闭合。
判定：两组分母不是谁对谁错，是「冻结态工作树遍历」与「git tracked 树」两种取证口径；c 不改写 b 清单，只补同源复算列与归因。交叉复核 5 项分母全部取到实数，0 项「没查清」，0 项编数。
b 的「A / B 才进入逐文件裁定、C 默认不移植、main 大改面不往 old 搬、凭证不碰、禁整分支 merge」五条使用口径，c 复核为真，不改写。

## 二、全三仓视角差异矩阵（c 独立复算，实时 tracked 树）
## 二、全三仓视角差异矩阵（c 独立复算，实时树）

基点：bus c12f974（master，736 tracked 文件）/ old 1e80680（legacy/old-stable，687 文件）/ main 3f8e79b（work/ai-c，785 文件）。

| 组 | 仅左有 | 仅右有 | 共有 | 内容不同 | 逐字节相同 |
|---|---|---|---|---|---|
| bus → old | 51 | 2 | 685 | 50 | 635 |
| old → main | 24 | 122 | 663 | 113 | 550 |
| bus → main | 29 | 78 | 707 | 104 | 603 |

按目录分布（前二组）：

- bus_only_vs_old：skills 28 / flask_server 22 / docs 1；old_only_vs_bus：flask_server 2。
- bus_old_diff：flask_server 22 / extend 14 / docs 12 / scripts 1 / root 1。
- old_only_vs_main：flask_server 22 / docs 1 / extend 1；main_only_vs_old：flask_server 67 / skills 23 / extend 15 / docs 14 / scripts 3。
- old_main_diff：flask_server 55 / extend 31 / docs 19 / root 4 / scripts 2 / skills 2。

## 三、old→main 适配面（b 单段视角不含，本片补齐）

候选 = old 独有 24 件 + old/main 内容不同 113 件中落在 main 大改面目录的部分：

| 适配面目录 | 候选文件数 |
|---|---|
| flask_server/routes/ | 6 |
| flask_server/core/ | 9 |
| extend/lib/ | 0 |
| extend/dialog/ | 26 |
| docs/ | 20 |

判定：main 是破坏性大改，标准接口 / 会话 / 客户端注册 / 指令收归四类已在 main 落地，old 侧同路径件须服从新结构先做接口与目录适配再同步修复；extend/lib/ 候选 0 说明纯函数层无 old 侧遗留适配项。本表只给面与分母，逐文件取舍由 R3 承接、分发方复核。

## 四、分母

- 交叉复核：5/5 项有实数，0 项编数；口径差 5/5 项登记归因（同源冻结态 32e83dd）。
- 三仓矩阵：3/3 组取到 only/diff/same 全量分母。
- 适配面：5/5 个目录取到候选数。
- 本段未改任何实现代码、未碰 a/b 分支、未翻 STATUS。
