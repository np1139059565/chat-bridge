# 接口参考（本地工具服务）

基地址：`http://127.0.0.1:<config.flask.port>`（默认 5000）。
所有响应带 CORS 头，且 `Cache-Control: no-store`。
工具类接口统一返回 `{ success: bool, ... }`。

---

## 一、工具

### GET /tools

返回当前**已上线**的工具列表（内置 + 自定义 + 外部工具）。

- 下线工具不返回，因此不会进入 System Prompt，也无法调用。
- 外部工具只要已注册就出现在目录中；其提供方是否轮询不影响可见性。
- `run_command` 额外带 `languages` 字段。

```json
{ "tools": [ { "name": "read_file", "description": "...", "parameters": [...] } ] }
```

### POST /tool

执行一次工具调用。

请求：
```json
{ "tool": "read_file", "parameters": { "file_path": "E:/projects/demo/README.md" } }
```

成功：
```json
{ "success": true, "tool": "read_file", "result": { ... } }
```

失败（HTTP 200，错误在 body）：
```json
{
  "success": false,
  "tool": "read_file",
  "error": "ToolParamError: ...",
  "errorType": "ToolParamError",
  "origin": "parameter",
  "originLabel": "parameter（参数问题）",
  "location": { "file": "...", "line": 123, "function": "t_read_file", "source": "..." },
  "traceback": "...",
  "hint": "这是调用参数问题..."
}
```

`origin` 取值：

| origin | 含义 | AI 应对 |
|---|---|---|
| `parameter` | 参数缺失/类型错/取值非法 | 改参数重试，**不要**改代码 |
| `environment` | 路径/权限/文件不存在 | 确认路径权限后重试 |
| `tool_internal` | 工具实现代码缺陷 | 改参数无效，需检查工具实现 |
| `unknown_tool` | 工具名不存在 | 从工具目录选正确名称 |
| `disabled` | 工具已下线 | 改用其它工具或上线该工具 |

### GET/POST /config

- GET：读取配置（flask / limits / default_profile / site_profiles / tools / available_tools）。
- POST：部分更新，写入 `config.yaml`。

POST 请求体示例：
```json
{ "flask": { "port": 5001 },
  "tools": { "read_file": { "enabled": false },
             "run_command": { "languages": ["python","git"] } },
  "limits": { "max_json_chars": 200000 } }
```

响应：`{ success, saved, changed: [...], requireRestart }`。
- `flask.host/port` 改动 `requireRestart=true`（需重启进程）。
- 其它改动即时生效：POST 会同步更新 `runtime.CONFIG` 内存并写回 `config.yaml`；
  `run_command` 的语言列表每次调用现读配置文件。

### GET /prompt_sections

返回各技能注入 System Prompt 的说明段落、本机技能清单与设置页管理视图。
- `sections`：已上线技能的统一说明，来自技能 `tool.json` 顶层的 `prompt` 字段。
- `skills`：已上线技能清单（仅含带说明文档、且至少有一个已上线工具的技能）。
- `skillsManage`：设置页「技能」区块的管理视图，覆盖全部技能（含已下线），不参与 System Prompt 注入。
```json
{
  "success": true,
  "sections": [ { "skill": "debug_chrome", "text": "..." } ],
  "skills": [ { "name": "debug_chrome", "summary": "...", "tools": ["get_element_style"] } ],
  "skillsManage": [ { "name": "debug_chrome", "summary": "...", "tools": [ ... ],
                       "tool_count": 6, "enabled_count": 2, "doc_file": "SKILL.md" } ]
}
```

### PUT /skills/&lt;skill&gt;/enabled

技能一键上 / 下线：批量设置该技能下全部工具的 `enabled`，并刷新提供方注册表。
请求：`{ "enabled": true }`。返回：`{ ok, skill, enabled, changed }`（`changed` 为受影响工具名列表）。

### GET/PUT /skills/&lt;skill&gt;/doc

