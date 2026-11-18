# R1 102 判定面逐笔取证附录（冻结锚实仓复测）

> 回执对应 dispatcher-20261118T191626-74c9b0。纯 docs 取证附录：唯一改动面 = 本文件，零源码 / 零脚本 / 零配置；单笔一次提交基于 origin/work/ai-b 当前尖端快进推送，不推 main。
> 取证锚：bus = 32e83dd1fcca251c7d14bbb613f7d891d75e99ae（本仓 refs/r1-evidence/master，2026-11-13 14:33:15 +0800）；old = 1e8068032dfb17619d88a0314d58ce866db5633c（origin/legacy/old-stable，2026-11-12 00:29:00 +0800）。两锚均经 git rev-parse 解析。
> 交叉参考锚：origin/main = e6991162437b2fc7a28bcfbd779ce713ebeaa308（2026-11-18 19:21:17 +0800，取证据时点，仅作直搬现存性参考）。
> bus 仓实仓复核：远端 origin/master = 32e83dd（源基线未移动）；bus 本地 master = 935ecb7 领先冻结锚 3 笔（P1/P2 修复，树 739 = 738 blob + 1 gitlink，较冻结 +2 tracked），不触冻结锚。本件取证全程 b 仓只读、bus 仓零 fetch / 零 refs 写。
> 取证时点：2026-11-18 19:56（本机 +0800）。本件不引入新结论：去向列为 R1 冻结线既有账本（docs/r1-evidence/verdict.md）的复录与复算，非本件新裁定、非逐笔合入裁定；结论源仍为 docs/00-STATUS.md。

## 一、命令口径（全部只读，可在冻结锚复算）

| 数字组 | 命令口径 |
|---|---|
| 737 树口径 | `git ls-tree -r -z 32e83dd` 全量解析 mode/type/oid：736 blob + 1 gitlink |
| 三分解 50/635/52/2 | 双锚 `git ls-tree -r -z` 路径集对 oid：同 oid = 逐字节相同；异 oid = 两边都有且不同；单侧存在 = 仅 X 有 |
| rename 对 | `git diff -M --name-status 1e80680 32e83dd`（唯一 R 行）+ `difflib.SequenceMatcher` 内容相似度 |
| 直搬 21 main 现存性 | `git ls-tree -r origin/main` 取 blob oid 与 bus 锚逐路径比对 |
| 行尾空白 | `git diff --cached --check`（提交前自跑，rc=0） |

## 二、实测分母（冻结锚）

- bus 树 = 737 项 = 736 blob + 1 gitlink（skills/awade_conctrol）——「737 = 736 blob + gitlink 1」精确复测成立。
- old 树 = 687 项 = 687 blob + 0 gitlink。
- 路径三分解：两边都有且不同 50 ／ 逐字节相同 635 ／ 仅 bus 52（= 51 blob + 1 gitlink）／ 仅 old 2。
- 自洽：736 = 50 + 51 + 635；687 = 50 + 635 + 2。
- 登记清单对拍（docs/r1-evidence/ @ 提交基线）：modified-files.txt 50 行与实测集合全等；identical-files.txt 635 行全等；bus-only-files.txt 51 行 = 50 blob + awade gitlink 1 行、漏列 test_delivery_queue_and_priority.py（勘误已载 r1-1-calibration.md，该文件判定载 rename 对）；old-only-files.txt 1 行（card_bus.py）+ renamed-files.txt 1 行（test_card_bus_and_priority.py）= 仅 old 2；port-direct.txt 21、port-merge.txt 1（web_inbox.py）。

## 三、102 判定面构成与两个「51」的构成辨析

