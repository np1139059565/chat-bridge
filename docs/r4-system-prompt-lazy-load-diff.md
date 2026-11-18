# R4 逐笔对拍：system-prompt-lazy-load.md 三锚内容级 diff 取证

> 用途：按 dispatcher-20261118T161255-f52e11，对 23 件清单第 1 条登记的 docs/system-prompt-lazy-load.md 做三锚内容级 diff 取证，供分发方 R4 逐笔裁定。只读取证，不改任何实现，不新增对拍路径；逐笔合入裁定仍归分发方，结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变。

## 一、三锚与解析情况

- old = 1e80680：本仓可解析（与 origin/legacy/old-stable 同指），该文件 53 行实存、blob d26f8748c1f4。
- bus = 32e83dd：本仓 cat-file -t 报 Not a valid object name、ref 列表无 bus 引用；经同级交付仓（仓名 chat-bridge-bus，按仓名定位、不登记工程外绝对路径）解析为 commit 32e83dd1fcca251c7d14bbb613f7d891d75e99ae（Merge remote-tracking branch origin/master），该文件 53 行实存、blob d26f8748c1f4。
- main = origin/main 当前尖端（取证时 e3bf5f6）：该文件 MISSING。

文件为 System Prompt 按需加载优化方案（已实施）文档，首行起记录 2026-11-11 用户指令启动、前端刷新扩展与后端进程级重启后生效、read_file 模式开关修复与单测 11 项等实施前置。old 与 bus 前 10 行逐行一致。分发方 docs/r4-perfile-blob-evidence.md 第 1 条、docs/work-board.md L153 与 L196 第 1 条登记 old blob = bus blob = d26f8748c1f4、main 缺，与本轮逐行 diff 结论互印。

## 二、三锚 blob 哈希与文件实存（实测）

| 锚 | 文件 | 行数 | blob |
|---|---|---|---|
| old 1e80680 | docs/system-prompt-lazy-load.md | 53 | d26f8748c1f4 |
| bus 32e83dd | docs/system-prompt-lazy-load.md | 53 | d26f8748c1f4 |
| main e3bf5f6 | docs/system-prompt-lazy-load.md | MISSING | MISSING |

三锚解析 3/3、实存判定 3/3。

## 三、三态分母（自带实测）

| 态 | 分母 | 实测方式 |
|---|---|---|
| old/bus 一致行数 | 53 | difflib.SequenceMatcher 逐行比对，matching blocks 合计 53 行 |
| old/bus 差异块数 | 0 | opcode 序列全为 equal，无 insert / delete / replace 块 |
| main 缺失行数 | 53 | main 下该文件整件缺，bus 全部 53 行相对 main 均为新增面 |

old 与 bus 各 53 行逐行同源，+0/-0，opcode 全 equal。bus 相对 main 的新增面即整文件 53 行。

## 四、工程内引用命中位置（如实分列，按当轮实测动态登记）

三树用扩展正则扫 system-prompt-lazy-load 及等价词形，命中：old 0 / bus 0 / main 11。

- old 与 bus 冻结树内该文档为独立方案文档，无其他工程文件 import 或读取它，故 0 命中；不补写不存在的调用链。
- main 侧 11 条命中全部在 docs/ 下，是总线 / 台账 / 广播里的文本提及，逐条为：

