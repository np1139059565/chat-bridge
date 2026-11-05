# 结构质量存量清理追踪

> 用途：追踪质量闸门登记的存量债务，逐批清理。
> 每批完成后更新本文件与 `scripts/quality_baseline.json`，使基线成为净减少的度量。

## 一、机制

闸门 `scripts/quality_rules.py` 跑十二项检查，存量登记在 `scripts/quality_baseline.json`。
清理后运行 `python scripts/quality_rules.py --update-baseline` 收敛基线；
**基线数字只应下降**，上升意味着接受了新增欠账，须在提交信息里说明原因。

## 二、存量分布（2026-11-05）

十二项中十项达标，剩余两项：

| 检查项 | 存量 |
|---|---|
| 超长 / 高复杂度函数（>30 行 或 cc ≥10） | 165 条 |
| 重复代码块（连续 5 行，跨文件） | 58 组 |

### 2.1 高复杂度函数按目录

| 目录 | 条数 |
|---|---|
| `flask_server/remote_bridge/` | 76 |
| `flask_server/core/` | 30 |
| `flask_server/routes/` | 16 |
| `flask_server/tools/` | 15 |
| `flask_server/custom_tools/` | 7 |
| `flask_server/web_bridge/` | 7 |
| 其余（scripts / skills / tests 等） | 14 |

### 2.2 重复代码块按文件对

| 组数 | 文件对 |
|---|---|
| 16 | `tests/test_message_router_lock.py` ↔ `tests/test_message_router_window.py` |
| 9 | `extend/dialog/parts/05_messages.js` ↔ `05i_files.js` |
| 8 | `remote_bridge/qq_client.py` ↔ `wecom_client.py` |
| 5 | `remote_bridge/adapters/qq.py` ↔ `adapters/wecom.py` |
| 5 | `scripts/hooks/check_js_tests.py` ↔ `check_syntax.py` |
| 4 | `extend/content/06_picker.js` ↔ `skills/debug_chrome/extension/content/04_element-selector.js` |
| 4 | `remote_bridge/adapters/wecom.py` ↔ `adapters/weixin.py` |
| 其余 | 多对，各 1~3 组 |

## 三、批次计划

原则：**先做风险低、收益大的**。测试代码与脚本层优先于运行时业务代码；
同一文件对的多组重复应一次处理完，避免反复动同一文件。

| 批次 | 范围 | 组数/条数 | 状态 |
|---|---|---|---|
| 1 | 两份 message_router 测试的公共夹具 | 16 组 | 已完成 |
| 2 | `scripts/hooks/` 两个检查脚本的公共部分 | 5 组 | 已完成 |
| 3 | `qq_client` ↔ `wecom_client` 的公共发送逻辑 | 8 组 | **评估后不做**（见 4.1） |
| 4 | 三个通道适配器的公共部分 | 9 组 | **评估后不做**（见 4.2） |
| 5 | 对话框分片的重复段 | 13 组 | **评估后不做**（见 4.3） |
| — | 高复杂度函数：`remote_bridge/` 分批 | 76 条 | 待排期 |
| — | 高复杂度函数：其余目录 | 89 条 | 待排期 |

## 四、批次记录

### 批次 1：两份 message_router 测试的公共夹具（2026-11-05）

**问题**：`test_message_router_lock.py` 与 `test_message_router_window.py` 各自复制了一份
「模拟存储 + 打补丁」脚手架，`_StoreMock` 类逐字相同，`_Base.setUp` 前半段也相同。
任一处调整都要改两遍，漏改会让两份测试的前置环境悄悄分叉。

**做法**：新建 `flask_server/tests/message_router_fixtures.py`，提供 `StoreMock` 与
`RouterTestBase`。两份测试改为继承共享基类；窗口那份的差异（需要隔离模块级窗口状态）
通过覆盖 `extra_patches()` 追加，而不是复制整段 `setUp`。

**顺带修的隐患**：两份测试原先只把 `flask_server` 加进 `sys.path`，单跑时找不到同级模块。
现已把 tests 目录也加入路径，单独运行任一文件均可行。

| 文件 | 行数变化 |
|---|---|
| `test_message_router_lock.py` | 162 → 116 |
| `test_message_router_window.py` | 271 → 241 |
| `message_router_fixtures.py` | 新增 96 |

**验证**：两份合计 16 项用例全过；这两份文件之间的重复组从 16 降到 0。
全量后端 625 项、前端 157 项通过。

**基线变化**：已知条目 314 → 228（净减 86）；跨文件重复组 79 → 63。

### 批次 2：`scripts/hooks/` 的「找 node」重复（2026-11-05）

**问题**：`check_js_tests.py` 与 `check_syntax.py` 各自复制了一份 `_find_node()`，
逐字相同。任一处调整都要改两遍，漏改会让两个钩子对「有没有 node」判断不一致——
表现为一个钩子跑、另一个跳过。