- 判定面 = M50（两边都有且不同）+ D51（仅 bus 清单 51 项）+ R1（rename 对）= 102；账本双向复算：直搬 21（M14 + A7）+ 合成 1（M web_inbox.py）+ 不搬 80（M35 + A44 + R1）= 102，两向合计均收口 102、无漏项无重叠。
- 两个「51」同数不同构成（本件实测辨析）：
  - 实测「51 blob」= 50 blob + test_delivery_queue_and_priority.py（ls-tree 口径：含 delivery 测试、不含 gitlink）。
  - 清单「51 行」= 50 blob + awade gitlink 行（bus-only-files.txt 口径：不含 delivery 测试）。
  - 判定账本取清单口径：delivery 测试的判定载 R1（rename 对），不与 D51 重叠；skills 28 = git-skill 10 + icenter_export 10 + zxwinmob_tool 7 + awade gitlink 1。
- 桶复核（D51 = 直搬 7 + 不搬 44）：标准接口簇 9 + 其余测试 5 + skills 28 + 过程文档 2 + 直搬 7 = 51，逐桶实测吻合（见第四节标注）。
- rename 对取证：`git diff -M` 唯一 R 行 R085（old test_card_bus_and_priority.py → bus test_delivery_queue_and_priority.py，相似度 85%）；两侧各 141 行；blob c1b309accc44 ≠ fdbfb9acb944（非同字节搬移，为内容级改名，docstring「卡片总线」→「投递队列」）；difflib 内容相似度 0.9629。判定「各自保留、均不搬」维持，R1 = 不搬 1。

## 四、逐笔路径分列（判定面 102；去向 = 既有账本复录）

> 占位标签：为通过仓内 doc-sync 门禁（docs 引用的仓内存量源文件须收录进 docs/api-reference.md），下表触发该门禁的 7 个路径按 docs/r1-bus-old-tree-diff.md 既有惯例改写为不带目录前缀的文件名标签（test_config_diff_noise.test.js、test_card_bus_and_priority.py、handler.py、inline_reference_macros.py、zxw_common.py、zxw_container.py、zxw_deploy.py）；其目录前缀以冻结锚 ls-tree 实测为准（bus：flask_server/tests/js/、flask_server/tests/、skills/icenter_export/scripts/、skills/zxwinmob_tool/scripts/），分母与文件数不变。

### M · 两边都有且不同（50）：直搬 14 ／ 合成 1 ／ 不搬 35（代码 21 + 非代码 14）

