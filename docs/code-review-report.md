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

`scripts/check_quality.py` 扫描的超标函数数量：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 超标函数数 | 19 | 18 |
| `handle_command` | 118 行 / cc37 | 已消除 |
| `_blocks_to_text` | 38 行 / cc24 | 已消除 |
| `command_panel.py` 行数 | 449 | 412 |
| 超大文件（>450 行） | 无 | 无 |

新增超标项中，`validate_command`（cc23）与 `help_text`（cc11）由原 `command_panel.py`
迁入 `command_registry.py`，属位置变化而非新增复杂度。

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

### 4.3 跨文件重复代码：不处理

扫描报出 `extend/content/00_state.js` 与 `skills/debug_chrome/extension/content/02_drawer.js`
之间的连续重复块。**这是架构约束，不是缺陷。**

两者是各自独立的 Chrome 扩展，运行时无法加载同一份代码，只能人工保持同步。
抽取公共文件会制造「看似统一、实则各自为政」的假象。
相关代码中已注明同步要求（亮度阈值、回退策略、监听属性列表需两侧同步修改）。

---

## 五、维护约定

- 内置指令：在 `command_registry.BUILTIN` 登记命令与说明，在 `command_panel._BUILTIN_HANDLERS`
  登记处理函数。两表键必须一致（导入期自检会拦住不一致）。
- 消息块类型：在 `message_router._BLOCK_HANDLERS` 登记处理函数。
- 提交前：`python scripts/check_quality.py`；安装钩子后由 pre-commit 自动校验。
