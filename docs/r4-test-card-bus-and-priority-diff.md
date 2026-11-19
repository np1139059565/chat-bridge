# R4 逐笔对拍：第 22 件 test_card_bus_and_priority.py 三锚内容级 diff 取证

> 用途：按 dispatcher-20261118T230617-0042dd（第92圈 / 16 件逐篇 diff 补齐，reply-to dispatcher-20261118T215426-7ff5e1），对 23 件清单第 22 条登记的 test_card_bus_and_priority.py 做三锚内容级 diff 取证，供分发方逐笔裁定。只读取证，不改任何实现、不新增对拍路径；建议仅为取证侧标注，逐笔合入裁定仍归分发方，结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变。

## 一、目录图例（零裸路径）

- js-tests = flask_server/tests/js/
- py-tests = flask_server/tests/
- tunnel = flask_server/
- docs = docs/

正文只写文件名，不裸列完整路径串、不写盘符；目录标签给出工程内相对路径。按仓内既有惯例（占位标签 + 图例）与第91圈 doc-sync 实读口径书写，新建代码/测试文件本身不触发该校验。

## 二、三锚解析与实存

- old = 1e80680：本仓可解析，旧名文件 test_card_bus_and_priority.py 实存 141 行、blob c1b309accc44；新名文件 MISSING。
- bus = 32e83dd：本仓不可解析，经同级交付仓（仓名 chat-bridge-bus，按仓名定位）解析为 commit 32e83dd1fcca251c7d14bbb613f7d891d75e99ae；旧名文件 MISSING，新名文件 test_delivery_queue_and_priority.py 实存 141 行、blob fdbfb9acb944。
- main = origin/main 当前尖端（取证时 4f94b76）：旧名文件 MISSING，新名文件实存 141 行、blob fdbfb9acb944。
- 口径分列：按「路径」记 bus 侧缺、按「rename pair 语义」取到 bus 与 main 侧新名对应文件，两张分母分列登记、不互相覆盖。

## 三、三态分母（实测）

| 锚 | 旧名 test_card_bus_and_priority.py | 新名 test_delivery_queue_and_priority.py |
|---|---|---|
| old 1e80680 | c1b309accc44 | MISSING |
| bus 32e83dd | MISSING | fdbfb9acb944 |
| main 4f94b76 | MISSING | fdbfb9acb944 |

四向实存判定 6/6、三锚解析 3/3。逐行 diff 分母（old-card vs bus-delivery 一致 128 / 差异块 12 / +13 / -13；bus-delivery vs main-delivery 差异块 0，blob 同为 fdbfb9acb944）与 12/12 测试名重叠结论引自既有 docs/r4-rename-pair-diff.md，本笔按分层表序号补该路径三锚实存表，不重做、不覆盖既有底稿。main 缺失行数按「旧名路径」记 141 行，按 rename 语义该能力已由新名文件承载。

## 四、main 现行层等价覆盖（词面分组，非断言）

文件名分词 card,bus,priority 在 origin/main 现行层（517 个候选文件）词面命中 20 个：01g_external_cards.js、01j_card_consume.js、05g_cards.js。仅为文件名词面重合数，未逐行核接口；等价覆盖成立与否归分发方逐笔裁定 [不知道]，不据命中数直接判不移植。

## 五、对象分列（行数两个对象分列登记，不混用）

| 对象 | 行数 |
|---|---|
| 被取证目标文件 test_card_bus_and_priority.py | old 141 / bus MISSING（旧名） |
| 本附录 docs/r4-test-card-bus-and-priority-diff.md | 51 |

## 六、口径与建议

- 建议：不移植（rename 后等价承载物已在 main，旧名不回灌）。main 现行层新名文件实存且与 bus 侧逐行同源； 本项仅为取证侧标注，不是逐笔合入裁定；直搬 / 本地化改写 / 不移植由分发方裁定，c 不代判。
- 两张账不混：取证附录合入 ≠ 逐笔合入裁定完成；材料级采信 ≠ 逐笔合入绿灯；0/23 分母行不改写、不虚报 23/23；不采信自述、不代执行方盖章。
- 第 11 件已由分发方第90/91圈裁版本「不移植」、本笔不重做；本附录是 16 件逐篇补齐中的一篇，不替代逐笔合入裁定。

## 七、复核结论

- 三锚解析 3/3；三态分母一致 128（见既有底稿） / 差异块 12（见既有底稿） / main 缺失 141 行，+13（见既有底稿）/-13（见既有底稿）；old blob c1b309accc44、bus blob 按 rename 语义取新名 fdbfb9acb944。
- 结论源 0/23 与 90%（18/20）不变；逐笔裁定由分发方按 R4 走查推进。