技能说明文档（默认 `SKILL.md`）的读取与写回。
- GET `?file=SKILL.md`：读取文档文本，返回 `{ ok, ... }`。
- PUT `{ file, text }`：写回文档文本。

### GET /

简易 HTML 索引页，列出内置工具。

---

## 二、自定义工具（标准 skill）

### GET /custom_tools

返回全部自定义工具（含未上线）与默认扫描根目录。
```json
{ "tools": [ { "name", "description", "skill_name", "skill_dir", "script",
               "interpreter", "arg_style", "enabled", "parameters", "fixed_args" } ],
  "scanRoots": [ "..." ] }
```

### POST /custom_tools/scan

扫描某目录下的可安装 skill。请求：`{ "dir": "<父目录>" }`。
返回 `{ ok, skills: [ { skill_dir, skill_name, tools: [...] } ] }`。

### POST /custom_tools/install

安装 skill 中的工具。请求：`{ "dir": "<skill目录>", "names": ["工具名"] }`（names 省略=全部）。
返回 `{ ok, installed: ["工具名"] }`。

### PUT/DELETE /custom_tools/&lt;name&gt;

- PUT：更新 description / interpreter / arg_style / enabled / parameters / fixed_args。
- DELETE：删除该自定义工具。

---

## 三、规则

### GET /rules

```json
{ "rules": [ { "name", "summary", "priority" } ],
  "rulesDir": "...", "priorities": ["always","on-demand","off"],
  "priorityLabels": { "always": "总是", ... } }
```

### POST /rules

新建规则。请求：`{ "name": "my-rule", "content": "# ...", "priority": "on-demand" }`。

### GET/PUT/DELETE /rules/&lt;name&gt;

- GET：`{ ok, name, content, priority }`。
- PUT：`{ content?, priority? }`（只改优先级可只传 priority）。
- DELETE：删除规则。

---

## 四、外部卡片（/api/cards）

外部卡片采用「发送即结束」：登记即返回，不阻塞、不等待回填，因此不存在超时失败。
任务进展由网页 AI 通过 `push_message` 主动推送给发起方。

### POST /api/cards

创建一张外部卡片并**立即返回**。
请求：`{ type, title, content, payload? }`（`content` 必填且为字符串）。

- 成功：`{ success: true, id, status }`
- 失败：`{ success: false, error: "INVALID_CARD" }`（content 缺失或非字符串）

> 发给网页 AI 的输入信封为 `{ type, request }`，不携带 id。
> 卡片自身的 uuid 仅用于轮询去重。

### GET /api/cards/pending

镜像插件轮询，取走尚未确认「已展示」的卡片（`{ success, cards: [...] }`）。
在收到确认前，任何客户端都可反复取走同一张卡片；接收方按 id 去重。

### POST /api/cards/&lt;id&gt;/delivered

确认卡片已由某客户端生成并展示，此后不再投递。重复调用幂等。

### GET /api/cards/&lt;id&gt;

查询单张卡片状态。

---

## 五、外部工具提供方通道（/api/ext）

### POST /api/ext/&lt;provider&gt;

提供方（如调试扩展）与工具服务的唯一通道。

| action | 请求字段 | 作用 |
|---|---|---|
| `poll` | `tab_id?`, `page_url?` | 心跳 + 取走待执行命令，返回 `{ success, commands }` |
| `result` | `request_id`, `result` | 回传某次工具调用结果，唤醒挂起的 `POST /tool` |

命令结构：`{ request_id, tool, params, silent }`。

> `silent=true` 仅表示提供方不在界面生成工具卡片；无论 silent 与否，提供方都需回传真实执行结果。

> 在线判定（10 秒内有过 `poll`）仅用于界面「已连接」指示灯，不参与执行判断。
> 外部工具调用一律入队等待提供方取走执行；等待上限内未取走才返回 `ForwardTimeout`（origin=environment）。

---

## 六、内置工具参数速查

