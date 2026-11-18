# R0 附件：配置面三树全量 blob 矩阵与 B 夹具实跑证据

> 任务 dispatcher-20261118T025047-6d5ccb（R0 配置八跳有效性核查）。本附件按 dispatcher-20261118T090647-d0d99a 三点裁定与 092129/095033 收口窄化口径落库：三树全量矩阵 + 4fbe920 勘误登记 + B 方案既有夹具实跑证据。A 方案（可跑反查夹具）已按 092129 转 c 的 P1 承接，本片不重复交付。

## 一、取证尖端

| 树 | 尖端 | 说明 |
|---|---|---|
| old | origin/legacy/old-stable 1e80680 | 矩阵取证与 B 实跑一致 |
| main | origin/main 239b906（矩阵取证时点） | 复核抽查于 efd6b4f：dialog.html 41a8de9、routes/tools.py 7763f3b、config_draft_store.py 不存在，与取证时点一致无漂移 |
| bus | 32e83dd（冻结基线） | R1 取证锚；B 实跑用 bus 仓工作树 c12f974（分发方已裁不要求回冻结态） |

## 二、32 文件 × 3 树 blob 矩阵（ls-tree 实测）

| 路径 | old | main | bus32 | 分配 |
|---|---|---|---|---|
| extend/dialog/parts/00_data.js | 68dac98 | 0fbb849 | 68dac98 | old=bus≠main |
| extend/dialog/parts/01_backend.js | 4f43424 | 311951f | 4f43424 | old=bus≠main |
| extend/dialog/parts/05e_quality.js | c531fd8 | c531fd8 | c531fd8 | 三版同 |
| extend/dialog/parts/05g_cards.js | 4bd5c1e | 6167159 | 4bd5c1e | old=bus≠main |
| extend/dialog/dialog.html | b61e029 | 41a8de9 | b61e029 | old=bus≠main |
| extend/dialog/parts/08_settings.js | 7ebf9ab | 62ac229 | a8c5c32 | 三版各异 |
| extend/dialog/parts/08b_settings.js | c9b72ed | 599abfa | f4f2c17 | 三版各异 |
| extend/dialog/parts/08c_bridge.js | 15eda67 | 15eda67 | 15eda67 | 三版同 |
| extend/dialog/parts/08d_bridge_weixin.js | 9cc2fcc | 9cc2fcc | 9cc2fcc | 三版同 |
| extend/dialog/parts/08e_bridge_wecom.js | ca1f8a9 | ca1f8a9 | ca1f8a9 | 三版同 |
| extend/dialog/parts/08e_toolconf.js | f402b7d | f402b7d | f402b7d | 三版同 |
| extend/dialog/parts/08f_commands.js | 7d5154c | 4014a02 | 7d5154c | old=bus≠main |
| extend/dialog/parts/08g_site_profiles.js | ee94c1e | 31a1fb1 | ee94c1e | old=bus≠main |
| extend/dialog/parts/08h_profile_fields.js | 46adf57 | 0f2037f | 1dd789b | 三版各异 |
| extend/dialog/parts/08i_config_cache.js | 6914116 | 91df1a1 | 6914116 | old=bus≠main |
| extend/dialog/parts/08j_config_actions.js | 1667538 | c099602 | 2978147 | 三版各异 |
| extend/dialog/parts/08k_config_blocks.js | 9a59dcc | 24ce1f8 | b9fda6e | 三版各异 |
| extend/dialog/parts/08l_config_field_tracking.js | 67558fb | 5c3140a | 67558fb | old=bus≠main |
| extend/dialog/parts/08m_config_restore.js | 0edc10b | 无此文件 | 0edc10b | old=bus、main 已移除 |
| extend/dialog/parts/09_skills.js | 1a6cef1 | 1a6cef1 | f23b83d | old=main≠bus |
| flask_server/config/definition.yaml | a06a313 | 4df94a9 | 5c62f3e | 三版各异 |
| flask_server/core/tool_config.py | 39c38af | 8d979af | 39c38af | old=bus≠main |
| flask_server/core/config_store.py | 8db1cb6 | ce6642e | 8db1cb6 | old=bus≠main |
| flask_server/core/config_file.py | bd5cead | 382cb27 | bd5cead | old=bus≠main |
| flask_server/core/yaml_utils.py | 36af39b | 36af39b | 36af39b | 三版同 |
| flask_server/core/screenshot_store.py | 46923bf | 46923bf | 46923bf | 三版同 |
| flask_server/config_draft_store.py | d6fa053 | 无此文件 | d6fa053 | old=bus、main 已移除 |
| flask_server/routes/config_route.py | 2431b78 | 71b3cbb | 2431b78 | old=bus≠main |
| flask_server/routes/tools.py | e244cd6 | 7763f3b | e244cd6 | old=bus≠main |
| flask_server/remote_bridge/bridge_store.py | bb32d2a | bb32d2a | bb32d2a | 三版同 |
| flask_server/remote_bridge/channel/push_pipeline.py | e102c50 | e102c50 | e102c50 | 三版同 |
| flask_server/remote_bridge/message_router.py | 32634f3 | 32634f3 | 32634f3 | 三版同 |