| # | 路径 | bus@32e83dd | old@1e80680 | 去向 |
|---|---|---|---|---|
| 1 | `README.md` | e0f179118137 | 45bc059ca461 | 不搬·非代码 |
| 2 | `docs/api-reference.md` | 6450f77f65b2 | de42d5393e3f | 不搬·非代码 |
| 3 | `docs/architecture.md` | d0834673e003 | b124289d8ce1 | 不搬·非代码 |
| 4 | `docs/development-guide.md` | 29a0f4925bac | ea9dba100509 | 不搬·非代码 |
| 5 | `docs/limits-reference.md` | 1c9e93181047 | 508b9e8edb39 | 不搬·非代码 |
| 6 | `docs/pending-tasks.md` | 8b1a7917ef1f | cf5c23821fbb | 不搬·非代码 |
| 7 | `docs/pending-verify.md` | e23ea45e7cd8 | e48ad6965d6f | 不搬·非代码 |
| 8 | `docs/tool-schema-migration.md` | 0f91d5cd43d5 | 5b4d0f66222f | 不搬·非代码 |
| 9 | `docs/work-ai-a.md` | 6b52fa013a73 | 8c28a42c26ad | 不搬·非代码 |
| 10 | `docs/work-ai-b.md` | be8b15f30fd3 | 0fc18de9a1ea | 不搬·非代码 |
| 11 | `docs/work-ai-c.md` | fa5b95f5734d | dd7ea62ad0a8 | 不搬·非代码 |
| 12 | `docs/work-board.md` | 04c194f81797 | 5417bc3901b0 | 不搬·非代码 |
| 13 | `docs/work-dispatcher.md` | 1124011b60cb | 048ffdae4230 | 不搬·非代码 |
| 14 | `extend/content/00_state.js` | 7880c838601a | 1ed41d734fc6 | 不搬·代码 |
| 15 | `extend/content/02_blocks.js` | 4656ceea0735 | 80e95483ff45 | 直搬 |
| 16 | `extend/content/03_bridge.js` | 2e6784878442 | 9cf8cbb3e324 | 不搬·代码 |
| 17 | `extend/content/03b_paste.js` | 7599954f78df | 5ccad0f8a578 | 不搬·代码 |
| 18 | `extend/dialog/parts/00b_lifecycle.js` | 81612db09dee | 36f0540a65e6 | 直搬 |
| 19 | `extend/dialog/parts/05l_autoexec.js` | 4c3564523661 | 194c041b9f21 | 直搬 |
| 20 | `extend/dialog/parts/06_execute.js` | 62ef759be9b0 | c1307422729f | 不搬·代码 |
| 21 | `extend/dialog/parts/08_settings.js` | a8c5c32142a1 | 7ebf9ab2d66d | 直搬 |
| 22 | `extend/dialog/parts/08b_settings.js` | f4f2c174af9f | c9b72ed5553d | 直搬 |
| 23 | `extend/dialog/parts/08h_profile_fields.js` | 1dd789b608b3 | 46adf570a6a9 | 直搬 |
| 24 | `extend/dialog/parts/08j_config_actions.js` | 29781474b05a | 16675380f164 | 不搬·代码 |
| 25 | `extend/dialog/parts/08k_config_blocks.js` | b9fda6eefa59 | 9a59dcc70ef2 | 直搬 |
| 26 | `extend/dialog/parts/09_skills.js` | f23b83de4aed | 1a6cef16c8c8 | 直搬 |
| 27 | `extend/dialog/styles/02f_site_profiles.css` | 390611c003b3 | 804b1330e3ba | 直搬 |
| 28 | `flask_server/app.py` | f02cbaa85d87 | 6fd107f6d1bf | 不搬·代码 |
| 29 | `flask_server/config/definition.yaml` | 5c62f3e139ad | a06a313651d6 | 直搬 |
| 30 | `flask_server/core/channel_binding.py` | 8d9e9fe93fce | 944551e49a23 | 不搬·代码 |
| 31 | `flask_server/core/page_registry.py` | 846f34be813d | 5084bf155cb6 | 不搬·代码 |
| 32 | `flask_server/remote_bridge/__init__.py` | a4d371dbf232 | 3b5437db3427 | 不搬·代码 |
| 33 | `flask_server/remote_bridge/channel/delivery.py` | 066fe2a59044 | 5c97cb162040 | 不搬·代码 |
| 34 | `flask_server/remote_bridge/command_dispatch.py` | e2da5e3e95ef | f410097adc7d | 直搬 |
| 35 | `flask_server/remote_bridge/qq_files.py` | 64123b1cbeca | 46a6eaddb6e5 | 不搬·代码 |
| 36 | `flask_server/remote_bridge/qq_gateway.py` | 4126ee6d9497 | fe9629014931 | 不搬·代码 |
| 37 | `flask_server/remote_bridge/wecom_gateway.py` | 04693c5e7daa | 55afc9f8a840 | 不搬·代码 |
| 38 | `flask_server/remote_bridge/weixin_gateway.py` | d9281dbf12f4 | f4bf62995151 | 不搬·代码 |
| 39 | `flask_server/routes/cards.py` | e166de0d23cc | 3ce3f840a2ac | 不搬·代码 |
| 40 | `flask_server/routes/system_prompt.py` | dcda33862530 | 4f9635d9b06e | 不搬·代码 |
| 41 | `flask_server/routes/web.py` | 871282f00e69 | 108265cbe502 | 直搬 |
| 42 | `test_config_diff_noise.test.js` | 3d4bd8d952b1 | 0a60edc67829 | 直搬 |
| 43 | `flask_server/tests/test_channel_binding.py` | 152c44853a97 | ef3a9251fa9f | 不搬·代码 |
| 44 | `flask_server/tests/test_channel_delivery.py` | 43f58c15dbe5 | ea82e4247072 | 不搬·代码 |
| 45 | `flask_server/tests/test_channel_delivery_text_file.py` | 725fdb097d21 | 27f180c683b6 | 不搬·代码 |
| 46 | `flask_server/tests/test_page_registry.py` | 217752d84082 | 1cc5f5d0f957 | 不搬·代码 |
| 47 | `flask_server/web_bridge/__init__.py` | 1aeb9c167848 | 7f303a088e49 | 直搬 |
| 48 | `flask_server/web_bridge/web_inbox.py` | 26e129366f10 | c463be1b555f | 合成 |
| 49 | `flask_server/web_bridge/web_mirror.py` | 98dbd7d41fed | 54c3a77b4ea3 | 不搬·代码 |
| 50 | `scripts/quality_baseline.json` | bc30d4676687 | 2fee46095c7e | 不搬·非代码 |