| 工具 | 必填参数 | 可选参数 |
|---|---|---|
| `list_dir` | `dir_path` | `ignore_globs` |
| `search_file` | `dir_path`, `pattern` | `recursive`, `ignore_globs`（匹配均不区分大小写） |
| `search_content` | `pattern` | `dir_path`, `glob`, `context_around`（上下文行数）, `case_sensitive` |
| `read_file` | `file_path`（绝对路径原样，相对路径以工程根为基准） | `offset`, `limit` |
| `list_skills` | — | — |
| `read_skill` | `skill`, `file` | `offset`, `limit` |
| `read_lints` | — | `paths`, `severity` |
| `replace_in_file` | `file_path`, `old_string` | `new_string` |
| `write_to_file` | `file_path`, `content` | — |
| `delete_file` | `file_path` | — |
| `get_tool_params` | `tool_id` | — |
| `list_rules` | — | — |
| `read_rule` | `name` | — |
| `run_command` | `language`, `command` | `cwd`, `timeout` |

> 参数命名口径：文件路径统一 `file_path`，目录路径统一 `dir_path`。调用前请先 `get_tool_params` 核对。

---

## 七、记忆系统

结构化记忆系统的 HTTP 接口。数据落 `flask_server/data/memory/memory.db`（单文件 SQLite）。
所有响应统一 `{ success: bool, ... }`。详见 `docs/记忆机制改进方案.md`。

### 会话（前端走后端查询）

#### GET /memory/conversation

取整个会话的消息树。查询参数 `conv_id`（必填）、`site_key`。
返回 `{ success, conv }`；会话不存在时 `conv` 为 null。

#### POST /memory/conversation

写整个会话的消息树，写入后触发异步蒸馏。
请求：`{ conv_id, site_key, conv: { title, page_url, msgTree, visibleKeys, ... } }`。
返回 `{ success, written }`（写入节点数）。

#### GET /memory/conversations

列出会话摘要。查询参数 `site_key`（可选）。返回 `{ success, conversations: [...] }`。

#### POST /memory/conversation/delete

删除一个会话及其全部节点、边、卡片。请求：`{ conv_id, site_key }`。返回 `{ success, deleted }`。

### 节点

- `GET /memory/node/<node_id>` — 取节点（含其卡片）。
- `GET /memory/list?conv_id=&site_key=` — 列举某会话全部节点。
- `POST /memory/delete` — 软删除节点，请求 `{ node_id }`。

### 检索（双接口防幻觉）

#### POST /memory/plan

接口 A：暂存任务计划原文，作为检索真值基准。请求 `{ plan_text, session_id }`。返回 `{ success, plan_id }`。

#### POST /memory/search

接口 B：验证式关联搜索。请求 `{ plan_id, keywords: [...], focus, top_k }`。
`focus` 取 `relevance`（默认）/ `time` / `strength`。
返回 `{ success, hits: [...], rejected: [...], plan_found }`。
`keywords` 中不在计划原文里的词会进 `rejected`，不参与检索。

### 分级 / 事件 / 图谱

- `POST /memory/decay/run` — 触发衰减计算与自动升降级，返回 `{ processed, upgraded, downgraded }`。
- `GET /memory/events` — 列出事件簇（用户发言按关键词聚类）。
- `GET /memory/event/history?root_id=` — 取某事件根节点的演化史（修订日志）。
- `GET /memory/graph?conv_id=&site_key=` — 导出图数据（节点 + 边），供可视化。
- `POST /memory/load` — 触发一次内存加载（规则 + 记忆摘要）。
- `GET /memory/fingerprint` — memory 目录内容指纹（判断 AI 是否写入工作记忆）。

### 图谱页面

#### GET /memory-graph

记忆图谱可视化页面（原生 Canvas 力导向图，零外部依赖）。
节点按分级着色（临时=灰 / 中期=蓝 / 永久=金 / 用户=红），大小反映强度；
边分树边（灰实线）、分支边（灰虚线）、突触边（金虚线）。支持悬停看精华、拖拽节点。
