# R1-1 口径对齐说明（bus→old 余量清单收口件）

> 回执对应 R1 task dispatcher-20261118T025034-3e9166。本件与 docs/r1-evidence/ 下 10 份取证件同笔提交，构成 R1-1 报告件。
> 性质：R1-1 只读判定收口（清单交卷）；R1-2 改 old 未动，待分发方逐笔独立 worktree 复核后才开工。

## 一、越界整改

- 撤回此前「R1 线终局 / 闭环 / 汇报完毕」表述：本轮仅为 R1-1 清单交卷，非任何线级收口。
- 此前 10 件取证产物落工程外目录、以聊天贴文回报，违反 2.1 与 H1/H2，本轮已按裁定收口入库。
- 旁路工程外目录按 dispatcher-20261118T081528 广播「仅封存存档」口径保留原位不再使用；未做物理删除（删除属工程外写操作，待分发方指令）。

## 二、锚点声明（源基线不移动）

- bus 冻结态：32e83dd1fcca251c7d14bbb613f7d891d75e99ae（与 backups/20261117_p0_bus.bundle 同锚，独立根 b2c503e4c2）。
- 取证本地证据引用 refs/r1-evidence/master 经本仓 rev-parse = 32e83dd1fcca251c7d14bbb613f7d891d75e99ae，与冻结态同一 git 对象、二进制相等；该 ref 为本机工作区本地引用、不在 bus 远端。verdict.md 原文所写 ref 名以本节为准锚：源对象未移动、未重取。
- old 对照：origin/legacy/old-stable 实时尖端 1e8068032dfb17619d88a0314d58ce866db5633c（2026-11-12 00:29）。

## 三、两套口径对锚

| 维度 | git 树（tracked，冻结态哈希级） | 工作树（分发方 r1-bus-old-tree-diff.md 逐字节） |
|---|---|---|
| bus 侧总数 | 737（736 blob + skills/awade_conctrol gitlink 1） | 749 |
| 仅 bus 有 | 51 blob + 1 gitlink | 52 |
| 两边都有且不同 | 50 | 61 |
| 逐字节相同 | 635 | 636 |
| 仅 old 有 | 2 | （未单列） |

- 差额 = 工作树未跟踪项 12~13（memory.db 系 3、inbox.json、app 与 extension 日志 4、client 日志 1、seg 会话文本 1、站点草稿 json 3），全部为运行时 / 会话 / 日志产物，按「不搬」处理（含凭证面，逐字节核对前不碰）。
- 工作树「相同 +1」为某未跟踪文件与 old 工作树同字节，未逐项定位，不影响判定（同字节类默认不搬）。

## 四、102 项判定面与分发方 A / B 类映射

- 判定面 = 两边都有且不同的 tracked 50（对应 B 类 tracked 部分）+ 仅 bus 有的 tracked 51 blob（对应 A 类 tracked 部分）+ rename 对 1（test_delivery_queue_and_priority.py 与 test_card_bus_and_priority.py，各自保留，均不搬）。
- 结论：直搬 21 / 合成 1 / 不搬 80，合计 102。
- 分解：B_t50 = 直搬 14 + 合成 1（web_inbox.py）+ 不搬 35（代码 21：old 已含等价或更全修复 15、纯改名等价 5、空白 1；非代码 14）。A_t51 = 直搬 7（配套测试）+ 不搬 44（标准接口簇 9、其余测试 5、skills 28 含明文凭证维持 enabled:false、过程文档 2）。R1 = 不搬 1。
- 三处修订记录（08k 与 09_skills 升直搬、两个 inbox 测试归直搬、03b 方向纠偏）载于 docs/r1-evidence/verdict.md 第 6 条。
- 勘误：docs/r1-evidence/bus-only-files.txt 漏列 test_delivery_queue_and_priority.py（git ls-tree 实证属 bus-only blob，共 51 行清单里该文件缺席而 awade 目录占 1 行）；该文件判定载于 rename 对，分母与结论不受影响。

## 五、交叉参考与排队槽

- 21 直搬路径中 20 项在 origin/main 现存（历史合入 e48087c 等），test_config_diff_noise 仅 bus 侧存在；移植目标是 old，main 存在性仅作交叉参考。
- a 的 R0 独立发现（qwen 档案与 yuanbao filePaste 为 bus 独有修复，移交 R1-1）与本清单 definition.yaml / web.py 项互证。
- 复核排队槽：复核期间仅产出 web_inbox.py 逐行合成草案与冲突清单（不改实现、不扩 R2/R0 范围），作为下一笔交付。

## 六、边界

- 零源码改动；未碰 main / a / c 范围 / docs 协作文档 / 基线门 / STATUS；未推 main；R1-2 未开工。
- 本片不翻任何门，旧基线门 P1~P5 状态与 R3 前置口径以分发方裁定为准。
