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
{ "tool": "read_file", "parameters": { "path": "E:/projects/demo/README.md" } }
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
- POST：部分更新，写入配置文件（定义写 definition.yaml，运行时写 runtime.yaml）。

POST 请求体示例：
```json
{ "flask": { "port": 5001 },
  "tools": { "read_file": { "enabled": false },
             "run_command": { "languages": ["python","git"] } },
  "limits": { "max_json_chars": 200000 } }
```

响应：`{ success, saved, changed: [...], requireRestart }`。
- `flask.host/port` 改动 `requireRestart=true`（需重启进程）。
- 其它改动即时生效：POST 会同步更新 `runtime.CONFIG` 内存并写回配置文件；
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
| `list_dir` | `path` | `ignore_globs` |
| `search_file` | `path`, `glob` | `recursive`, `ignore_globs`（匹配均不区分大小写） |
| `search_content` | `pattern` | `path`, `glob`, `context_around`（上下文行数）, `case_sensitive` |
| `read_file` | `path`（字符串读单个文件，数组一次读多个；绝对路径原样，相对路径以工程根为基准） | `offset`, `limit`；不指定行范围时为整文件读取，结果只含 `data.file`（`mime`/`name`/`path`/`source`），正文由前端经 `GET /api/web/source-file` 取原始字节后作为附件粘贴；指定行范围时为分段读取，片段以 `data:text/plain` 的 dataURL 放在 `data.file.content`；回传 AI 的只有精简标记；数组单次上限 20 个文件，体积受 `limits.max_json_chars` 约束 |
| `read_image` | `path` | —（支持 png/jpg/jpeg/gif/webp/bmp，单张上限 10MB） |
| `push_file` | `path` | —（把本地文件推到用户手机 QQ 供下载；类型白名单复用 `file_types.PASTEABLE_EXTS`；体积上限见设置页 `push_file.max_bytes`，默认 50MB；推送目标取「最近发消息的 QQ 用户」，被动回复窗口过期时返回原因） |
| `list_skills` | — | — |
| `read_skill` | `skill`, `path` | `offset`, `limit` |
| `read_lints` | — | `paths`, `severity` |
| `replace_in_file` | `path`, `old_string` | `new_string` |
| `write_to_file` | `path`, `content` | — |
| `delete_file` | `path` | — |
| `get_tool_params` | `tool_id` | — |
| `list_rules` | — | — |
| `read_rule` | `rule` | — |
| `run_command` | `language`, `command` | `cwd`, `timeout`, `async`（true 时后台执行，返回 task_id） |
| `command_task` | `task_id` | — |
| `memory_search` | `query` | `limit` |
| `memory_inspect` | — | `node_ids`, `conv_id`, `limit`（默认 5，上限 20） |
| `memory_refine` | `node_id` | `essence`, `keywords`（两者至少提供一个） |

> 参数命名口径：路径统一 `path`（多路径传数组），文件名过滤统一 `glob`，内容匹配统一 `pattern`，返回条数统一 `limit`。
> `command_task` 用于查询 `run_command` 异步调用的状态与结果；`memory_*` 三个工具服务于记忆系统的检索、抽检与修正。

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

### 记忆系统补充接口

#### POST /memory/set

写入单个节点（含其卡片）。请求：`{ node: {...} }`。返回 `{ success }`。

#### POST /memory/node/delete

删除单个节点。请求：`{ node_id }`。返回 `{ success, deleted }`。

#### POST /memory/node/clean_children

清理某节点下挂的全部 AI 与工具节点（图谱右键菜单用，不可恢复）。
请求：`{ node_id }`。返回 `{ success, deleted, candidates }`。

#### POST /memory/node/clean_older

清理创建时间早于某节点的全部旧节点（图谱右键菜单用，破坏性最强）。
请求：`{ node_id }`。返回 `{ success, deleted, candidates }`。

#### POST /memory/promote

手动提升某节点分级（如临时 → 中期 → 永久）。请求：`{ node_id, tier }`。返回 `{ success, tier }`。

#### GET /memory/strength

查询某节点的记忆强度。查询参数 `node_id`。返回 `{ success, strength }`。

#### POST /memory/rule-check

对指定文本跑一遍规则检查（供质量评估）。请求：`{ text }`。返回检查结果。

#### GET /memory/notes

列出笔记条目。查询参数 `kind`（`journal` / `notebook`）、`day`（YYYY-MM-DD，可选）。返回 `{ success, notes: [...] }`。

#### GET /memory/notes/days

列出有每日记忆的日期。返回 `{ success, days: [...] }`。

#### POST /memory/note

写入一条笔记。请求：`{ kind, text, day?, node_id?, keywords? }`。返回 `{ success, note_id }`。

#### POST /memory/note/delete

