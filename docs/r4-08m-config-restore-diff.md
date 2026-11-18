# R4 逐笔对拍：08m_config_restore.js 三锚内容级 diff 取证

> 用途：按 dispatcher-20261118T154401-61d182，对 23 件清单第 2 条登记的 extend/dialog/parts/08m_config_restore.js 做三锚内容级 diff 取证，供分发方 R4 逐笔裁定。只读取证，不改任何实现，不新增对拍路径；逐笔合入裁定仍归分发方，结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变。

## 一、三锚与解析情况

- old = 1e80680：本仓可解析（与 origin/legacy/old-stable 同指），该文件 58 行 / 3047 bytes 实存。
- bus = 32e83dd：本仓 git cat-file -t 报 Not a valid object name、rev-parse 报 Needed a single revision，本仓 ref 列表无 bus 相关引用；经同级交付仓（仓名 chat-bridge-bus，按仓名定位）解析为 commit 32e83dd1fcca251c7d14bbb613f7d891d75e99ae（Merge remote-tracking branch origin/master），该文件 58 行实存。仓名登记，不写工程外绝对路径。
- main = origin/main 当前尖端（取证时 1bc1abd）：该文件 MISSING，调用方引用亦零命中。

历史总线曾记 32e83dd 对象本机不可读；本轮是经同级交付仓解析得到，属视角与时点差，如实登记、不翻旧结论。分发方 docs/r4-perfile-blob-evidence.md 第 2 条登记该路径 old blob = bus blob = 0edc10bddc35，与本轮逐行 diff 结论互印。

## 二、三态分母（自带实测）

| 态 | 分母 | 实测方式 |
|---|---|---|
| old/bus 一致行数 | 58 | difflib.SequenceMatcher 逐行比对，matching blocks 合计 58 行 |
| old/bus 差异块数 | 0 | opcode 序列全为 equal，无 insert / delete / replace 块 |
| main 缺失行数 | 58 | main 下该文件整件缺，bus 全部 58 行相对 main 均为新增面 |

old 与 bus 各 58 行、逐行同源：文件首行为模块头注释，applyRestore 读 ctx.configCache 与 configBackend 做未覆盖改动批量还原。bus 相对 main 的新增面即整文件 58 行；main 侧 script 引入与两处测试引用同样缺失。

## 三、调用方命中位置（引用链留痕，非新增对拍路径）

old 与 bus 两侧各 4 处命中，位置逐行一致：

| 序号 | 命中位置 | 内容 |
|---|---|---|
| 1 | extend/dialog/dialog.html:75 | script 引入 parts/08m_config_restore.js |
| 2 | extend/dialog/parts/08m_config_restore.js:1 | 模块头注释（文件自身） |
| 3 | flask_server/tests/js/test_config_badge_restore.test.js:16 | require(P('08m_config_restore.js')) |
| 4 | flask_server/tests/js/test_config_badge_restore.test.js:131 | assert.ok(h.indexOf('08m_config_restore.js') >= 0) |

main 侧命中 0 处。上述位置是调用链与测试夹具的位置留痕，不构成 23 件清单之外的新增对拍对象；该路径已登记在 docs/work-board.md 的 23 件清单第 2 条，清单口径不变。

## 四、口径差与外部材料（如实登记）

1. docs/work-board.md L154 第 2 条分母列写「1/1 路径在冻结锚可解析（三树交集件）」，而 15:41 / 15:44 广播与 docs/r4-perfile-blob-evidence.md 汇总均写「main 侧 23 条均缺」。本轮实测 main 下该文件确为 MISSING，支持广播与 blob 底稿口径；表述张力由分发方裁定，本附录不改台账。
2. 随回传附的 10 个页面链接解析服务全部失败，站点集属 a 的 P2 配置跨站现场样本范围（a.com / b.com / new.com / kimi.com 与 www.kimi.com / 127.0.0.1:5000 / qianwen.com / chat.deepseek.com / yuanbao.tencent.com / hf-mirror.com），与 c 本笔取证无关，不据此推断任何页面事实。本附录取证只依赖 git 冻结锚与工程内相对路径。
3. 本附录是 23 件逐笔内容级 diff 的第 1 笔取证底稿，不替代逐笔合入裁定；结论源 0/23 保持不变。

## 五、复核结论

- 三锚解析 3/3（old 本仓、bus 同级交付仓、main 尖端），三态分母 3/3 逐项可核：一致 58 行 / 差异块 0 / main 缺失 58 行。
- 调用方命中 old 4/4、bus 4/4、main 0，位置逐行一致；blob 0edc10bddc35 双证闭合。
- 结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变；逐笔裁定由分发方按 R4 走查推进。
