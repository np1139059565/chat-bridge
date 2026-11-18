# R4 逐笔对拍对象 blob 取证底稿（2026-11-18）

> 取数锚点：old 1e80680、bus 32e83dd、main 为 origin/main 当前尖端；命令 git ls-tree -r，哈希取前 12 位。
> 本表仅登记冻结锚下的 blob 取证结果；逐笔内容级 diff 与合入裁定仍待分发方 R4 走查，结论源 docs/00-STATUS.md 进度数值不变。

| 序号 | 路径 | old blob | bus blob | old/bus | main |
|---|---|---|---|---|---|
| 1 | docs/system-prompt-lazy-load.md | d26f8748c1f4 | d26f8748c1f4 | 一致 | 缺 |
| 2 | extend/dialog/parts/08m_config_restore.js | 0edc10bddc35 | 0edc10bddc35 | 一致 | 缺 |
| 3 | flask_server/config_draft_store.py | d6fa05345d6d | d6fa05345d6d | 一致 | 缺 |
| 4 | flask_server/tests/js/test_command_restore_btn.test.js | 2814d4dc0141 | 2814d4dc0141 | 一致 | 缺 |
| 5 | flask_server/tests/js/test_command_restore_fixes.test.js | ffe019b5d626 | ffe019b5d626 | 一致 | 缺 |
| 6 | flask_server/tests/js/test_command_unified_list.test.js | 919436945189 | 919436945189 | 一致 | 缺 |
| 7 | flask_server/tests/js/test_config_backend_draft.test.js | 85274480148b | 85274480148b | 一致 | 缺 |
| 8 | flask_server/tests/js/test_config_badge_icons.test.js | 47938278d3c5 | 47938278d3c5 | 一致 | 缺 |
| 9 | flask_server/tests/js/test_config_badge_restore.test.js | 8f216b76b029 | 8f216b76b029 | 一致 | 缺 |
| 10 | flask_server/tests/js/test_config_cache_global.test.js | 904ef5183b5b | 904ef5183b5b | 一致 | 缺 |
| 11 | flask_server/tests/js/test_config_diff_noise.test.js | 0a60edc67829 | 3d4bd8d952b1 | 不同 | 缺 |
| 12 | flask_server/tests/js/test_config_diff_tip.test.js | 2637826e47f5 | 2637826e47f5 | 一致 | 缺 |
| 13 | flask_server/tests/js/test_config_draft_isolation.test.js | 74461e56ba45 | 74461e56ba45 | 一致 | 缺 |
| 14 | flask_server/tests/js/test_config_ui_fixes.test.js | 0ee861e0ef56 | 0ee861e0ef56 | 一致 | 缺 |
| 15 | flask_server/tests/js/test_custom_tools_scan.test.js | 05f402e99240 | 05f402e99240 | 一致 | 缺 |
| 16 | flask_server/tests/js/test_site_profile_hosts_text.test.js | e8d629c3a7cd | e8d629c3a7cd | 一致 | 缺 |
| 17 | flask_server/tests/js/test_site_profile_restore_layout.test.js | 06edb6002328 | 06edb6002328 | 一致 | 缺 |
| 18 | flask_server/tests/test_capability_visibility.py | b0a01e487973 | b0a01e487973 | 一致 | 缺 |
| 19 | flask_server/tests/test_config_draft.py | dcb0e15c723a | dcb0e15c723a | 一致 | 缺 |
| 20 | flask_server/tests/test_custom_tools_scan.py | 41b47563d9ca | 41b47563d9ca | 一致 | 缺 |
| 21 | flask_server/tests/test_file_paste_mode.py | 96f74ecd38ae | 96f74ecd38ae | 一致 | 缺 |
| 22 | flask_server/tests/test_card_bus_and_priority.py | c1b309accc44 | 缺 | old 单侧 | 缺 |
| 23 | flask_server/tunnel.cmd | a5a970fbe9ff | a5a970fbe9ff | 一致 | 缺 |

汇总：23/23 条路径取到冻结锚 blob；old 与 bus 一致 21 条、old 单侧 1 条、不同 1 条；main 侧 23 条均缺。
第 19 个测试 flask_server/tests/test_card_bus_and_priority.py 为 old 单侧，与 bus 侧 test_delivery_queue_and_priority.py 构成 rename pair。
逐笔对拍结论仍为 0/23，本底稿不替代内容级裁定。