**做法**：新建 `scripts/hooks/hook_common.py`，提供 `find_node()`。两个脚本删除本地定义，
改为 `from hook_common import find_node as _find_node`，调用处一行未改。

**为何不并入 `scripts/qcommon.py`**：那是质量检查脚本（`check_quality` / `quality_rules`）的
公共层，服务于「扫描全工程」；本模块服务于「提交前钩子」。职责不同，合并会让两边耦合。

| 文件 | 行数变化 |
|---|---|
| `check_js_tests.py` | 165 → 152 |
| `check_syntax.py` | 160 → 145 |
| `hook_common.py` | 新增 40 |

**验证**：两个钩子实际执行均正常（`check_syntax` 校验通过、`check_js_tests` 157 项通过）；
`scripts/hooks/` 内的重复组 5 → 0。全量后端 625 项通过。

**基线变化**：已知条目 228 → 223（净减 5）；跨文件重复组 63 → 58。

### 4.1 批次 3 评估：不做

**可抽内容**：两个客户端的连接骨架——websocket 导入兜底、`start`/`stop`、重连循环、
错误与关闭回调，共约 60 行。

**不做理由**：这些属于长连接生命周期，测试覆盖实况：

| 方法 | 企业微信 | QQ |
|---|---|---|
| `start()` | 1 次（仅「无凭证失败」分支） | 0 |
| `stop()` | 0 | 0 |
| `_run_forever()` | 0 | 0 |
| `_connect_once()` | 0 | 0 |
| `_on_error` / `_on_close` | 0 | 0 |

现有 28 个用例全在协议层（帧构造、拆分、编解码、参数校验），连接生命周期一行未测。
且这类代码依赖真实 WebSocket 连接与断线重连，单元测试需先造假的 websocket 服务，
成本远高于收益。出错表现是「连不上 / 断线不重连 / 停不掉」，只在生产暴露。

抽 60 行重复换这个风险不成比例。

### 4.2 批次 4 评估：不做

**可抽内容**：三个通道适配器之间的 9 组重复。

**分类后**：1 组是导入语句（属「依赖相同」）、5 组是文档字符串模板（各通道照同一规范写）、
真实逻辑重复仅 3 组。

**关键发现：`merge_batch` 是「巧合相同、理由不同」，不可合并**

| 通道 | 代码 | 注释里写的理由 |
|---|---|---|
| 企业微信 | 相同 | 「企微无配额压力，但逐条推会在手机上刷出很多条」 |
| 微信 | 相同 | 「微信必须合并：每条用户消息只给约 10 条的回复池」 |
| QQ | 不合并 | 默认返回 None，逐条发送 |

抽到基类等于抹掉「为什么合并」的区别：后来者看到基类有默认合并实现，
会以为所有通道都该合并，而 QQ 恰恰不该。这是把巧合当成本质。

`prepare_items` 是真重复（两个通道都只是转发 `bridge_store.merge_pending`），但仅 4 行；
且三个适配器零测试覆盖（`test_push_pipeline_branches.py` 用的是自写 `FakeAdapter`，测管线不测适配器），
改动只能人工验证。收益与风险不成比例。

### 4.3 批次 5 评估：不做

**13 组检测命中，实际是三处重复**（相邻窗口会把一处重复计成多组）：

| 处 | 位置 | 性质 |
|---|---|---|
| 1 | `00_data.js` ↔ `05c_prompt.js` | 4 行孤儿消息兜底，两处独立实现 |
| 2–4 | `01g_external_cards.js` ↔ `01j_card_consume.js` | 卡片字段清单，16 个字段中约 12 个相同 |
| 5–13 | `05i_files.js` ↔ `05_messages.js` | 待处理图片与用户消息的文本匹配，约 15 行 |

**关于第 2 处：这是拆分带来的可见性变化，不是历史遗留**

那段重复原本在 `01e_bridge_actions.js` 的 `consumeQqImage` 里，与 `01g` 的 `buildExternalCard` 一直有字段重复，
只是两个文件差异够多、没被检出。批次 1 之前把 `consumeQqImage` 拆到 `01j_card_consume.js` 后，
它与 `01g` 变得更像，重复才暴露。挪位置暴露了隐藏重复，是好事，但须记明来源。

**不做理由：前端分片层缺行为测试**

现有前端测试只对 4 个分片做专项验证（`05j` / `05g` / `05h` / `05f`），
上述三处涉及的文件都不在覆盖内。`test_dialog_boot` 会按 `dialog.html` 全量加载全部脚本，
能发现**语法错误与方法缺失**，但发现不了**行为偏差**——卡片字段漏一个、文件挂错消息，都不会报错。

即：`extend/dialog/parts/` 下业务逻辑的改动安全网只有「语法没错、方法还在」。
在这个网下继续抽重复，等于每次重构都在赌。

**结论**：先补前端行为测试，再谈该区域的重复清理。顺序反了，收益不抵风险。
该缺口已记入 `pending-tasks.md`。
