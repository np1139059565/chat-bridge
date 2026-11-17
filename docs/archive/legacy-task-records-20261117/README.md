# 旧任务记录归档（2026-11-17 10:19）

A-14 / B-15 / C-19 三链收口后的 inventory / report 归属登记。

## 本轮结论（A/B 实测）

- 冻结 tag `migration-p0-f126c6a` 原布局：`test_standard_chain_*` 10/10 全绿。
- 19 份全部移出 `docs/` 根后：10 个 `not ok`（测试按 `docs/<name>.md` 硬路径读夹具）。
- 故**测试 / 收录表按 `docs/` 路径依赖的 19 份保留原位**；
  仅 0 份无源码引用者物理归档到本目录（`git mv`，内容未改、历史保留）。

## 实际归档清单

- （无：19 份均为测试夹具依赖，全部保留 `docs/` 根，仅登记不移动）

## item 8 清理口径

`D:\mydata` 根层 61 个 `_cb_*` 临时/进度/输出文件、13 个 `_cb_verify_*` worktree、
25 个缓存目录、0 字节 `flask_server/PATH` 已在前轮删净（`REMAIN_CB_ITEMS=0`）。
本目录这些是 **git tracked 正式文档**，非临时文件，不可删；清理以登记 + 无引用件归档交付。

## 恢复

`git mv docs/archive/legacy-task-records-20261117/<name> docs/<name>`
