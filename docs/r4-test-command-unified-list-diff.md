# R4 逐笔对拍：test_command_unified_list.test.js 三锚内容级 diff 取证

> 用途：按 dispatcher-20261118T191638-f1b0f3，对 23 件清单测试面第 6 条登记的 flask_server/tests/js/test_command_unified_list.test.js 做三锚内容级 diff 取证，供分发方 R4 逐笔裁定。本片为测试面第 3 件（接在 test_command_restore_btn 与 test_command_restore_fixes 之后）、第 7 笔内容级 diff 底稿。只读取证，不改任何实现，不新增对拍路径；逐笔合入裁定仍归分发方，结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变。

## 一、三锚与解析情况

- old = 1e80680：本仓可解析（与 origin/legacy/old-stable 同指），该文件 80 行实存、blob 919436945189。
- bus = 32e83dd：本仓 cat-file -t 报 Not a valid object name、ref 列表无 bus 引用；经同级交付仓（仓名 chat-bridge-bus，按仓名定位、不登记工程外绝对路径）解析为 commit 32e83dd1fcca251c7d14bbb613f7d891d75e99ae（Merge remote-tracking branch origin/master），该文件 80 行实存、blob 919436945189。
- main = origin/main 当前尖端（取证时 bbbfdc9）：该文件 MISSING。

文件为 C-7 指令区统一列表 + 行内编辑的回归测试：node:test 与 node:assert、P 指向 extend/dialog/parts、R 指向工程根、Vue h stub、window.AIMirrorDialog 与 postMessage stub、require 08f_commands.js 与 01c_bridge_cmd.js，old 与 bus 前 10 行逐行一致。分发方 docs/r4-perfile-blob-evidence.md 第 6 条（L13）、docs/work-board.md L158 与 L201 第 6 条登记 old blob = bus blob = 919436945189、main 缺，与本轮逐行 diff 结论互印。

## 二、三锚 blob 哈希与文件实存（实测）

| 锚 | 文件 | 行数 | blob |
|---|---|---|---|
| old 1e80680 | flask_server/tests/js/test_command_unified_list.test.js | 80 | 919436945189 |
| bus 32e83dd | flask_server/tests/js/test_command_unified_list.test.js | 80 | 919436945189 |
| main bbbfdc9 | flask_server/tests/js/test_command_unified_list.test.js | MISSING | MISSING |

三锚解析 3/3、实存判定 3/3。

## 三、三态分母（自带实测）

| 态 | 分母 | 实测方式 |
|---|---|---|
| old/bus 一致行数 | 80 | difflib.SequenceMatcher 逐行比对，matching blocks 合计 80 行 |
| old/bus 差异块数 | 0 | opcode 序列全为 equal，无 insert / delete / replace 块 |
| main 缺失行数 | 80 | main 下该文件整件缺，bus 全部 80 行相对 main 均为新增面 |

old 与 bus 各 80 行逐行同源，+0/-0，opcode 全 equal。bus 相对 main 的新增面即整文件 80 行。

## 四、对象分列：附录行数与被取证目标文件行数（task 第 1 点硬要求）

| 对象 | 行数 | 说明 |
|---|---|---|
| 被取证目标文件 flask_server/tests/js/test_command_unified_list.test.js | old 80 / bus 80 | 冻结锚下的测试夹具，三态分母 80/0/80 依附于此对象 |
| 本附录 docs/r4-test-command-unified-list-diff.md | 76 | c 本笔产出的纯 docs 取证附录，行数按交付轮 splitlines 实测 |

两个对象不同、分母语言不同，分列登记、不混用。本条为 task 第 1 点新增硬要求，起因是分发方 19:16:50 广播第 2 点对上一笔回帖「附录 63 行被误写成目标文件 58 行」的对象错标更正：分发方实测上一笔附录 63 行、目标文件 58 行，两个数字对象不同、不构成矛盾，并声明「确认不等于背书」。19:19:28 广播第 2 点复用同一分列口径。本笔附录正文与回执均按此分列。

## 五、工程内引用命中位置（不变量 + 动态登记）

三树用扩展正则扫 test_command_unified_list 及等价词形，命中：old 0 / bus 0 / main 9。

- old 与 bus 冻结树内该文件为独立 node:test 夹具，无其他工程文件按名引用它，故 0 命中；不补写不存在的调用链。
- main 侧 9 条命中按命中文件路径判定全部落在 docs/ 下，是总线 / 台账 / 广播里的文本提及，逐条为：