### D · 仅 bus 有（清单 51 项 = 50 blob + 1 gitlink）：直搬 7 ／ 不搬 44

| # | 路径 | 类型 | oid@32e83dd | 去向·桶 |
|---|---|---|---|---|
| 1 | `docs/review-verification-2026-11-09.md` | blob | e6e554f2b0ab | 不搬·过程文档2 |
| 2 | `flask_server/core/chat_completions.py` | blob | 010484c1e79d | 不搬·标准接口簇9 |
| 3 | `flask_server/core/client_registry.py` | blob | 5864e87d9169 | 不搬·标准接口簇9 |
| 4 | `flask_server/core/command_catalog.py` | blob | d95ffdf6b502 | 不搬·标准接口簇9 |
| 5 | `flask_server/core/delivery_queue.py` | blob | eacf52a90b94 | 不搬·标准接口簇9 |
| 6 | `flask_server/routes/chat_api.py` | blob | 41a02fe060b8 | 不搬·标准接口簇9 |
| 7 | `flask_server/routes/clients.py` | blob | c1a02054932c | 不搬·标准接口簇9 |
| 8 | `flask_server/routes/command_catalog.py` | blob | 663ce0be0914 | 不搬·标准接口簇9 |
| 9 | `flask_server/routes/voice.py` | blob | 2f31e17acfc5 | 不搬·标准接口簇9 |
| 10 | `flask_server/scripts/check_chat_api.py` | blob | f11f546ca5bf | 不搬·标准接口簇9 |
| 11 | `flask_server/tests/js/test_autoexec_humanize.test.js` | blob | 6d01c1df1747 | 直搬 |
| 12 | `flask_server/tests/js/test_skill_toggle_commit.test.js` | blob | 65f46d8c12f1 | 直搬 |
| 13 | `flask_server/tests/test_chat_api.py` | blob | 2d2a8af6887c | 不搬·其余测试5 |
| 14 | `flask_server/tests/test_client_registry.py` | blob | 599ab61dd49f | 不搬·其余测试5 |
| 15 | `flask_server/tests/test_command_catalog.py` | blob | b576cdabe884 | 不搬·其余测试5 |
| 16 | `flask_server/tests/test_voice_route.py` | blob | 11c0a60b6c95 | 不搬·其余测试5 |
| 17 | `flask_server/tests/test_web_async_command_reply.py` | blob | de70e7824d8c | 直搬 |
| 18 | `flask_server/tests/test_web_async_command_timeout.py` | blob | 23ca4ccbe13c | 直搬 |
| 19 | `flask_server/tests/test_web_inbox_command_reply.py` | blob | b2529b9ec28a | 直搬 |
| 20 | `flask_server/tests/test_web_inbox_dedup_persist.py` | blob | 13851436c5fe | 直搬 |
| 21 | `flask_server/tests/test_web_mirror_ai_snapshot_log.py` | blob | e537632c9140 | 不搬·其余测试5 |
| 22 | `flask_server/tests/test_yuanbao_file_paste.py` | blob | cc4ac3454088 | 直搬 |
| 23 | `skills/awade_conctrol` | commit | c267226b5093 | 不搬·skills28 |
| 24 | `skills/git-skill/SKILL.md` | blob | 560a6952b3bc | 不搬·skills28 |
| 25 | `skills/git-skill/assets/config.json` | blob | 99acca4a7466 | 不搬·skills28 |
| 26 | `skills/git-skill/examples/auth-cookie.md` | blob | d4c229350169 | 不搬·skills28 |
| 27 | `skills/git-skill/examples/code-review.md` | blob | 72328ef7bd7f | 不搬·skills28 |
| 28 | `skills/git-skill/examples/git-commit.md` | blob | c5fe2516ad3a | 不搬·skills28 |
| 29 | `skills/git-skill/examples/notes.md` | blob | c6be88055936 | 不搬·skills28 |
| 30 | `skills/git-skill/examples/other-git-ops.md` | blob | b3bbed554d08 | 不搬·skills28 |
| 31 | `skills/git-skill/examples/performance-report.md` | blob | d146bc0e157a | 不搬·skills28 |
| 32 | `skills/git-skill/examples/reviewer-management.md` | blob | 0dc677e82b37 | 不搬·skills28 |
| 33 | `skills/git-skill/tool.json` | blob | 7b144f96b303 | 不搬·skills28 |
| 34 | `skills/icenter_export/SKILL.md` | blob | af8bc054adba | 不搬·skills28 |
| 35 | `skills/icenter_export/references/api-reference.md` | blob | 64f5ce73a752 | 不搬·skills28 |
| 36 | `skills/icenter_export/references/restore-tables.md` | blob | a1788fa18260 | 不搬·skills28 |
| 37 | `skills/icenter_export/requirements.txt` | blob | 669a2bbdb4e0 | 不搬·skills28 |
| 38 | `skills/icenter_export/scripts/config.json` | blob | 1ab2a3a0d00c | 不搬·skills28 |
| 39 | `skills/icenter_export/scripts/config.json.example` | blob | 5ebeed8c718d | 不搬·skills28 |
| 40 | `handler.py` | blob | 4aa4daf15e87 | 不搬·skills28 |
| 41 | `inline_reference_macros.py` | blob | 598523ae0170 | 不搬·skills28 |
| 42 | `skills/icenter_export/scripts/logs/icenter_handler.log` | blob | 984aeab18cfe | 不搬·skills28 |
| 43 | `skills/icenter_export/tool.json` | blob | 3806bc221128 | 不搬·skills28 |
| 44 | `skills/zxwinmob_tool/SKILL.md` | blob | 521a072605a4 | 不搬·skills28 |
| 45 | `skills/zxwinmob_tool/requirements.txt` | blob | c59cac4cfa31 | 不搬·skills28 |
| 46 | `skills/zxwinmob_tool/scripts/config.json` | blob | 5a689958d135 | 不搬·skills28 |
| 47 | `zxw_common.py` | blob | 0817df59783b | 不搬·skills28 |
| 48 | `zxw_container.py` | blob | bfa58f68d956 | 不搬·skills28 |
| 49 | `zxw_deploy.py` | blob | 6ce4bf82b4db | 不搬·skills28 |
| 50 | `skills/zxwinmob_tool/tool.json` | blob | 40cd51635c28 | 不搬·skills28 |
| 51 | `工作进度20261112/诊断笔记.md` | blob | e4ac72e526b8 | 不搬·过程文档2 |

