# C-9 六段占位接口边界 / 异常语义契约

> 性质：只读契约底稿，只描述返回形状与不变量，不实装执行下游。
> 基准：C-7 适配层已合入 main（20ccf641 / 合并 0897e0a）；
> C-8 对拍矩阵与九步装配推演已合入 main（6394fbf / 合并 17a8b32）。
> B-7 未交付，运行时执行权仍在旧建卡直调路径；六段仍为 declared-placeholder。
> 口径依据：分发方 11:22 定向 task 与广播「小片化、合入即续派、C-9 不依赖 B-7」。

## 全局不变量（每条边界断言均须同时成立）

- G1 **STATUS 恒为 `declared-placeholder`**：六段均为纯声明，不装配到运行时 M、
  不注册钩子、不建切换开关、不新增探测他笔是否存在的运行期分支、不切活链。
- G2 **唯一键**：标准 `tool_call.id`（`call_<nonce>`）与 tool 消息三键
  `role` / `tool_call_id` / `content`；不含消息指纹。
- G3 **异常输入不抛错**：占位期一律回显或归一为固定形状；
  边界校验、抛错、判重决策留给后续实装，本笔不实装任何执行下游。
- G4 **刷新恢复键语义**：`restore` 的 `noMessageFingerprint` 恒为 true；
  纯函数无状态，重复恢复幂等（每次返回新对象、深相等，不累加、不切换 status）。

## 一、六段逐段边界语义

### 1. parse(block)

| 输入 | 返回形状 | 不变量 |
| --- | --- | --- |
| `parse(null)` | `{ by: KEY, block: null, status: STATUS }` | G1 / G2 / G3 |
| `parse(undefined)` | 同上，`block: null` | 缺块归一为 null |
| `parse({})`（空 block） | `{ by: KEY, block: {}, status: STATUS }` | 空对象为真值，原样回显、不补字段 |
| `parse({ type: 'code', code: '...' })` | `block` 原样引用回显 | 不读 code、不产出 tool_calls |

说明：占位期不解析、不校验 type；下游装配后由标准 `tool_calls` 面接管。

### 2. buildCard(call)

| 输入 | 返回形状 | 不变量 |
| --- | --- | --- |
| `buildCard(null)` | `id: null` | 缺 call 不抛错 |
| `buildCard({})` / 缺 `id` | `id: null` | 缺 id 回落 null，不生成替代 id |
| `buildCard({ id: 'call_n1' })` | `id: 'call_n1'` | 标准键原样保留 |

说明：不校验 `function.name`、不把卡片落到消息树、不触发建卡流程。

### 3. execute(card)

| 输入 | 返回形状 | 不变量 |
| --- | --- | --- |
| `execute(null)` | `{ by: KEY, card: null, status: STATUS }` | 不抛错、不发命令 |
| `execute()`（无参） | 同上，`card: null` | 缺参归一 |
| `execute({ id: 'call_n1' })` | `card` 原样回显 | 不触发 run-command / external-call |

说明：运行时执行权仍在 `05g_cards.js` / `06_execute.js` 旧直调路径，本段占位不碰。

### 4. reply(msg)

| 输入 | 返回形状 | 不变量 |
| --- | --- | --- |
| 缺 `tool_call_id`（`null` / `{}` / `{ role: 'tool' }`） | `tool_call_id: null`，`role: 'tool'` | 缺键归一为 null |
| role 非 tool（如 `{ role: 'assistant', tool_call_id: 'call_n1' }`） | `role` 仍为 `'tool'`，`tool_call_id: 'call_n1'` | 占位契约强制归一，**不回显入参 role、不抛错** |
| 完整 `{ role:'tool', tool_call_id:'call_n1', content:'OK' }` | `role: 'tool'`，`tool_call_id: 'call_n1'` | `content` 不在返回形状内（占位期不回显） |

说明：这是最容易被误读的一条——`adapter.reply` 的 `role` 是硬编码常量，
不是入参透传；「role 非 tool」边界断言的是「归一后仍为标准 tool 消息角色」，
不是「校验后抛错」。tool 消息三键由 `standardToolMessage` 产出，本段只声明键位。

### 5. dedupe(a, b)

| 输入 | 返回形状 | 不变量 |
| --- | --- | --- |
| 同 `call_<nonce>` id（`'call_n1','call_n1'`） | `a` / `b` 原样回显 | 占位期不做判重决策、不吞并 |
| 不同 id（`'call_a','call_b'`） | `a` / `b` 原样回显 | 不比较、不排序、不去重 |
| null 入参（`(null,null)` / `(null,'call_a')`） | 缺失侧回落 `null` | 不抛错 |

说明：唯一键标准下「同 id 即同一调用」的判定留给后续实装；本期只保证形状稳定。

### 6. restore(sessionId, call)

| 输入 | 返回形状 | 不变量 |
| --- | --- | --- |
| 空 sessionId（`''` / `null` / `undefined`） | `sessionId: ''` | `String(...)` 归一 |
| 无消息指纹 | `noMessageFingerprint: true` 恒真 | G4；键不含 msgId |
| 重复恢复（同参连续多次） | 每次返回新对象、深相等，status 不变、不累加 | 幂等，不写会话状态 |
| 缺 `call` | `id: null` | 不抛错 |

说明：与 `05j_card_sig.js` / `05g_cards.js` 实改的「标准 `call_<nonce>` 优先、
旧 `msgId` 兼容双查、去消息指纹」方向一致；本段只钉声明语义，不改运行时。

## 二、逐段状态标注

| 段 | STATUS | 唯一键 | noMessageFingerprint | 实装执行下游 |
| --- | --- | --- | --- | --- |
| parse | declared-placeholder | `tool_call.id` + tool 三键 | n/a | 否 |
| buildCard | declared-placeholder | `tool_call.id` + tool 三键 | n/a | 否 |
| execute | declared-placeholder | `tool_call.id` + tool 三键 | n/a | 否 |
| reply | declared-placeholder | `tool_call.id` + tool 三键 | n/a | 否 |
| dedupe | declared-placeholder | `tool_call.id` + tool 三键 | n/a | 否 |
| restore | declared-placeholder | `tool_call.id` + tool 三键 | true（恒真） | 否 |

## 三、验收口径与只追加记录

- 范围：只新增本文件（`extend/lib/` 下契约文档）与 `flask_server/tests/js/` 下断言夹具；
  两个已合入 lib 只读 require、不改源码；不改 `extend/dialog/parts/` 任何文件，
  不改 `core/chat_completions.py` 与 `routes/chat_api.py`，不碰 B-7 协议字段退役面。
- 新增被测 JS 源文件数为 0（文档为 `.md`，不进覆盖率分母、不被 quality 扫描）；
  夹具六段各至少 1 条边界断言，反查 `STATUS` / `KEY` / `noMessageFingerprint` 与本文一致。
- 覆盖率：不引入新分母，`05j` 与两个 lib 的 line / branch 维持既有水平，
  无退化与新增欠账；本机 node v24 的「ℹ 前缀 / 分层路径」报告差异不作达标依据，
  不改钩子脚本 / 90-70 阈值 / `js_coverage_baseline.json`、不用 `--update-baseline`。
- docs 只追加：本笔不删改历史台账与总线消息；记录由 `send report` 追加到
  `docs/bus/c.md`，分发方验收结论由其追加到 work-board。
- 提交：基于实时 `origin/main` 新建提交，勿 amend 已合入历史、
  勿 force-with-lease 回退已发总线消息；一次提交收口，
  `force-with-lease` 更新 `origin/work/ai-c`，`send report` 回 hash 与实测。