- docs/bus/a.md:321 ：  flask_server/tests/js/test_command_unified_list.test.js 9194369451899906cfe76fe7565848e8bba3c7f2
- docs/bus/dispatcher.md:1601 ：4. 续派排期（本轮不叠单）：a = 145554（R0 逐文件裁定输入清单）、b = 190618 交付收口后新片、c = 测试面第 3 件（test_command_unified_list.te
- docs/bus/dispatcher.md:1615 ：【c · 当前在途片】flask_server/tests/js/test_command_unified_list.test.js 三锚内容级 diff 取证附录（单笔一次提交）。
- docs/bus/dispatcher.md:1626 ：3. 续派按队列实况收紧：a 的 dispatcher-20261118T145554-8650c1（R0 逐文件裁定输入清单）为已落库在途单，145117 的 P2 定位已收件，本轮不重发、不叠同题
- docs/bus/dispatcher.md:1634 ：1. 19:16 平稳绿灯：b 的 191626（R1 102 判定面逐笔取证）、c 的 191638（测试面第 3 件 test_command_unified_list.test.js 三锚 di
- docs/bus/dispatcher.md:1648 ：5. 队列三张在途、不叠单：a = 145554（R0 逐文件裁定输入清单，已落库，仅点名催接不重发；145117 P2 定位已收件登记）；b = 191626（R1 102 判定面逐笔取证）；c =
- docs/r4-perfile-blob-evidence.md:13 ：| 6 | flask_server/tests/js/test_command_unified_list.test.js | 919436945189 | 919436945189 | 一致 | 缺
- docs/work-board.md:158 ：| 6 | flask_server/tests/js/test_command_unified_list.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性
- docs/work-board.md:201 ：| 6 | flask_server/tests/js/test_command_unified_list.test.js | 一致 | old/bus 同 blob，内容一致；待内容级抽查与合入裁定

- 代码面引用 0 处：按命中文件路径判定，main 侧命中无一条以 flask_server/ 或 extend/ 开头，无任何模块按名 import 或读取该夹具；命中正文里出现的路径字样属文本提及，不计代码引用。文本提及与代码引用分列，不混作调用链留痕，也不构成 23 件清单之外的新增对拍对象。
- 计数口径：代码面零引用为不变量；docs 文本提及数随分发方总线广播自指登记增长属易变量，按当轮实测动态登记、不写死条数、不作硬校验、不凑调用链。与分发方 16:32 广播第 2 点、53df2e9 独立复核节同一口径；此前把提及数写死触发 MISMATCH 即停的教训已规避。

## 六、口径差与台账（如实登记）

1. docs/work-board.md L158 第 6 条「三树交集件」措辞已由分发方 16:00:34 广播裁定为 old 与 bus 两树交集、相对 main 缺失，不表示 main 已含，表本体不改、末节追加裁定为准；本轮实测 main 下确为 MISSING，支持裁定，本附录不改台账、不代判。
2. 实现面 3/3 取证链已闭合（08m_config_restore.js 075ec77、config_draft_store.py 418e258、system-prompt-lazy-load.md 3346846）；测试面第 1 件 test_command_restore_btn.test.js db3c4d6（合入 f04ae06）、第 2 件 test_command_restore_fixes.test.js 26334c0（合入 0ff7ebcd）已交，本片为测试面第 3 件。取证附录合入与取证链闭合均不等于逐笔合入裁定完成，结论源 0/23 保持不变。
3. e604e9d（docs: 增补分发方无人值守运行约定与续链口令）正文已补读闭合：改动仅 docs/work-dispatcher.md 共 282 行，主体为分发方职责约定、审核清单、交接说明与遗留登记；尾部 L259-282 为「给 a」「给 c」两段角色转贴话术收录，正文即 16:45 那轮空铃回帖模板（内嵌 main tip 277e23b / behind 100 为当时快照，与当前 e604e9d / behind 114 不同，按 commit 查、不误读为实时指令）。文档重申「任务下发、验收结论、合入 main 只认 docs/bus/dispatcher.md 裁定」「执行方只推自己分支、回执 reply-to 原任务 id」，未给出新 wait 口令；本笔续链仍按广播明文 wait --me c --round 5 --tick 10。
4. 本笔为补盲核到的在途单：上一轮 wait 回传 new=9 但正文被输出截断，c 的 dispatcher-20261118T191638-f1b0f3 已被游标消费、不再作为 UPDATE 推回；本轮按 origin/main 权威版本补读全文与三条后续广播（191650 / 191928 / 192113），确认该单在途、不叠单、无作废无覆盖，docs/r4-test-command-unified-list-diff.md 在 main 侧 ABSENT。19:21:13 广播第 2 点末句「/profiles 端点返回体是否全取 runtime.CONFIG 未逐行核」被输出截断，属分发方 P2 自留门限，不补全、不猜测。
5. 上一笔 2ec6f19 的 L45 行尾空格触发 git diff --cached --check rc=2 红灯；本笔按 task 第 1 点硬要求「提交前自跑 git diff --cached --check 须 rc=0、重点核行尾空白」，写入前逐行剥离行尾空白自检、cached-check 与文档同步钩子双验通过。
6. 本轮再附 11 个链接（a.com / b.com / chat.deepseek.com 与 /chat/abc / hf-mirror.com / kimi.com 与 www.kimi.com / new.com / qianwen.com / yuanbao.tencent.com / 127.0.0.1:5000）解析服务全部失败，站点集属 a 的 P2 配置跨站现场样本范围，与 c 本笔取证无关，不据此推断任何页面事实。本附录取证只依赖 git 冻结锚与工程内相对路径。
7. 本附录是 23 件逐笔内容级 diff 的第 7 笔取证底稿，不替代逐笔合入裁定。

## 七、复核结论

- 三锚解析 3/3、实存判定 3/3；三态分母 3/3 逐项可核：一致 80 行 / 差异块 0 / main 缺失 80 行，+0/-0。
- 对象分列：目标文件 old/bus 各 80 行，本附录 76 行，不混用。工程内引用命中 old 0 / bus 0 / main 9（文本提及 9、代码引用 0），按当轮实测动态登记；blob 919436945189 双证闭合。
- 结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变；逐笔裁定由分发方按 R4 走查推进。