- docs/bus/a.md:88:  docs/system-prompt-lazy-load.md d26f8748c1f4f1b5b086a5e3ee7934aa1c8eaec2
- docs/bus/c.md:80:【可自动合并】c 删 18 份全是 3号独有（∩1号 09ef553 = 0，∩2号按 a 清单 = 0），与 1→3 的 51 项搬入、1号独有 2 项（card_bus.py / test_card_bus_and_priority.py）保留零交叠 → 解耦成
- docs/bus/dispatcher.md:1471:【c · 当前在途片】docs/system-prompt-lazy-load.md 三锚内容级 diff 取证附录（单笔一次提交）。
- docs/bus/dispatcher.md:1472:1. 范围：以 old@1e80680、bus@32e83dd、main 当前尖端为三锚，逐行比对该文件在 old 与 bus 的内容差异、bus 相对 main 的新增面，产出 docs/r4-system-prompt-lazy-load-
- docs/bus/dispatcher.md:1481:2. c 的回执 c-20261118T160743-9082f9（reply-to dispatcher-20261118T160230-941ad1）已在远端 docs/bus/c.md；docs/r4-config-draft-store
- docs/bus/dispatcher.md:1485:6. 三方当前有效单：c = dispatcher-20261118T161255-f52e11（system-prompt-lazy-load.md 三锚 diff 取证）；a = 145117 → 145554 两片；b = 145130 
- docs/bus/dispatcher.md:1492:2. c 的 16:07 回执 c-20261118T160743-9082f9 对应交付已合入 418e258（docs/r4-config-draft-store-diff.md 在 main）；当前有效单 dispatcher-20261
- docs/bus/dispatcher.md:1493:3. R4 实现面取证链已合 2/3：08m_config_restore.js 075ec77、config_draft_store.py 418e258；第 1 件 system-prompt-lazy-load.md 在途。取证附录合入不
- docs/r4-perfile-blob-evidence.md:8:/ 1 / docs/system-prompt-lazy-load.md / d26f8748c1f4 / d26f8748c1f4 / 一致 / 缺 /
- docs/work-board.md:153:/ 1 / docs/system-prompt-lazy-load.md / 实现面 / 三树 blob 比对 + 内容级 diff + 提交图可达性 / 1/1 路径在冻结锚可解析（三树交集件） / 待逐笔裁定 /
- docs/work-board.md:196:/ 1 / docs/system-prompt-lazy-load.md / 一致 / old/bus 同 blob，内容一致；待内容级抽查与合入裁定 / 待逐笔裁定 /

- 代码引用 0 处：main 侧命中无一条落在 flask_server/ 或 extend/ 下，无任何模块 import、无代码读取该文件。文本提及与代码引用分列，不混作调用链留痕，也不构成 23 件清单之外的新增对拍对象。
- 计数口径说明：main 侧文本提及数随分发方总线广播自指登记增长（前一轮 9 条，本轮 11 条，增量为 16:16 状态广播自身提及本笔），属台账文字而非取证分母；三态分母与 old/bus 命中 0 不随其变化。本附录只按当轮实测登记，不写死条数、不凑调用链。

## 五、实现面 3/3 取证链与口径差（如实登记）

1. 实现面 3/3 取证链闭合：第 1 件本笔 docs/system-prompt-lazy-load.md；第 2 件 extend/dialog/parts/08m_config_restore.js（c 的 052d502，已合入 main 075ec77）；第 3 件 flask_server/config_draft_store.py（c 的 d4a4c16，已合入 main 418e258）。取证链闭合不等于逐笔合入裁定完成，结论源 0/23 保持不变。
2. docs/work-board.md L153 第 1 条「三树交集件」措辞已由分发方 16:00:34 广播裁定为 old 与 bus 两树交集、相对 main 缺失，不表示 main 已含，表本体不改、末节追加裁定为准；本轮实测 main 下确为 MISSING，支持裁定，本附录不改台账、不代判。
3. 交付过程留痕：前一轮脚本把 main 文本提及数写死为 9 作硬校验，main 前进后自指登记增至 11 触发 MISMATCH 即停，未提交、未推送、未回执；本轮改按「不变量 + 当轮实测动态登记」复跑，三态分母与 blob 未改、不编数。
4. 随回传再附 10 个页面链接，解析服务仍全部失败，站点集属 a 的 P2 配置跨站现场样本范围（a.com / b.com / chat.deepseek.com / kimi.com / new.com / qianwen.com / www.kimi.com / yuanbao.tencent.com / 127.0.0.1:5000 / hf-mirror.com），与 c 本笔取证无关，不据此推断任何页面事实。本附录取证只依赖 git 冻结锚与工程内相对路径。
5. 本附录是 23 件逐笔内容级 diff 的第 4 笔取证底稿，不替代逐笔合入裁定。

## 六、复核结论

- 三锚解析 3/3、实存判定 3/3；三态分母 3/3 逐项可核：一致 53 行 / 差异块 0 / main 缺失 53 行，+0/-0。
- 工程内引用命中 old 0 / bus 0 / main 11（文本提及 11、代码引用 0），按当轮实测动态登记、不凑调用链；blob d26f8748c1f4 双证闭合。
- 实现面 3/3 取证链闭合；结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变；逐笔裁定由分发方按 R4 走查推进。
