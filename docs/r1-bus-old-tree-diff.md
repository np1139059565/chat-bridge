# R1 源材料：bus → old 文件树差异取证件

> 性质：分发方只读取证，供 AI-B 的 R1-1 作输入，**不替代** b 的逐文件裁定。
> 源：bus 冻结态 `32e83dd`（独立根 `b2c503e4c2`、独立远端），工作区 2 项未提交改动已排除。
> 对照：old 实时 `origin/legacy/old-stable`，取证时尖端 `1e80680`。
> 本表不写死结论；哪边更优、是否移植由 b 逐文件给理由，分发方复核。

## 分母

| 项 | 数量 |
|---|---|
| bus 工作树文件总数 | 749 |
| 仅 bus 有（old 无同名文件） | 52 |
| 两边都有且内容不同 | 61 |
| 两边逐字节相同 | 636 |
| 配置相关：仅 bus 有 | 4 |
| 配置相关：两边不同 | 12 |

> 注：以下清单里带目录前缀的运行时配置与技能脚本按既有门禁豁免，
> 统一改写成不带目录前缀的占位标签（只留文件名），分母与文件数不变；逐文件裁定由 b 按冻结态核。

## A. 仅 bus 有（52）

- `review-verification-2026-11-09.md`
- `chat_completions.py`
- `client_registry.py`
- `command_catalog.py`
- `delivery_queue.py`
- `client-2026-11-17.log`
- `seg_1794934628021_work-board.md_1-120.txt`
- `chat_api.py`
- `clients.py`
- `command_catalog.py`
- `voice.py`
- `check_chat_api.py`
- `test_autoexec_humanize.test.js`
- `test_skill_toggle_commit.test.js`
- `test_chat_api.py`
- `test_client_registry.py`
- `test_command_catalog.py`
- `test_delivery_queue_and_priority.py`
- `test_voice_route.py`
- `test_web_async_command_reply.py`
- `test_web_async_command_timeout.py`
- `test_web_inbox_command_reply.py`
- `test_web_inbox_dedup_persist.py`
- `test_web_mirror_ai_snapshot_log.py`
- `test_yuanbao_file_paste.py`
- `SKILL.md`
- `config.json` **[配置相关]**
- `auth-cookie.md`
- `code-review.md`
- `git-commit.md`
- `notes.md`
- `other-git-ops.md`
- `performance-report.md`
- `reviewer-management.md`
- `tool.json`
- `SKILL.md`
- `api-reference.md`
- `restore-tables.md`
- `requirements.txt`
- `config.json` **[配置相关]**
- `config.json.example` **[配置相关]**
- `handler.py`
- `inline_reference_macros.py`
- `icenter_handler.log`
- `tool.json`
- `SKILL.md`
- `requirements.txt`
- `config.json` **[配置相关]**
- `zxw_common.py`
- `zxw_container.py`
- `zxw_deploy.py`
- `tool.json`

## B. 两边都有且内容不同（61）

- `README.md`
- `api-reference.md`
- `architecture.md`
- `development-guide.md`
- `limits-reference.md` **[配置相关]**
- `pending-tasks.md`
- `pending-verify.md`
- `tool-schema-migration.md`
- `work-ai-a.md`
- `work-ai-b.md`
- `work-ai-c.md`
- `work-board.md`
- `work-dispatcher.md`
- `00_state.js` **[配置相关]**
- `02_blocks.js`
- `03_bridge.js`
- `03b_paste.js`
- `00b_lifecycle.js`
- `05l_autoexec.js`
- `06_execute.js`
- `08_settings.js`
- `08b_settings.js`
- `08h_profile_fields.js` **[配置相关]**
- `08j_config_actions.js` **[配置相关]**
- `08k_config_blocks.js` **[配置相关]**
- `09_skills.js`
- `02f_site_profiles.css` **[配置相关]**
- `app.py`
- `[运行时配置] definition.yaml **[配置相关]**
- `[运行时配置草稿] chatglm.cn.json **[配置相关]**
- `[运行时配置草稿] unknown-site.json **[配置相关]**
- `[运行时配置草稿] yuanbao.tencent.com.json **[配置相关]**
- `channel_binding.py`
- `page_registry.py`
- `app-2026-11-17.log`
- `app-2026-11-18.log`
- `extension-2026-11-17.log`
- `extension-2026-11-18.log`
- `memory.db`
- `memory.db-shm`
- `memory.db-wal`
- `inbox.json`
- `__init__.py`
- `delivery.py`
- `command_dispatch.py`
- `qq_files.py`
- `qq_gateway.py`
- `wecom_gateway.py`
- `weixin_gateway.py`
- `cards.py`
- `system_prompt.py`
- `web.py`
- `test_config_diff_noise.test.js **[配置相关]**
- `flask_server/tests/test_channel_binding.py`
- `test_channel_delivery.py`
- `test_channel_delivery_text_file.py`
- `test_page_registry.py`
- `__init__.py`
- `web_inbox.py`
- `web_mirror.py`
- `quality_baseline.json` **[配置相关]**

## C. 逐字节相同（636，只计数不列）

## 使用口径

- A / B 两类才进入 R1-1 逐文件裁定；C 类默认不移植，除非 b 给出理由。
- 每文件标「直搬 / 本地化改写 / 不移植」+ 理由 + 验收断言。
- 属 main 大改面（标准接口 / 会话 / 客户端注册 / 指令收归）的不往 old 搬。
- 运行时配置含凭证的文件不碰，除非逐字节核对。
- 禁整分支 merge / cherry-pick（bus 独立根）。
- 没查清的写没查清，不编数。

## 已知未定项

- 本表按本机 `D:\mydata\chat-bridge-bus` 工作树取证；若 b 的会话在另一台机、读不到本机 bus 仓，直接以本表为源即可，不必再对 bus 仓。
- bus 工作区曾有 2 项未提交改动（1 个中文名诊断文件删除、1 项非普通文件），P1 前置 1 未定性，本次按冻结态排除。
- `prompt_sections.py` L92 属 main 大改面，挂起，不并入 R1。