删除一条笔记。请求：`{ note_id }`。返回 `{ success, deleted }`。

#### POST /memory/solidify/rule

把某节点固化为规则文件。请求：`{ node_id }`。返回 `{ success }`。

#### POST /memory/solidify/notebook

把某节点写入错题本。请求：`{ node_id }`。返回 `{ success }`。

#### GET /memory/event/tree

取事件树结构（事件根 + 其成员）。查询参数 `root_id`（可选）。返回 `{ success, tree }`。

#### POST /memory/event/merge

合并两个事件簇。请求：`{ from_root, to_root }`。返回 `{ success }`。

---

## 八、桥接层（/api/bridge）

QQ ↔ 网页 AI 的双向桥接接口。抽屉插件与后端交互，把网页对话切片推给 QQ，
并把 QQ 侧的指令回传到抽屉执行。

桥接层运行时数据文件（均落在 `data/` 下，不入库）：

| 文件 | 内容 |
|---|---|
| `data/remote_bridge_state.json` | 已推送消息 id 的去重记账，防止重启后复推刷屏 |
| `data/remote_bridge_windows.json` | 被动回复窗口（`msg_id` / 序号 / 过期时间）；重启后未过期窗口可直接续用，序号一起恢复以免撞号被 QQ 丢弃 |

### GET /api/bridge/status

返回桥接运行状态（供设置页指示灯与窗口信息展示）。返回 `{ success, connected, ... }`。

### GET /api/bridge/config

读取桥接配置。

### POST /api/bridge/config

部分更新桥接配置并重启桥接（凭证 / 开关变化需重建长连接）。
请求为待更新字段的字典；返回 `{ success }`。

### GET /api/bridge/voices

列出某引擎可选音色，供设置页音色下拉使用。
查询参数 `engine`（可选，缺省取当前配置实际生效的引擎；auto 取 fallback 首个）。
四类引擎音色来源不同：pyttsx3 读 Windows 系统语音（子进程列举，避免占用 SAPI）、
sapi 读 Windows 自带 System.Speech 语音清单（同样子进程列举）、
piper 读本地模型文件、edge_tts 取内置音色清单。
返回 `{ success, engine, voices: [{id, name}], current }`。

### POST /api/bridge/report

抽屉上报消息切片，触发向 QQ 推送。
请求：`{ conversationId, messages: [{id, role, blocks}], openid }`。
`messages` 是全量可见切片，桥接层自行与已推送集合比对取差集。

### POST /api/bridge/result

抽屉回传指令执行结果，转发到 QQ。请求：`{ request_id, result }`。返回 `{ success }`。

### GET /api/bridge/help

返回桥接指令帮助文本。返回 `{ success, text }`。

### GET /api/bridge/command_params

查询某桥接指令的参数说明。查询参数 `name`。返回 `{ success, params }`。

### POST /api/bridge/run-command

由抽屉直接执行一条指令（供设置页的指令按钮调用）。与 QQ 里敲指令走完全相同的处理链路，区别只在于回执落网页收件箱、不发 QQ。

请求：`{ text: "/sd" }`。返回 `{ success, handled }`。

### GET /tools/all

返回全部内置工具及其开关状态，供设置页管理。与 `/tools` 的关键区别是**不过滤已下线工具**——`/tools` 是给 AI 看的目录，设置页若复用它，工具一旦下线就从界面消失、无法重新上线。返回 `{ tools: [{name, description, parameters, enabled}] }`。

### GET /api/bridge/commands

列出可用桥接指令。返回 `{ success, commands: [...] }`。

### POST /api/bridge/commands

登记或更新桥接指令面板。请求为指令清单；返回 `{ success }`。

### DELETE /api/bridge/commands

移除桥接指令面板。返回 `{ success }`。

### POST /api/bridge/restart

重启桥接。返回 `{ success }`。

### 微信通道（/api/bridge/weixin）

微信 ClawBot（iLink）通道的配置与扫码登录接口。与 QQ 通道并列独立：
微信没有 AppID / AppSecret，凭证由扫码登录获得，保存在本机数据目录，不入库。

#### GET /api/bridge/weixin/status

查询微信通道状态与登录进度。
返回 `{ success, channel: {enabled, connected, hasCred, botId, lastEvent}, login: {state, qrcode_url, message, need_verify} | null, quota: {used, limit, remaining} }`。
`login.state` 取值：`idle` / `waiting` / `scanned` / `need_verify` / `confirmed` / `failed`。
`quota` 为当前用户的发送配额余量：微信限制 24 小时内最多 10 条消息。

#### POST /api/bridge/weixin/config

保存微信通道开关。请求：`{ enabled: true|false }`。保存后自动重启桥接。
返回 `{ success, weixin, ...status }`。

#### POST /api/bridge/weixin/login