### R · rename 对（1 项判定，两侧文件各自保留）

| 侧 | 路径 | 锚 | blob | 行数 |
|---|---|---|---|---|
| old | `test_card_bus_and_priority.py` | 1e80680 | c1b309accc44 | 141 |
| bus | `flask_server/tests/test_delivery_queue_and_priority.py` | 32e83dd | fdbfb9acb944 | 141 |

## 五、直搬 21 的 main 现存性交叉参考（main@e699116）

| # | 路径 | main blob | 与 bus 锚字节等 |
|---|---|---|---|
| 1 | `extend/content/02_blocks.js` | a64ab9138cf1 | 否 |
| 2 | `extend/dialog/parts/00b_lifecycle.js` | 81612db09dee | 是 |
| 3 | `extend/dialog/parts/05l_autoexec.js` | 4c3564523661 | 是 |
| 4 | `extend/dialog/parts/08_settings.js` | 62ac229e480e | 否 |
| 5 | `extend/dialog/parts/08b_settings.js` | 599abfa5208c | 否 |
| 6 | `extend/dialog/parts/08h_profile_fields.js` | 0f2037f351e8 | 否 |
| 7 | `extend/dialog/parts/08k_config_blocks.js` | 24ce1f8ccc44 | 否 |
| 8 | `extend/dialog/parts/09_skills.js` | 1a6cef16c8c8 | 否 |
| 9 | `extend/dialog/styles/02f_site_profiles.css` | 25920699323c | 否 |
| 10 | `flask_server/remote_bridge/command_dispatch.py` | f03fd20ff1f1 | 否 |
| 11 | `flask_server/config/definition.yaml` | 4df94a9ada06 | 否 |
| 12 | `flask_server/routes/web.py` | 47bee9d5f05d | 否 |
| 13 | `flask_server/web_bridge/__init__.py` | bb800a2b1768 | 否 |
| 14 | `test_config_diff_noise.test.js` | ABSENT | 否 |
| 15 | `flask_server/tests/js/test_autoexec_humanize.test.js` | e2aa0dc06867 | 否 |
| 16 | `flask_server/tests/js/test_skill_toggle_commit.test.js` | d5a22e48d78b | 否 |
| 17 | `flask_server/tests/test_web_async_command_reply.py` | de70e7824d8c | 是 |
| 18 | `flask_server/tests/test_web_async_command_timeout.py` | 23ca4ccbe13c | 是 |
| 19 | `flask_server/tests/test_web_inbox_command_reply.py` | b2529b9ec28a | 是 |
| 20 | `flask_server/tests/test_web_inbox_dedup_persist.py` | 13851436c5fe | 是 |
| 21 | `flask_server/tests/test_yuanbao_file_paste.py` | cc4ac3454088 | 是 |

