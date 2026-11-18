# R4 逐笔对拍：test_command_restore_btn.test.js 三锚内容级 diff 取证

> 用途：按 dispatcher-20261118T163351-1cbd5f，对 23 件清单第 4 条登记的 flask_server/tests/js/test_command_restore_btn.test.js 做三锚内容级 diff 取证，供分发方 R4 逐笔裁定。本片为测试面首件、第 5 笔内容级 diff 底稿。只读取证，不改任何实现，不新增对拍路径；逐笔合入裁定仍归分发方，结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变。

## 一、三锚与解析情况

- old = 1e80680：本仓可解析（与 origin/legacy/old-stable 同指），该文件 48 行实存、blob 2814d4dc0141。
- bus = 32e83dd：本仓 cat-file -t 报 Not a valid object name、ref 列表无 bus 引用；经同级交付仓（仓名 chat-bridge-bus，按仓名定位、不登记工程外绝对路径）解析为 commit 32e83dd1fcca251c7d14bbb613f7d891d75e99ae（Merge remote-tracking branch origin/master），该文件 48 行实存、blob 2814d4dc0141。
- main = origin/main 当前尖端（取证时 3e29414）：该文件 MISSING。

文件为指令编辑态还原按钮的回归测试：node:test 与 node:assert、require 08f_commands.js、Vue h stub 与按 class 收集节点的递归 find，old 与 bus 前 10 行逐行一致。分发方 docs/r4-perfile-blob-evidence.md 第 4 条（L11）、docs/work-board.md L156 与 L199 第 4 条登记 old blob = bus blob = 2814d4dc0141、main 缺，与本轮逐行 diff 结论互印。

## 二、三锚 blob 哈希与文件实存（实测）

| 锚 | 文件 | 行数 | blob |
|---|---|---|---|
| old 1e80680 | flask_server/tests/js/test_command_restore_btn.test.js | 48 | 2814d4dc0141 |
| bus 32e83dd | flask_server/tests/js/test_command_restore_btn.test.js | 48 | 2814d4dc0141 |
| main 3e29414 | flask_server/tests/js/test_command_restore_btn.test.js | MISSING | MISSING |

三锚解析 3/3、实存判定 3/3。

## 三、三态分母（自带实测）

| 态 | 分母 | 实测方式 |
|---|---|---|
| old/bus 一致行数 | 48 | difflib.SequenceMatcher 逐行比对，matching blocks 合计 48 行 |
| old/bus 差异块数 | 0 | opcode 序列全为 equal，无 insert / delete / replace 块 |
| main 缺失行数 | 48 | main 下该文件整件缺，bus 全部 48 行相对 main 均为新增面 |

old 与 bus 各 48 行逐行同源，+0/-0，opcode 全 equal。bus 相对 main 的新增面即整文件 48 行。

## 四、工程内引用命中位置（不变量 + 动态登记）

三树用扩展正则扫 test_command_restore_btn 及等价词形，命中：old 0 / bus 0 / main 6。

- old 与 bus 冻结树内该文件为独立 node:test 夹具，无其他工程文件按名引用它，故 0 命中；不补写不存在的调用链。
- main 侧 6 条命中按文件路径判定全部落在 docs/ 下，是总线 / 台账 / 广播里的文本提及，逐条为：

- docs/bus/a.md:319 ：  flask_server/tests/js/test_command_restore_btn.test.js 2814d4dc0141694d75edb8b85ca174713eaa4d77
- docs/bus/dispatcher.md:1541 ：【c · 当前在途片】flask_server/tests/js/test_command_restore_btn.test.js 三锚内容级 diff 取证附录（单笔一次提交）。
- docs/bus/dispatcher.md:1555 ：6. 三方当前有效单：c = dispatcher-20261118T163351-1cbd5f（test_command_restore_btn.test.js 三锚 diff 取证，测试面首件）；
- docs/r4-perfile-blob-evidence.md:11 ：| 4 | flask_server/tests/js/test_command_restore_btn.test.js | 2814d4dc0141 | 2814d4dc0141 | 一致 | 缺
- docs/work-board.md:156 ：| 4 | flask_server/tests/js/test_command_restore_btn.test.js | 测试面 | 三树 blob 比对 + 内容级 diff + 提交图可达性
- docs/work-board.md:199 ：| 4 | flask_server/tests/js/test_command_restore_btn.test.js | 一致 | old/bus 同 blob，内容一致；待内容级抽查与合入裁定

- 代码面引用 0 处：按命中文件路径判定，main 侧命中无一条以 flask_server/ 或 extend/ 开头，无任何模块按名 import 或读取该夹具；命中正文里出现的路径字样属文本提及，不计代码引用。文本提及与代码引用分列，不混作调用链留痕，也不构成 23 件清单之外的新增对拍对象。
- 计数口径：代码面零引用为不变量；docs 文本提及数随分发方总线广播自指登记增长属易变量，按当轮实测动态登记、不作硬校验、不凑调用链。与分发方 16:32 广播第 2 点、53df2e9 独立复核节同一口径。

## 五、口径差与台账（如实登记）

1. docs/work-board.md L156 第 4 条「三树交集件」措辞已由分发方 16:00:34 广播裁定为 old 与 bus 两树交集、相对 main 缺失，不表示 main 已含，表本体不改、末节追加裁定为准；本轮实测 main 下确为 MISSING，支持裁定，本附录不改台账、不代判。
2. 实现面 3/3 取证链已闭合（task 第 2 点口径：08m_config_restore.js 075ec77、config_draft_store.py 418e258、system-prompt-lazy-load.md 经 L45 格式修复重出）；本片为测试面首件。取证附录合入与取证链闭合均不等于逐笔合入裁定完成，结论源 0/23 保持不变。
3. 上一笔 L45 行尾空格触发 git diff --cached --check rc=2 红灯；本笔按 task 第 1 点硬要求，提交前自跑 git diff --cached --check 须 rc=0，且附录写入前逐行剥离行尾空白自检，不带 trailing whitespace。
4. 本轮无新增页面材料；此前 11 个链接（a.com / b.com / chat.deepseek.com 与 /chat/abc / hf-mirror.com / kimi.com 与 www.kimi.com / new.com / qianwen.com / yuanbao.tencent.com / 127.0.0.1:5000）解析服务全部失败，站点集属 a 的 P2 配置跨站现场样本范围，与 c 本笔取证无关，不据此推断任何页面事实。本附录取证只依赖 git 冻结锚与工程内相对路径。
5. 本附录是 23 件逐笔内容级 diff 的第 5 笔取证底稿，不替代逐笔合入裁定。

## 六、复核结论

- 三锚解析 3/3、实存判定 3/3；三态分母 3/3 逐项可核：一致 48 行 / 差异块 0 / main 缺失 48 行，+0/-0。
- 工程内引用命中 old 0 / bus 0 / main 6（文本提及 6、代码引用 0），按当轮实测动态登记；blob 2814d4dc0141 双证闭合。
- 结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变；逐笔裁定由分发方按 R4 走查推进。
