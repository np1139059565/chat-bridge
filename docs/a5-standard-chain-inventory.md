# A-5 盘点报告：标准链路侧「只为网页 AI 写的字段与分支」

> 性质：阶段 3 准备 / 只读取证 + L10 契约入口；不是删除动作（三前置未满足，见 START_HERE 第 2 节）。
> 取证基线：origin/main @ 4388363（2026-11-13 rebase 后实时尖端）。
> 范围：flask_server/core/chat_completions.py、flask_server/routes/chat_api.py、flask_server/core/system_prompt.py。

## 一、当前调用方地图

### POST /v1/chat/completions（routes/chat_api.py）

| 调用方 | 位置 | 性质 |
|---|---|---|
| flask_server/scripts/check_chat_api.py | L34 `CHAT_URL` | A-1 验收脚本（六场景） |
| flask_server/tests/test_chat_api.py | `post()` | A-1 / A-4 测试 |
| flask_server/tests/test_chat_sessions.py | L137 | A-3 会话测试 |
| flask_server/tests/test_chat_l10_contract.py | 复用 `post()` | A-5 L10 契约测试 |

**extend/（网页前端）与 remote_bridge/ 下没有任何直接调用**——网页侧当前只消费
`/v1/system_prompt`（翻译员取回标准四段），消息链路尚未走标准对话接口。

### GET /v1/system_prompt（routes/system_prompt.py + core/system_prompt.py）

| 调用方 | 位置 | 性质 |
|---|---|---|
| extend/lib/translator.js | L46 `apiFetch('/v1/system_prompt')` | 网页翻译员取回标准四段（阶段 2 已接线，实调用） |
| extend/dialog/parts/01b_bridge.js | L127 | 注释性引用（说明取回行为） |
| flask_server/tests/test_system_prompt.py | — | A-2 测试 |

### 模块级导入方（非测试）

- `chat_completions`：routes/chat_api.py（链路本体）；flask_server/scripts/check_chat_api.py（A-1 验收脚本亦直接导入）；
- `system_prompt`（core）：仅 routes/system_prompt.py；
- `routes.chat_api` 蓝图：app.py 注册（端点存活来源）；scripts/check_chat_api.py（验收脚本导入蓝图打点）。

## 二、「只为网页 AI 写的字段与分支」逐条盘点

| # | 位置 | 内容 | 当前调用方 | 可摘除性 | 摘除前置 |
|---|---|---|---|---|---|
| 1 | chat_completions.py L131 `_sanitize_tool_calls` | 清洗 tool_calls 只留 id/type/function，docstring 明写「丢弃网页场景附加字段」 | normalize_messages（标准入口唯一路径）；附加字段的产生方在翻译员旧直调路径（C-6 盘点范围） | 阶段 3 评估项：保留为防御亦可 | 三前置同时满足 + 翻译员确认只发标准 tool_calls（属前置 3「旧路径无调用方」的子项） |
| 2 | chat_api.py `_build_response` 的 `messages` 扩展字段 | 回传合并后完整历史，供客户端断言与续接（决策 14） | 测试断言 + 翻译员未来续接 | 不可摘（决策 14 明文设计） | 需分发方修订决策 14 并下发 |
| 3 | chat_api.py `site_key` 扩展字段 | 会话键回传（决策 14） | 同上 | 同上 | 同上 |
| 4 | chat_completions.py L184 `_response_to_body` | 兼容 Flask Response 与 (Response, status) 元组 | `_dispatch_tool`（复用 routes/tools.py 管线） | 属管线兼容、非网页专用 | —（保留） |
| 5 | system_prompt.py 全文件 | 四段式（身份/规则/技能/通则）；方言内容明文不进本文件 | translator.js 消费 | 无网页专用字段 | —（无需摘除） |

结论：三个文件里真正的「网页专用」只有 #1 的清洗语义（防御性）与 #2/#3 的扩展字段（决策 14 有意设计）；
标准链路本体（role 白名单、tool_call_id 防重放、幂等合并、原子落盘）与场景无关，阶段 3 无需为摘除而动。

## 三、L10 契约入口（本次交付）

routes/chat_api.py 新增三个函数，既有链路语义零改动：

- `register_pre_dispatch_hook(fn)`：注册分发前钩子；`fn(history) -> None | list`；
  None 沿用、list 整体替换（分发输入、落盘、响应 messages 三步一致）；多钩子按注册顺序链式；
  返回非 None/list 抛 TypeError；钩子异常不吞（请求失败且无部分副作用）；线程安全、单请求用调用时点快照。
- `clear_pre_dispatch_hooks()`：清空注册表（测试隔离用）。
- `_run_pre_dispatch_hooks(history)`：唯一点位——历史合并之后、`_execute_pending` 之前。

「模型未接」即以此为显式可插拔入口：接真实模型时注册一个把 history 送模型的钩子即可，
不动链路本体、不需要切换开关（符合任务边界）。

契约测试：flask_server/tests/test_chat_l10_contract.py，9 条（收参语义 / 累积历史 / 替换并落盘 /
链式顺序 / 每请求一次 / 产出即分发输入 / 异常无部分副作用 / 违约 TypeError / 用例间不泄漏）；
夹具与样板从 tests.test_chat_api 导入复用（不复制，结构质量 dup 基线零新增）。

## 四、验收自测

- `python -m pytest tests/test_chat_api.py tests/test_chat_sessions.py tests/test_chat_l10_contract.py -q` → 41 passed；
- `scripts/quality_rules.py` exit 0、[新增] x0（dup 组总数回到基线 94）；
- pre-commit 七道全过（js-tests 本机实跑 Passed，分发方环境复验）。