## 三、分配归纳

- 三版同 10：05e / 08c / 08d / 08e_bridge_wecom / 08e_toolconf / yaml_utils / screenshot_store / bridge_store / push_pipeline / message_router。
- old=bus≠main 13：00_data / 01_backend / 05g / dialog.html / 08f / 08g / 08i / 08l / tool_config / config_store / config_file / config_route / routes/tools——配置主干链 old=bus 成立。
- old=bus 且 main 已移除 2：08m_config_restore / config_draft_store（main 无 draft 链，走 C-3a 寄存）。
- 三版各异 6：08_settings / 08b_settings / 08h / 08j / 08k / definition.yaml。
- old=main≠bus 1：09_skills（bus f23b83d 独立实现，与 b 的 R1-1 直搬清单互证）。
- def.yaml 行数：old 903 / main 507 / bus 929（bus 独有 29 行 = F5 本体：yuanbao filePaste 与 qwen 档案）。

## 四、B 方案既有夹具实跑证据（081846 B）

js 侧（node --test 逐文件，以逐文件 rc 定案；not ok 明细行经运输层存在错位，仅作归因参考）：

| 树 | 基点 | 分母 | 明细 |
|---|---|---|---|
| main | 449d761 worktree | 6/6 pass | actions / audit / blocks / cache / diff_items / public_config_ui 全 rc=0 |
| old | 1e80680 worktree | 6/14 | pass：actions / blocks / cache / diff_items / draft_isolation / public_config_ui；fail：audit / backend_draft / badge_icons / badge_restore / cache_global / diff_noise / diff_tip / ui_fixes |
| bus | c12f974 工作树 | 10/14 | pass：actions / backend_draft / badge_icons / cache / cache_global / diff_items / diff_noise / draft_isolation / ui_fixes / public_config_ui 共 10 件；fail：audit / badge_restore / blocks / diff_tip |

失败归因：old 侧 8 个失败中 5 个为「行数门禁 ≤450 行」基线断言（audit / backend_draft / badge_icons / cache_global / ui_fixes），diff_tip 为「明细携带母本值」断言，badge_restore 为块头徽标断言，diff_noise 为文件级 ERR_ASSERTION 崩溃；bus 侧 diff_noise 已过（与 aed612e 修路径互证）、blocks 失败为白名单与 applyPendingToRead 三断言、audit / badge_restore / diff_tip 同 old 侧。所有失败均为各树自身基线态，非本片引入（本片零代码改动）。

py 侧（pytest）：

| 树 | 基点 | 分母 |
|---|---|---|
| main | 449d761 worktree | 3 件批量 53 passed rc=0（file / route / store） |
| old | 1e80680 worktree | 4/4 件全过：draft 6 passed + file/route/store 52 passed，rc=0 |
| bus | c12f974 工作树 | 4/4 件全过：draft 6 passed + file/route/store 52 passed，rc=0 |

## 五、分母与查证限度

- 分母：矩阵 32 文件×3 树 blob 全实测；B 证据 js 34 文件次 + py 11 文件次实跑；main 239b906→efd6b4f 三点复核无漂移。
- 限度：①old/bus js 失败的逐断言归因受运输层 not ok 行错位影响，pass/fail 以 rc 为准；②bus B 实跑基点为工作树 c12f974 而非 32e83dd（分发方已裁可接受）；③F5 行级证据维持 4fbe920 §二，本片不重跑。