# 阶段 2 翻译员验收报告（G-C）

- 任务 id：`dispatcher-20261117T220241-bb1485`
- 身份：`actor=c`，分支 `work/ai-c`
- 依据：`docs/split-mirror-and-tools-service.md` 第七节阶段 2 五项、第四节 4.1-4.6；分发方 23:28 广播内联全文、23:57 口径定稿、22:58 定向 c 裁定
- 验收形态：逐项脚本化自测（`flask_server/tests/js/test_gc_translator_acceptance.test.js` 与 `test_gc_translator_logic.test.js`），不改业务代码、不改已合入夹具

## 只读合入预演结论（22:58 要求写入）

- `fetch --prune` 后 `origin/main` 尖端 `de8ccc2`；本方旧提交 `9f77b87` 非其祖先，`7458b45`（batch1 解耦成果）是其祖先。
- `9f77b87` 改动的 30 个文件：11 个与 `origin/main` blob 完全一致（10 份夹具改写 + 共享 fixture），18 个两边均已删除，唯一 `both_diff` 为 `docs/work-ai-c.md`（main 侧追加了 G-C 任务书）。即本方旧提交实质内容已全部在 main。
- 临时 worktree 真跑 `git merge --no-commit --no-ff origin/main`：`merge_exit=1`，`UU` 冲突文件清单仅 `docs/work-ai-c.md` 一处；其余为 main 侧新增/修改文档，无 delete/modify 文本冲突。worktree 已 `merge --abort` 并清理。
- 对齐动作：本地 `work/ai-c` 重置到 `origin/main`（丢弃 `9f77b87` 重复引用，内容经 `7458b45` 全在 main），`ahead/behind = 0/0`、工作区干净。未 force 推 main、未改已合入夹具、未重复应用同批文件。
- 推送形态：`origin/work/ai-c` 旧尖端为 `9f77b87`，交付时以 `force-with-lease` 更新自己分支引用（只动自己分支，不动 main、不丢内容），此形态如实登记。

## 阶段 2 五项与 4.1-4.6 逐项验收

| 编号 | 项 | 结果 | 证据 |
|---|---|---|---|
| S2-1 | 取回标准提示词 + 追加方言说明 | PASS | `translator.fetchStandard` 取 `/v1/system_prompt`；`05c_prompt.js` 调 `T.composePrompt(T.state.standard, dialect)`，标准四段前置、原模板作方言追加 |
| S2-2 | `bridge-chat-call` → 标准 `tool_calls` | PASS | `toToolCalls` 产出 `{id:call_<nonce>,type:function,function:{name,arguments}}`；`fromBlocks` 多块取首个并告警 |
| S2-3 | 标准 `tool` 消息 → `bridge-chat-res` | PASS | `toToolMessage` 产出 `role/tool_call_id/name/content`；`fromToolMessage` 剥 `call_` 前缀回填 nonce，成败信封带出 |
| S2-4 | 语言包从 `/api/clients` 取回 | PASS | `fetchLanguagePack` 按 `site_key` 取 `custom_config`；`dialects.languagePack` 原样不解释；`01b_bridge.js` 与 `05_index.js` 接线 |
| S2-5 | 指令执行端对接服务端下发定义 | PASS | `fetchCommands` 同批取 `/api/commands` 与 `/api/commands/help`；`01b_bridge.js` 的 `refreshCommandDefinitions` 登记 `commandDefinitions` |
| 4.1 | 四支方言处理函数 | PASS | `dialects.defaultHandlers` 的 locate / write / send / generating 均走注入 dom 原语 |
| 4.2 | 语言包寄存、服务端不解释 | PASS | 规格四节原文 + `custom_config` 原样存取（中文/嵌套/null 深比较） |
| 4.3 | 提示词拼装 | PASS | `defaultDialect` 三段 + 工具清单 + 语音约定；`composePrompt` 拼接 |
| 4.4 | 调用解析与结果回传、多调用拦截 | PASS | 双向翻译 + `multiple_tool_calls` 告警 |
| 4.5 | 卡片语义与执行状态 | PASS | 规格四节归属约束 + 一个本体多套方言覆盖表 |
| 4.6 | 网页原文存储 | PASS | 规格四节「刷新不丢 / 不设过期 / 唯一清理入口」约束逐字核对 |

