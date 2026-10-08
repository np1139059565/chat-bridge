# 代码走查报告（chat-bridge）

走查范围：本地工具服务（`flask_server/`）与镜像插件（`extend/`）。
走查方法：静态阅读 + `scripts/check_quality.py` 客观扫描 + 冒烟与修复验证脚本。

---

## 一、结论摘要

工程整体代码质量处于上游水平：模块边界清晰，注释解释「为什么这么做」而非「这行在干嘛」，
错误分类体系（parameter / environment / tool_internal）设计完整。

本次走查识别出三类可优化项，前两类已修复，第三类整理为下方待办清单。

---

## 二、已修复项

### 修复 1：`handle_command` 圈复杂度过高

| 项 | 修复前 | 修复后 |
|---|---|---|
| 文件 | `remote_bridge/command_panel.py` | 同左 |
| 函数行数 | 118 行 | 已消失（改为表驱动） |
| 圈复杂度 | 37 | 已消失 |

**问题**：原实现用 18 个连续的 `if cmd == "..."` 分支处理内置指令。
新增一条指令需要改动主分发函数，且圈复杂度是阈值的近 4 倍。

**改法**：把内置指令从「命令名 → 描述」的表，升级为「命令名 → 处理函数」的分发表。
主函数缩短为「解析命令 → 查表 → 调用」，新增指令只需写一个处理函数并登记到表中。

**防错**：指令表与处理函数表分离后，若只改一处会导致「指令可见但不可用」。
为此在 `command_panel.py` 导入期加入 `_check_handler_table()` 自检，
两表键不一致时直接抛错拦住，避免错配在运行时才暴露。

### 修复 2：`command_panel.py` 文件过长

| 项 | 修复前 | 修复后 |
|---|---|---|
| 文件行数 | 449 行（阈值 450） | 412 行 |

**问题**：文件距 450 行拆分阈值仅差 1 行。若先拆函数而不拆文件，
拆出的小函数塞回同一文件会让行数继续增长、直接撞线。

**改法**：按职责拆出 `remote_bridge/command_registry.py`（149 行），承载纯静态知识：

- `BUILTIN`：内置指令表（命令名 → 说明 + 快捷键）
- `resolve_cmd`：别名 → 主命令名
- `validate_command`：自定义指令合法性校验
- `help_text`：`/help` 的回复文本
- `register_panel`：指令面板注册

`command_panel.py` 只保留「指令怎么执行」，并从 `command_registry` 重导出
`register_panel` / `validate_command`，保证 `__init__.py` 与 `routes/bridge.py`
的既有引用无需改动。两模块单向依赖，无循环引用。

### 修复 3：`_blocks_to_text` 圈复杂度过高

| 项 | 修复前 | 修复后 |
|---|---|---|
| 文件 | `remote_bridge/message_router.py` | 同左 |
| 圈复杂度 | 24 | 已消失 |

**问题**：单个函数用 7 个 `elif` 分支处理不同消息块类型。

**改法**：拆为「块类型 → 处理函数」的表（`_BLOCK_HANDLERS`），
每种类型一个短函数。新增块类型只需登记，无需改动主流程。
未登记类型不产出文本，与旧实现语义一致。

**回归验证**：对 thinking / paragraph / heading / list / table / code / 工具调用 / 未知类型
逐类构造输入比对，输出与旧实现一致（`push_thinking` 开关两种取值均验证）。

---

## 三、修复效果对比

`scripts/check_quality.py` 扫描的超标函数数量（阈值：函数体 > 30 行 或 圈复杂度 ≥ 10）：

| 指标 | 该轮修复前 | 该轮修复后 |
|---|---|---|
| 超标函数数 | 19 | 0 |
| 超大文件（>450 行） | 无 | 无 |

> 上表是**该轮修复工作完成时**的快照。此后代码继续演进，超标函数会重新出现，
> 属正常现象，不代表该轮修复失效。**当前实况请以 `python scripts/check_quality.py` 为准。**
> 复核时（本轮走查）测得超标函数 78 个：其中同时超行数与复杂度 33 个、仅超行数 24 个、仅超复杂度 21 个。
> 治理超标函数是持续工作，不是一次性归零；阈值口径见脚本，历史快照仅作对照。

分两轮推进：首轮处理圈复杂度最高、影响面最大的三处；
后续轮次把其余超标函数逐一拆分，直至当时扫描报告「超长 / 高圈复杂度函数」为空。

各函数采用的拆分手法：

| 位置 | 修复前 | 手法 |
|---|---|---|
| `command_panel.handle_command` | 118 行 / cc37 | 指令表驱动，主流程改为查表调用 |
| `message_router._blocks_to_text` | cc24 | 块类型 → 处理函数的映射表 |
| `command_registry.validate_command` | cc23 | 拆出名称冲突、子指令存在性校验 |
| `qq_client.send_c2c_image` / `_on_message` | cc18 | 上传与发送分离；下行按 op 查表分派 |
| `routes/bridge.bridge_result` | cc18 | 取上下文、送达结果、发送图片各成一函数 |
| `external_tools.poll` / `dispatch` | cc12 / cc11 | 页面状态登记、命令筛选、超时撤回分离 |
| `message_router.handle_report` | cc20 | 筛选新消息、判定推送、推送单条分离 |
| 其余（`prompt_sections` / `tools_impl` / `__init__` / 钩子等） | cc10–11 | 按职责抽出子函数 |

