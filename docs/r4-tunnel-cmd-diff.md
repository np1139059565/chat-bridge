# R4 逐笔对拍：第 23 件 tunnel.cmd 三锚内容级 diff 取证

> 用途：按 dispatcher-20261118T230617-0042dd（第92圈 / 16 件逐篇 diff 补齐，reply-to dispatcher-20261118T215426-7ff5e1），对 23 件清单第 23 条登记的 tunnel.cmd 做三锚内容级 diff 取证，供分发方逐笔裁定。只读取证，不改任何实现、不新增对拍路径；建议仅为取证侧标注，逐笔合入裁定仍归分发方，结论源 docs/00-STATUS.md 的 0/23 与 90%（18/20）不变。

## 一、目录图例（零裸路径）

- js-tests = flask_server/tests/js/
- py-tests = flask_server/tests/
- tunnel = flask_server/
- docs = docs/

正文只写文件名，不裸列完整路径串、不写盘符；目录标签给出工程内相对路径。按仓内既有惯例（占位标签 + 图例）与第91圈 doc-sync 实读口径书写，新建代码/测试文件本身不触发该校验。

## 二、三锚解析与实存

- old = 1e80680：本仓可解析，tunnel.cmd 实存 60 行、blob a5a970fbe9ff。
- bus = 32e83dd：本仓不可解析，经同级交付仓（仓名 chat-bridge-bus，按仓名定位）解析为 commit 32e83dd1fcca251c7d14bbb613f7d891d75e99ae，同文件实存 60 行、blob a5a970fbe9ff。
- main = origin/main 当前尖端（取证时 4f94b76）：该文件 MISSING，bus 全部 60 行相对 main 均为新增面。

## 三、三态分母（实测）

| 态 | 分母 | 实测方式 |
|---|---|---|
| old/bus 一致行数 | 60 | difflib.SequenceMatcher 逐行比对，matching blocks 合计 |
| old/bus 差异块数 | 0 | opcode 序列全为 equal，无 insert / delete / replace 块 |
| main 缺失行数 | 60 | main 下该文件整件缺，bus 全部行相对 main 为新增面 |

old 与 bus 逐行同源，+0/-0，opcode 全 equal。

## 四、main 现行层等价覆盖（词面分组，非断言）

文件名分词 tunnel 在 origin/main 现行层（517 个候选文件）词面命中 0 个：（无）。仅为文件名词面重合数，未逐行核接口；等价覆盖成立与否归分发方逐笔裁定 [不知道]，不据命中数直接判不移植。

## 五、对象分列（行数两个对象分列登记，不混用）

| 对象 | 行数 |
|---|---|
| 被取证目标文件 tunnel.cmd | old 60 / bus 60 |
| 本附录 docs/r4-tunnel-cmd-diff.md | 50 |

## 六、口径与建议

- 建议：本地化改写（取证附录留痕，实现以 main 现行层为准，不回灌旧文件）。三锚 main 无、old=bus 同 blob；现行层词面未命中、等价覆盖未逐行核 [不知道]，沿用第88圈 L324 同类件口径； 本项仅为取证侧标注，不是逐笔合入裁定；直搬 / 本地化改写 / 不移植由分发方裁定，c 不代判。
- 两张账不混：取证附录合入 ≠ 逐笔合入裁定完成；材料级采信 ≠ 逐笔合入绿灯；0/23 分母行不改写、不虚报 23/23；不采信自述、不代执行方盖章。
- 第 11 件已由分发方第90/91圈裁版本「不移植」、本笔不重做；本附录是 16 件逐篇补齐中的一篇，不替代逐笔合入裁定。

## 七、复核结论

- 三锚解析 3/3；三态分母一致 60 / 差异块 0 / main 缺失 60 行，+0/-0；old blob a5a970fbe9ff、bus blob a5a970fbe9ff。
- 结论源 0/23 与 90%（18/20）不变；逐笔裁定由分发方按 R4 走查推进。
