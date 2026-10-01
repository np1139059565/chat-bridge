# 外部工具规范（chat-bridge）

> 适用对象：以「外部工具提供方」形式接入的 skill（如 `debug_chrome`）。
> 本文规定外部工具的声明格式、执行通道与硬约束。

---

## 一、什么是外部工具

内置工具跑在 Flask 服务里（`tools_impl.py`）；外部工具不跑在服务里，
而是由**扩展自己轮询、自己执行**——服务只负责把命令入队、等结果。

判据看 `tool.json` 里工具的 `executor` 字段：`external` 即外部工具。

---

## 二、声明位置与格式

在 `skills/<name>/tool.json` 中声明：

```json
{
  "provider": "debug_chrome",
  "prompt": "本技能提供……（注入给 AI 的说明）",
  "tools": [
    {
      "name": "get_element_style",
      "description": "按选择器采集元素样式与 DOM 信息。",
      "executor": "external",
      "parameters": [
        { "name": "selector", "type": "string", "required": true, "description": "CSS 选择器" }
      ]
    }
  ]
}
```

### 2.1 顶层字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `provider` | 是 | 提供方标识，扩展轮询时用它认领命令 |
| `prompt` | 否 | 注入 System Prompt 的 skill 说明 |
| `tools` | 是 | 工具数组 |

### 2.2 工具字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 工具名，须与扩展 `TOOL_HANDLERS` 的键一致 |
| `description` | 是 | 说明，展示给 AI |
| `executor` | 是 | `external`（外部）|
| `silent` | 否 | 为 `true` 时不在抽屉生成工具卡片（如 `push_message`） |
| `wakeup` | 否 | 为 `true` 时允许在抽屉关闭时被待命轮询取走（如 `open_drawer`） |
| `command_only` | 否 | 为 `true` 时该工具**仅供外部指令执行，对 AI 透明**（见下） |
| `parameters` | 是 | 参数数组，每项含 `name` / `type` / `required` / `description` |

### 2.2.1 command_only：指令执行端工具

**背景**：外部指令（如 `/dbg-open`）需要映射到一个工具来执行（见 `external-command.md`）。
但这个工具是**指令的执行端**，供 QQ 用户在聊天对话里使用，**不应对 AI 暴露**。

**问题**：若把这类工具当普通工具声明（仅 `enabled: true`），它会：
1. 进入 `/tools` 返回的 AI 工具目录；
2. 被 `meta.all_meta()` 收集，**污染 System Prompt 的工具列表**。

这违反「指令对 AI 透明、工具才对 AI 暴露」的边界，是严重错误。

**约定**：凡「只作外部指令执行端、不供 AI 调用」的工具，必须标 `command_only: true`。
效果：
- `meta.all_meta()` 过滤它 → 不进 AI 工具目录、不进 System Prompt；
- `hub.provider_tools()` 过滤它 → 不出现在 `/tools`；
- **但仍注册进 provider hub** → 指令经 `hub.dispatch` 执行时，`find_tool` 仍能找到它（含 `wakeup` 等属性），执行不受影响。

**判据**：问自己——「这个工具会被 AI 调用吗？」
- 会（如 `get_element_style`、`exec_js`）→ 普通工具，不标。
- 不会，只作为某条指令的执行端（如 `open_drawer`）→ 必须标 `command_only: true`。

### 2.3 参数类型

沿用内置工具的类型名：`string` / `number` / `boolean` / `array`。
`required` 缺省为 `false`。参数的准确名字以 `get_tool_params` 返回为准——
AI 调用前应先查，不得臆造别名。

---

## 三、执行通道

```
AI 生成工具调用代码块
  → 工具服务解析、生成工具卡片
  → 工具服务把命令入队（按 provider）
  → 扩展轮询取走命令、在页面执行
  → 回传结果 → 工具卡片显示
```

### 3.1 关键常量

| 项 | 值 | 位置 |
|---|---|---|
| 提供方在线判定窗口 | 10 秒 | `external_tools.ONLINE_WINDOW` |
| 命令等待上限 | 10 秒 | `external_tools.FORWARD_TIMEOUT` |

- 在线判定仅用于界面指示灯，**不参与执行判断**。
- 命令路由依据「目标页面的工具（抽屉）是否打开」：扩展每次轮询上报 `is_open`，
  目标页未打开时命令立即逸散到其他页面代收。

### 3.2 回传时机

- 结果**一律回传**（含 `silent` 工具），让调用方拿到真实执行状态。
- `silent` 仅表示不在抽屉生成工具卡片。
- 是否把结果再发回网页 AI，由调用方（插件侧 `no_reply` 参数）决定。

---

## 四、扩展侧约定（debug_chrome 实例）

### 4.1 工具注册表

扩展用一张表登记工具名 → 处理函数（`05_tool-handlers.js` 的 `A.TOOL_HANDLERS`）：

```js
A.TOOL_HANDLERS = {
  get_element_style: (params) => A._toolGetElementStyle(params),
  // 新增工具：写一个处理函数并登记到表里，不必改分发逻辑
};
```

未登记的工具名返回 `UNKNOWN_TOOL`。

### 4.2 结果回传

经 service worker 代发（内容脚本直连本机地址会被 PNA 拦截，见开发指南 3.6）：

```js
A.postResult(requestId, result);  // 走 proxyFetch → service worker → 后端
```

### 4.3 必须遵守

- **内容脚本只做 DOM 操作，不直接发网络请求**，一律走 `A.proxyFetch`。
- 有超时兜底：执行可能长阻塞（如 `exec_js`），必须自行超时，否则卡死轮询循环。
- 参数名与 `tool.json` 声明严格一致，避免边角不一致（曾出过此问题，见开发指南 D6）。

---

## 五、新增一个外部工具的流程

1. 扩展侧：写处理函数，登记进 `A.TOOL_HANDLERS`。
2. 声明侧：在 `tool.json` 的 `tools` 里加一项，`executor` 填 `external`。
3. 设置页扫描 + 安装 + 上线。
4. 用 `get_tool_params` 核对参数名后调用验证。