流程可用性：既有 `test_translator.test.js`（纯逻辑）、`test_translator_wiring.test.js`（全量 bootDialog + spy 计数）、`test_translator_wiring_require.test.js`、`test_05c_prompt_schema_coverage.test.js` 构成网页 AI 全流程可用且行为与改造前一致的回归面；本笔新增两份夹具逐项反查与实跑，不改动既有夹具。

## pass / fail 分母

- 新增验收夹具：`node --test` 两份合计 `12 / 12 pass`、`0 fail`（验收反查 6 + 纯逻辑实跑 6）。
- 前端全量：`check_js_tests.py` `711 / 711 pass`、`0 fail`；本机 node v24 打印「跳过覆盖率门禁：未解析到覆盖率报告」，如实标注为跳过、由分发方环境复验，不作达标依据。
- 结构质量：`quality_rules.py rc=0`、零 `[新增]`（首轮因纯逻辑夹具注释率 3.9 percent 触发 1 条新增，已只改本笔新增夹具补足逐行中文注释后归零，未动基线 / 钩子 / 已合入文件、未用 --update-baseline）；`check_doc_sync.py rc=0`。
- 七道钩子：`pre-commit run --all-files` 七道逐个 Passed、`pc_exit=0`；`git diff --check rc=0`。
- 后端串行单进程全量 pytest：本笔 `1091 passed / 18 failed`；在临时 worktree 检出 `origin/main` 跑同口径全量，基线同为 `18 failed / 1091 passed`（分布：test_web_async_command_reply.py(1)、test_web_async_command_timeout.py(5)、test_web_inbox_command_reply.py(2)、test_web_inbox_dedup_persist.py(4)、test_web_mirror_ai_snapshot_log.py(3)、test_yuanbao_file_paste.py(3)）。本笔零 `.py` 改动（新增仅 `.js` 夹具与 `.md` 报告），失败集合与基线一致，属基线既有；G-A 任务书已点名「18 failed 的 stash 对照归因证据」，如实登记、不掩盖、不代 a 归因、不拿「已知波动」糊过去。

## 缺口清单

1. `yuanbao` 识别：方言覆盖表已登记 `yuanbao` 条目，但当前为空覆盖（复用默认处理函数），站点专属输入框/发送/生成态选择器未取证落地；并入缺口面，本笔不单独开工。
2. 独立工具配置页：规格未单列页面验收项，结论源四份旧复核块称「独立工具页 0」已被分发方更正为判据用错，但页面级脚本化验收未纳入本笔阶段 2 五项；并入缺口面。
3. 实机端到端：网页 AI 真实浏览器全流程由用户侧确认，本机无浏览器环境，不代勾。
4. 阶段 3 红线：旧标记摘除硬前置三项未满足，`STATUS` 恒 `declared-placeholder`，运行时执行权仍绑旧建卡直调链；不自行摘除、不翻状态、不装配运行时 M、不推 main。

## 范围与边界

- 只新增 `docs/gc-stage2-translator-acceptance.md` 与 `flask_server/tests/js/test_gc_translator_acceptance.test.js`、`test_gc_translator_logic.test.js` 三份文件；零业务代码改动。
- 不碰 `flask_server/` 下 `.py`、不碰 a/b 范围、不碰活链九文件与 `standard_chain_adapter.js` / `standard_chain_contract.js` 本体、不改 10 份已合入夹具与共享 fixture、不翻 STATUS、不自填 `[答复]`。
- 回执经 `doc_bus.py send --me c --to dispatcher --kind report --reply-to dispatcher-20261117T220241-bb1485` 推送；完成后回 `wait --round 40 --tick 10` 监听。