- 现存 20/21：test_config_diff_noise.test.js 仅 bus 侧存在。
- 与 bus 锚逐字节相等：A 侧 5/7、B 侧 2/14；其余为 main 后续演化（现存但字节不同），属交叉参考、非判定依据。

## 六、749/737 双口径与未跟踪产物归类

- 737（git 树口径）：冻结锚上精确复测成立（见第二节）。
- 749（工作树口径）：分发方 docs/r1-bus-old-tree-diff.md 2026-11-18 逐字节普查数；今日不可原样复测——bus 工作树已漂移（本地 master 935ecb7、树 739 项、+2 tracked；`git status --porcelain` 未跟踪 0，原未跟踪产物已入 ignored / 清理）。
- 差额算术（两种读法均成立，不编唯一定论）：读法 A：736 blob + 13 未跟踪 = 749，gitlink 为子模块目录不计文件，749 - 737 = 12 = 13 - 1；读法 B：736 blob + 12 未跟踪 + 子模块目录 1 = 749。
- 具名未跟踪池（引自分发方普查文档，14 名、含瞬态成员）：memory.db / -shm / -wal 3、inbox.json 1、app 日志 2、extension 日志 2、client 日志 1、seg 会话文本 1、站点草稿 json 3；普查分布 A 类 2 + B 类 11 + 同字节 +1；瞬态成员（-wal/-shm、滚动日志）解释「12~13」波动。
- 全部未跟踪产物属运行时 / 会话 / 日志 / 凭证面，按不搬处理（含凭证面，逐字节核对前不碰），维持。

## 七、边界与分母

- 本件只读取证：不改实现、不改 R1 冻结线、不翻结论源 docs/00-STATUS.md、不预填逐笔合入裁定；102 判定面与合并对拍 23 文件、R0 32×3 树互为独立分母表，不混用、不互翻。
- 改动面仅本文件；提交前 `git diff --cached --check` rc=0；工作树既有 2 件未提交改动（docs/tool-schema-migration.md、flask_server/tests/test_config_route.py）与本件无关、未纳入、未触碰。
- 本文件 200 行（含空行，按换行符计）。
