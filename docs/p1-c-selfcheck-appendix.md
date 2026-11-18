# P1 工具结果体积上限即时生效 · 自检附录

## 一、五态夹具与实测分母

| 态 | 用例 | 断言 | 结果 |
|---|---|---|---|
| 超限报错 | test_over_limit_raises | 超出上限抛 ToolParamError，文案带生效上限 | pass |
| 未超限原样 | test_under_limit_returns_same_object | 返回同一对象，不截断不复制 | pass |
| 边界等值 | test_boundary_equal_passes | 序列化长度恰等于上限时按未超限放行 | pass |
| 内存值优先 | test_runtime_value_overrides_disk_master | 运行时内存上限优先于磁盘母版 | pass |
| 覆盖回写重启 | test_covered_restart_keeps_value | 母版回写新值后重启仍按新值受限 | pass |

合计 5 pass / 0 fail（5/5，100%）；三态 3/3、配置源优先级 2/2。
分母来源：补丁在 old@1e80680 树注入运行时内存与磁盘母版两组配置的实跑结果；两仓搬运后定向夹具 old rc=0、bus rc=0，实机复验由分发方串行执行。

## 二、文件边界

补丁改动面，M 为修改、A 为新增：

    M  flask_server/tools/tool_helpers.py
    A  flask_server/tests/test_tool_helpers_size_limit.py

改动集中在 max_json_chars：优先读取运行时内存里的 limits.max_json_chars 即时值，磁盘母版保留为启动阶段兜底；统一出口沿用原调用。新增夹具仅依赖仓库内模块。

沿用仓库原实现的文件：

    08k_config_blocks.js
    08_settings.js
    08j_config_actions.js
    config_route.py
    config_draft_store.py
    08i_config_cache.js
    definition.yaml
    CONFIG_SCHEMA

## 三、交付形态

补丁全文经总线回执 c-20261118T110935-270731 送达；分发方串行应用到 old-stable 与 bus master，两仓各一次提交，bus master 以 32e83dd 为父提交。本附录为工作分支上的单笔纯文档交付。
