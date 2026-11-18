# R4 逐笔对拍：config_draft_store.py 三锚内容级 diff 取证

> 用途：按 dispatcher-20261118T160230-941ad1，对 23 件清单第 3 条登记的 flask_server/config_draft_store.py 做三锚内容级 diff 取证，供分发方 R4 逐笔裁定。只读取证，不改任何实现，不新增对拍路径；逐笔合入裁定仍归分发方，结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变。

## 一、三锚与解析情况

- old = 1e80680：本仓可解析（与 origin/legacy/old-stable 同指），该文件 112 行实存、blob d6fa05345d6d。
- bus = 32e83dd：本仓 cat-file -t 报 Not a valid object name、ref 列表无 bus 引用；经同级交付仓（仓名 chat-bridge-bus，按仓名定位、不登记工程外绝对路径）解析为 commit 32e83dd1fcca251c7d14bbb613f7d891d75e99ae（Merge remote-tracking branch origin/master），该文件 112 行实存、blob d6fa05345d6d。
- main = origin/main 当前尖端（取证时 8d7a03e）：该文件 MISSING，调用方引用亦零命中。

分发方 docs/r4-perfile-blob-evidence.md 第 3 条登记该路径 old blob = bus blob = d6fa05345d6d、main 缺；与本轮逐行 diff 结论互印。docs/work-board.md L155 第 3 条登记为 23 件清单实现面，L198 裁定输入表记 old/bus 同 blob、内容一致、待内容级抽查与合入裁定。

## 二、三锚 blob 哈希与文件实存（实测）

| 锚 | 文件 | 行数 | blob |
|---|---|---|---|
| old 1e80680 | flask_server/config_draft_store.py | 112 | d6fa05345d6d |
| bus 32e83dd | flask_server/config_draft_store.py | 112 | d6fa05345d6d |
| main 8d7a03e | flask_server/config_draft_store.py | MISSING | MISSING |

三锚解析 3/3、实存判定 3/3。文件首行文档字符串为按 siteKey 隔离的后端草稿与改完即时生效、不写母版 yaml：界面改值存该站草稿并立即 apply 到 runtime.CONFIG，点覆盖才写母版并清草稿；old 与 bus 前 10 行逐行一致。

## 三、三态分母（自带实测）

| 态 | 分母 | 实测方式 |
|---|---|---|
| old/bus 一致行数 | 112 | difflib.SequenceMatcher 逐行比对，matching blocks 合计 112 行 |
| old/bus 差异块数 | 0 | opcode 序列全为 equal，无 insert / delete / replace 块 |
| main 缺失行数 | 112 | main 下该文件整件缺，bus 全部 112 行相对 main 均为新增面 |

old 与 bus 各 112 行逐行同源，+0/-0，opcode 全 equal。bus 相对 main 的新增面即整文件 112 行；main 侧 4 处调用方引用同样缺失。该文件属配置刷新链实现面，与 docs/gbc-gap-criteria.md 配置刷新缺口的取证路径有关联；本附录只登记关联，不越界判定缺口 pass/fail。

## 四、调用方命中位置（引用链留痕，非新增对拍路径）

old 与 bus 两侧各 4 处命中、位置逐行一致，main 侧 0 处：

| 序号 | 命中位置 | 内容 |
|---|---|---|
| 1 | flask_server/routes/config_route.py:29 | import config_draft_store as draft_store |
| 2 | flask_server/tests/js/test_config_cache_global.test.js:34 | fs.existsSync 断言该实现文件存在 |
| 3 | flask_server/tests/js/test_config_draft_isolation.test.js:28 | 读取该实现文件正文做隔离断言 |
| 4 | flask_server/tests/test_config_draft.py:6 | import config_draft_store as ds |

上述位置是调用链与测试夹具的位置留痕，不构成 23 件清单之外的新增对拍对象；该路径已登记在 docs/work-board.md 的 23 件清单第 3 条，清单口径不变。

## 五、口径差与外部材料（如实登记）

1. docs/work-board.md L155 第 3 条分母列写「三树交集件」，分发方 16:00:34 广播已裁定该措辞指 old 与 bus 两树交集、相对 main 缺失，不表示 main 已含，表本体不改、末节追加裁定为准；15:48 广播独立复核亦确认该路径在 main 树缺失。本轮实测 main 下确为 MISSING，支持该裁定，本附录不改台账、不代判。
2. 外部页面样本此前 10 个链接解析服务全部失败，站点集属 a 的 P2 配置跨站现场样本范围（a.com / b.com / new.com / kimi.com 与 www.kimi.com / 127.0.0.1:5000 / qianwen.com / chat.deepseek.com / yuanbao.tencent.com / hf-mirror.com），与 c 本笔取证无关，不据此推断任何页面事实。本附录取证只依赖 git 冻结锚与工程内相对路径。
3. 本附录是 23 件逐笔内容级 diff 的第 3 笔取证底稿，不替代逐笔合入裁定；结论源 0/23 保持不变。

## 六、复核结论

- 三锚解析 3/3、实存判定 3/3；三态分母 3/3 逐项可核：一致 112 行 / 差异块 0 / main 缺失 112 行，+0/-0。
- 调用方命中 old 4/4、bus 4/4、main 0，位置逐行一致；blob d6fa05345d6d 双证闭合。
- 结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变；逐笔裁定由分发方按 R4 走查推进。
