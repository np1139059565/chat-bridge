# 外部指令规范（chat-bridge）

> 状态：设计稿。外部指令的注册接口尚未实现；本文先定规矩，实现后按此文逐条核对。
> 适用对象：希望向宿主注册 QQ 指令的外部工具（skill）。

---

## 一、定位

「指令」指 QQ 消息里以 `/` 开头的命令，例如 `/rf`（刷新并打开抽屉）。
用户在 QQ 里敲下指令，宿主识别、路由、执行。

本文规定两件事：
1. 现有指令系统长什么样（内置 + 自定义）；
2. 外部工具如何注册自己的指令（新机制）。

---

## 二、现有指令系统

### 2.1 内置指令

表驱动，两张表分离：

| 表 | 文件 | 管什么 |
|---|---|---|
| `BUILTIN` | `remote_bridge/command_registry.py` | 命令名 → 说明 / 别名 / 分组 |
| `_BUILTIN_HANDLERS` | `remote_bridge/command_panel.py` | 命令名 → 执行函数 |

- 两表的键必须一致，导入期由 `_check_handler_table()` 自检，错配直接报错。
- 别名解析：`resolve_cmd()` 把别名（如 `/rf`）归一为主命令名（`/refush`）。
- 执行路径：处理函数调 `_dispatch()` → 经卡片总线创建 `drawer-command` 卡片 →
  **宿主的抽屉**轮询取走并执行。

### 2.2 自定义指令

存在配置的 `commands` 字段里，由用户在设置页维护，三类：

- 组合（`steps`）：按序执行多条子指令，步骤间有间隔。
- 采集（`collect`）：点按钮取 Markdown。
- 点击（`selector`）：点击指定元素。

合法性由 `validate_command()` 校验：命令名须以 `/` 开头、不得与内置或其它自定义指令（含别名）冲突、组合的子指令必须存在。

---

## 三、外部指令注册（新机制）

### 3.1 目标

让外部工具**像声明工具一样声明指令**：宿主扫描后纳入指令列表，用户敲指令时命令**直接路由给该扩展执行**，宿主只当「目录 + 转接器」，不介入扩展内部。

关键判据：**按下指令后，动手的是扩展自己，而不是宿主。** 否则与现在 `/rf` 靠 `sessionStorage` 旁路通知 `debug-chrome` 没有本质区别。

### 3.2 声明位置与格式

在 `skills/<name>/tool.json` 中增加 `commands` 数组，与 `tools` 并列：

```json
{
  "provider": "debug_chrome",
  "tools": [ /* 原样 */ ],
  "commands": [
    { "name": "/dbg-open", "alias": "/do", "desc": "打开调试抽屉", "tool": "open_drawer", "params": {} },
    { "name": "/dbg-close", "alias": "/dc", "desc": "关闭调试抽屉", "tool": "close_drawer", "params": {} }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 主命令名，须以 `/` 开头 |
| `alias` | 否 | 快捷键，须唯一、不得与既有别名冲突 |
| `desc` | 是 | 说明，进 `/help` 与指令面板 |
| `tool` | 是 | 映射到本扩展的哪个工具（即 `TOOL_HANDLERS` 的键） |
| `params` | 否 | 固定参数，敲指令时原样随命令下发 |

### 3.3 执行通道

复用现成的 external 工具通道，不新开管道：

```
用户敲 /dbg-open
  → command_panel 查外部指令注册表
  → 命中 provider=debug_chrome, tool=open_drawer
  → 走 external_tools 通道入队
  → debug-chrome 轮询取走、自己执行
  → 结果按原路回传
```

宿主全程不碰扩展内部状态。这与 AI 调 `open_drawer` 走的是同一条路，扩展只维护一份执行逻辑。

### 3.4 命名与快捷键

- **命名空间**：外部指令建议统一前缀（如 `debug_chrome` 用 `/dbg-`），便于辨认与避让。
- **快捷键**：两字符为宜（如 `/do`），越短越好按，但越短越易撞车。
- **冲突校验**：主名与别名都要过 `_check_name_free()`，与内置（含别名）、其它自定义、其它外部指令均不得重名。
- 快捷键被占用时，注册失败并回执，由扩展换名重报。

### 3.5 配额

- 不再硬限「20 个元素」。面板元素超出平台上限时**截断并记录**，保留优先级高者，不阻断注册。

### 3.6 生命周期

- 扩展卸载 / 下线（取消上线）时，其指令一并**注销**，不得在 `/help` 或面板里留下按了没反应的死开关。
- 注册表以 `provider` 为键聚合，便于整体注销。

---

## 四、示例：debug_chrome

| 主命令 | 快捷键 | 作用 | 映射工具 |
|---|---|---|---|
| `/dbg-open` | `/do` | 打开调试抽屉 | `open_drawer` |
| `/dbg-close` | `/dc` | 关闭调试抽屉 | `close_drawer` |
| `/dbg-side` | `/dl` | 抽屉左右切换 | `switch_drawer_side` |
| `/dbg-settings` | `/dt` | 打开设置页 | `open_settings` |
| `/dbg-back` | `/db` | 从设置页返回 | `close_settings` |

其中 `open_drawer` 等工具需在 debug-chrome 侧补齐（现仅注册查询类工具）。

---

## 五、待定问题

1. 外部指令是否参与「组合指令」的子指令集？建议参与，但需防跨 provider 的循环依赖。
2. 指令面板注册接口（`register_panel`）当前仅打印待注册内容，未接真实 HTTP；外部指令接入前需先落地该接口。
3. 外部指令执行是否需要 `request_id` 回传结果（如 `/dbg-shot` 要发图）？建议默认无回传，特殊指令显式声明。
