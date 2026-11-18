# R4 逐笔对拍：rename pair 内容级 diff 取证

> 用途：按 dispatcher-20261118T155431-cbd6c5，对 23 件清单第 22 条登记的 rename pair 做三锚内容级 diff 取证，供分发方 R4 逐笔裁定。只读取证，不改任何实现，不新增对拍路径；逐笔合入裁定仍归分发方，结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变。

## 一、三锚与解析情况

- old = 1e80680：本仓可解析（与 origin/legacy/old-stable 同指），旧名文件 flask_server/tests/test_card_bus_and_priority.py 实存 141 行、blob c1b309accc44；同名新文件 MISSING。
- bus = 32e83dd：本仓 cat-file -t 报 Not a valid object name、ref 列表无 bus 引用；经同级交付仓（仓名 chat-bridge-bus，按仓名定位、不登记工程外绝对路径）解析为 commit 32e83dd1fcca251c7d14bbb613f7d891d75e99ae，新名文件 flask_server/tests/test_delivery_queue_and_priority.py 实存 141 行、blob fdbfb9acb944；旧名文件 MISSING。
- main = origin/main 当前尖端（取证时 4f35829）：新名文件实存 141 行、blob fdbfb9acb944；旧名文件 MISSING。

口径分列：分发方 docs/r4-perfile-blob-evidence.md 第 22 条按「路径」记 old c1b309accc44、bus 侧缺（old 单侧）；本轮按 rename pair 语义取到 bus 与 main 侧的新名对应文件 fdbfb9acb944。两张分母分列登记、不互相覆盖。docs/work-board.md L174 与 L217 已把该对登记为 old 单侧、rename pair 关联项、挂起待裁定；15:29 广播另提该对与 R1 冻结线关联，本附录只登记关联、不越界裁定 R1。

## 二、三锚 blob 哈希与文件实存（实测）

| 锚 | 旧名 test_card_bus_and_priority.py | 新名 test_delivery_queue_and_priority.py |
|---|---|---|
| old 1e80680 | c1b309accc44 | MISSING |
| bus 32e83dd | MISSING | fdbfb9acb944 |
| main 4f35829 | MISSING | fdbfb9acb944 |

四向文件实存判定 6/6 逐项可核；三锚解析 3/3。bus 与 main 侧新名文件 blob 同为 fdbfb9acb944。

## 三、逐行 diff 分母（自带实测）

| 比对 | 行数 | 一致行数 | 差异块数 | + 行 | - 行 |
|---|---|---|---|---|---|
| old-card vs bus-delivery | 141 / 141 | 128 | 12 | 13 | 13 |
| bus-delivery vs main-delivery | 141 / 141 | 141 | 0 | 0 | 0 |

old-card 与 bus-delivery 的 opcode 序列为 12 个 replace 夹 equal，无纯 insert / delete；12 个差异块全部是术语中性化替换：卡片总线与界面优先级→投递队列与界面优先级、card_bus→delivery_queue、CardBus→DeliveryQueue、_cards→_items、class TestCardBus→TestDeliveryQueue、import 模块名、unittest 运行命令说明与文档字符串中的类名。无测试语义增删。

bus-delivery 与 main-delivery 差异块 0、opcode 全 equal，blob 同为 fdbfb9acb944，即 bus 与 main 侧新名文件逐行同源。

## 四、测试名重叠面与覆盖判定

- old-card 12 个 test 名、bus-delivery 12 个、main-delivery 12 个，三侧名单一致：test_create_and_get、test_get_missing_returns_none、test_claim_pending_excludes_delivered、test_unconfirmed_can_be_claimed_repeatedly、test_confirm_idempotent、test_confirm_missing_returns_false、test_trim_keeps_unconfirmed、test_trim_reduces_size、test_enter_exit_counts、test_exit_not_below_zero、test_yield_no_wait_when_idle、test_yield_waits_when_active。
- 交集：old∩bus 12/12、old∩main 12/12、bus∩main 12/12；旧名被 main 覆盖 12/12。
- 覆盖判定（实测）：旧名文件在 bus 与 main 均 MISSING，不再以原名存在；对应新名文件 141 行、12/12 测试名全保留，差异仅为术语 / 类名 / 模块名 / 内部字段名中性化替换，无测试语义增删，且 bus 与 main 侧新文件逐行同源。即旧文件已由新名文件以 rename 加中性化改写形式覆盖。最终合入裁定仍归分发方 R4 逐笔走查，本附录不代判。

## 五、口径差与外部材料（如实登记）

1. 三锚 blob 底稿第 22 条按「路径」记 bus 缺，本轮按 rename pair 语义取到 bus 与 main 侧新名文件；两个分母分列，不互相覆盖，也不改写 docs/work-board.md 台账。
2. 随回传附的 10 个页面链接解析服务全部失败，站点集属 a 的 P2 配置跨站现场样本范围（a.com / b.com / new.com / kimi.com 与 www.kimi.com / 127.0.0.1:5000 / qianwen.com / chat.deepseek.com / yuanbao.tencent.com / hf-mirror.com），与 c 本笔取证无关，不据此推断任何页面事实。本附录取证只依赖 git 冻结锚与工程内相对路径。
3. 本附录是 23 件逐笔内容级 diff 的第 2 笔取证底稿，不替代逐笔合入裁定；结论源 0/23 保持不变。

## 六、复核结论

- 三锚解析 3/3、四向实存判定 6/6；逐行 diff 分母 old-card vs bus-delivery 一致 128 / 差异块 12 / +13 / -13，bus-delivery vs main-delivery 差异块 0。
- 测试名重叠 12/12，旧名被 main 覆盖 12/12，bus 与 main blob 同为 fdbfb9acb944。
- 结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变；逐笔裁定由分发方按 R4 走查推进。
