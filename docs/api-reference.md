# 接口参考（本地工具服务）

基地址：`http://127.0.0.1:<config.flask.port>`（默认 5000）。
所有响应带 CORS 头，且 `Cache-Control: no-store`。
工具类接口统一返回 `{ success: bool, ... }`。

---

## 一、工具

### GET /tools

返回当前**已上线**的工具列表（内置 + 自定义 + 在线的外部工具）。

- 下线工具不返回，因此不会进入 System Prompt，也无法调用。
- 自愈工具（`read_tool_source` / `hot_reload_fix`）始终在线。
- `run_command` 额外带 `languages` 字段。

```json
{ "tools": [ { "name": "read_file", "description": "...", "parameters": [...] } ] }
```

### POST /tool

执行一次工具调用。

请求：
```json
{ "tool": "read_file", "parameters": { "filePath": "E:/projects/demo/README.md" } }
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
| `tool_internal` | 工具实现代码缺陷 | 用 `read_tool_source` + `hot_reload_fix` 自愈 |
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
- 其它改动即时生效（tools_impl 每次调用现读 config.yaml）。

### POST /hot_fix

等价于 `hot_reload_fix` 工具，对工具实现文件打补丁并热重载，失败自动回滚。
请求体：`{ file_path?, old_str?, new_str?, content? }`。
`file_path` 省略时默认 `tools_impl.py`；`tool_helpers.py` 与 `tool_meta.py` 同样支持热重载。

### GET /prompt_sections

返回各技能注入 System Prompt 的说明段落。
```json
{ "success": true, "sections": [ { "skill": "debug_chrome", "text": "..." } ] }
```

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

### POST /api/cards

创建一张外部卡片并**阻塞等待**。
请求：`{ type, title, content, payload?, timeout_ms? }`（`content` 必填且为字符串）。

- 成功：`{ success: true, id, result }`
- 超时：`{ success: false, id, error: "TIMEOUT" }`

> 注意：在当前「发送即结束」模型下，卡片被投递后镜像插件会立即回填确认，故该请求通常很快返回。
> 发给网页 AI 的输入信封为 `{ type, request }`，**不携带 id**（已取消等待回复，无需配对）。
> 卡片自身的 uuid 仅用于轮询去重与回填确认（`/api/cards/<id>/reply`）。

### GET /api/cards/pending

镜像插件轮询，取走尚未投递的卡片（`{ success, cards: [...] }`），取走后标记为已投递。

### POST /api/cards/&lt;id&gt;/reply

回填结果，唤醒挂起的创建请求。请求：`{ "result": ... }`。

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

> 提供方在线判定：3 秒内有过 `poll`。离线时调用其外部工具返回 `ProviderOffline`（origin=environment）。

---

## 六、内置工具参数速查

| 工具 | 必填参数 | 可选参数 |
|---|---|---|
| `list_dir` | `target_directory` | `ignore_globs` |
| `search_file` | `target_directory`, `pattern` | `recursive`, `caseSensitive`, `ignore_globs` |
| `search_content` | `pattern` | `path`, `glob`, `contextAround`, `caseSensitive` |
| `read_file` | `filePath`（绝对路径） | `offset`, `limit` |
| `read_skill` | `skill`, `file` | `offset`, `limit` |
| `read_lints` | — | `paths`, `severity` |
| `replace_in_file` | `filePath`, `old_str` | `new_str` |
| `write_to_file` | `filePath`, `content` | — |
| `delete_file` | `target_file` | — |
| `get_tool_params` | `tool_id` | — |
| `list_rules` | — | — |
| `read_rule` | `name` | — |
| `run_command` | `language`, `command` | `cwd`, `timeout` |
| `read_tool_source` | `tool` | — |
| `hot_reload_fix` | `old_str`, `new_str` | `file_path`, `content` |

> 参数名不统一是刻意的（如 `list_dir` 用 `target_directory`、`read_file` 用 `filePath`）。调用前请先 `get_tool_params` 核对。
