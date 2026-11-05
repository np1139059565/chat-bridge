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
| 重复代码块（连续 5 行，跨文件） | 79 组 |

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
| 2 | `scripts/hooks/` 两个检查脚本的公共部分 | 5 组 | 待开始 |
| 3 | `qq_client` ↔ `wecom_client` 的公共发送逻辑 | 8 组 | 待开始 |
| 4 | 三个通道适配器的公共部分 | 9 组 | 待开始 |
| 5 | 对话框分片的重复段 | 9+3 组 | 待开始 |
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