拆分只移动代码位置、不改变行为；每轮结束后跑 `_smoke_ct.py` 与 `_verify_fixes.py` 回归，
最终两者均通过（`SMOKE OK` / `ALL OK`）。

---

## 四、待办清单

### 4.1 QQ 接口核对结果

`remote_bridge/` 下原标注 `[待核对]` 的位置已逐一对照 QQ 开放平台官方文档核对确认，
代码与注释中的不确定性标记已清除。核对结果如下：

| 文件 | 核对项 | 官方接口 / 取值 | 状态 |
|---|---|---|---|
| `qq_client.py` | 接口地址 | `https://api.sgroup.qq.com` | 一致 |
| `qq_client.py` | 单聊消息 intents | `GROUP_AND_C2C_EVENT = 1 << 25` | 一致 |
| `qq_client.py` | 取 token 请求体字段 | `appId` / `clientSecret` | 一致 |
| `qq_client.py` | 单聊发送接口 | `POST /v2/users/{openid}/messages` | 一致 |
| `qq_client.py` | 富媒体上传接口 | `POST /v2/users/{openid}/files`，`file_type=1`，`msg_type=7` | 一致 |
| `qq_gateway.py` | 用户 openid 字段 | `author.user_openid` | 一致 |
| `command_registry.py` | 指令面板接口 | `POST /v2/panels`、`PUT /v2/panels/{panel_id}` | 一致 |
| `command_registry.py` | 自定义菜单接口 | `GET /v2/menu`、`PUT /v2/menu` | 一致 |

### 4.2 已知问题（承接 `development-guide.md`）

| 编号 | 位置 | 问题 |
|---|---|---|
| M3 | `flask_server/card_bus.py` | 卡片投递为全局 claim，多标签页可能串台 |
| D2 | `skills/debug_chrome/extension/content/03_heartbeat.js` | 抽屉折叠即停轮询，10 秒后判离线（仅影响指示灯） |
| D4 | `skills/debug_chrome/extension/content/00_namespace.js` | 后端地址端口硬编码 5000 |
| D5 | `extend/content/00_state.js` | DeepSeek 输入框选择器含哈希类 |

### 4.3 跨文件重复代码：分类与处理

重复代码按性质分四类，处理方式各不相同：

| 类别 | 判据 | 处理 |
|---|---|---|
| 结构约定 | 各分片文件统一的 IIFE 包裹、命名空间声明、`'use strict'` | 保留不动。属模块约定，抽走反而破坏可读性；扫描已按样板行排除 |
| 同步副本 | 由单一真源经脚本同步生成的副本，内容刻意一致 | 保留副本，扫描跳过副本、只留真源；改动只写真源 |
| 可抽逻辑 | 跨文件、语义一致的实现片段 | 抽公共函数或公共模块，各调用点改为引用 |
| 数据类表格 | 纯静态数据（如样式片段） | 视成本决定，通常保留 |

**同步副本机制（两个独立扩展间）**：

`extend/` 与 `skills/debug_chrome/extension/` 是两个独立的 Chrome 扩展，
运行时无法加载同一份代码。为消除「改一处忘一处」的分叉风险，采用「单一真源 + 同步副本」：

- 真源：`shared/host_theme.js`（宿主明暗主题探测实现）。
- 副本：`extend/lib/host_theme.js`、`skills/debug_chrome/extension/shared/host_theme.js`，
  文件头带「自动生成，请勿直接编辑」标记。
- 同步：`python scripts/sync_host_theme.py` 生成副本；`--check` 校验副本与真源是否一致。
- 消费：两处 `detectHostTheme` 改为薄包装，调用 `window.HostThemeDetector.detect()`。

如此，改动只发生在真源一处，副本由脚本保证一致，「看似统一、实则各自为政」的隐患由校验兜住。

---

## 五、维护约定

- 内置指令：在 `command_registry.BUILTIN` 登记命令与说明，在 `command_panel._BUILTIN_HANDLERS`
  登记处理函数。两表键必须一致（导入期自检会拦住不一致）。
- 消息块类型：在 `message_router._BLOCK_HANDLERS` 登记处理函数。
- 提交前：`python scripts/check_quality.py`；安装钩子后由 pre-commit 自动校验。
- 共享真源：改动 `shared/host_theme.js` 后运行 `python scripts/sync_host_theme.py` 同步副本；
  `--check` 模式校验副本是否与真源一致。副本文件请勿直接编辑（文件头已标注）。
- 日志落盘：统一走 `core/log_sink.py` 的 `DayFileSink`；`app_log` 与 `bridge_log` 各持一个实例，
  不再各自实现按天分文件逻辑。
- 安全 JSON 解析：统一用 `core/json_utils.safe_json_loads`；记忆子系统各模块的 `_loads` 为薄包装。
- CORS 预检：由 `app.py` 的 `_register_options` 集中处理，路由函数不再各自判断 `OPTIONS`。