发起扫码登录，立即返回二维码内容（不等用户扫完）。
返回 `{ success, login, ...status }`；`login.qrcode_url` 是二维码内容，前端渲染成图即可。

#### POST /api/bridge/weixin/verify

提交手机微信上显示的验证码。请求：`{ code: "123" }`。
仅在 `login.state` 为 `need_verify` 时有效。返回 `{ success, ...status }`。

#### POST /api/bridge/weixin/logout

退出登录：清除本机凭证并停止长轮询。返回 `{ success, ...status }`。

### 企业微信通道（/api/bridge/wecom）

企业微信智能机器人通道，与 QQ、微信并列的第三条通道。
走 WebSocket 长连接（`wss://openws.work.weixin.qq.com`），凭证为手工填写的
BotID / Secret，支持主动推送、图片、文件与群聊。

#### GET /api/bridge/wecom/status

查询企业微信通道状态。
返回 `{ success, channel: {enabled, connected, hasCred, botId, lastEvent}, botId, hasSecret, chatid, chatType }`。
`hasSecret` 只表示是否已保存密钥，不回传明文。
`chatid` 为当前活跃会话，主动推送依赖它。

#### POST /api/bridge/wecom/config

保存通道开关与凭证。请求：`{ enabled?, bot_id?, secret? }`。
`secret` 留空表示不修改已有值——避免只想改开关时把密钥清空。
保存后自动重启桥接以重建长连接。返回 `{ success, wecom, ...status }`。

---

## 九、网页版机器人（/api/web 与 /web-bot）

网页版对话机器人：把 QQ 侧消息投递到网页收件箱，并支持从网页发图、发语音、回传消息。

### GET /web-bot

网页版机器人页面。

### GET /web-bot/<name>

按名字取网页版机器人会话页面。返回对应 HTML。

### GET /api/web/commands

列出网页版可用指令。返回 `{ success, commands: [...] }`。

### GET /api/web/messages

拉取网页收件箱消息。返回 `{ success, messages: [...] }`。

### POST /api/web/send

从网页发送一条消息（转投到 QQ）。请求：`{ text }`。返回 `{ success }`。

### POST /api/web/image

从网页发送一张图片。请求含图片数据（base64）；返回 `{ success, name }`。

### POST /api/web/file

从网页发送一个文件。请求：`{ name, data（base64）, text }`。

校验顺序与 `push_file` 一致：文件名净化（去目录部分）→ 要求扩展名在 `file_types.PASTEABLE_EXTS` 内 → 体积上限与 QQ 来件同口径 → 落盘到 `data/qq_files/` → 投 `web-file` 卡片。

成功返回 `{ success, cardId, name, path, size }`；类型不支持返回 400 + `error: unsupported_type` 与可读的 `message`，网页据此直接提示用户，**不会**把读不了的文件投给 AI。

### GET /api/web/source-file

按路径返回工程内源文件的原始字节，供前端直接构造 File 粘贴进网页 AI 输入框。查询参数：`path`（工程内路径，绝对或相对）。

不复制、不编码，直接以二进制流返回。仅限工程根内文件，拒绝点文件；路径越界、点文件、不存在均返回 404。

### GET /api/web/image-file/<name>

读取已保存的网页图片。返回图片二进制（带长缓存）。

### GET /api/web/screenshot-file/<name>

读取已保存的工具截图（debug_chrome 的 get_page_snapshot 结果）。返回图片二进制（带长缓存）。

### POST /api/web/voice

从网页发送语音。请求含音频数据；返回 `{ success, name }`。

### GET /api/web/audio/<name>

读取已合成的语音文件。返回音频二进制（带长缓存）。

### GET /api/web/file-download/<name>

下载网页会话中被推送的文件（`push_file` 在网页版下的产物），以附件形式返回，手机浏览器点开即下载。

只接受纯文件名，越界或不存在均返回 404。文件名唯一（原名 + 时间戳），内容不变，带长缓存。

### POST /api/web/voice-ensure

按需合成语音（已存在则复用）。请求：`{ text }`。返回 `{ success, name }`。

### GET /api/web/voice-status

查询语音合成状态。查询参数 `name`。返回 `{ success, status }`。

### POST /api/web/client_log

接收网页端上报的客户端日志，落到服务端日志。请求：`{ level, text }`。返回 `{ success }`。

---

## 十、路由补充接口

### GET/POST /config/restart-port

改端口并重启服务（重启后新端口生效）。

### PUT/DELETE /custom_tools/<name>

按名字更新或删除自定义工具。

### GET /tool/command_task

查询 `run_command` 异步调用的状态与结果。查询参数 `task_id`。
返回 `{ success, task_id, status, result?, error? }`。

### GET/PUT/DELETE /rules/<name>

按名字读取、更新或删除某条规则。
