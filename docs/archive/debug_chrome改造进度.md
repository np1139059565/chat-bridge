# debug_chrome 工具改造进度

> 本文件记录本轮改造的完整清单与进度，供中断后恢复。
> 每完成一项，把对应复选框改为 [x]，并在该条目下补一行「状态：已完成」+ 改动文件。

## 任务总览

1. **执行 JS 能力**：AI 可执行任意 JS，读写页面内存（window / document / localStorage 等），可对指定对象触发 click 等操作。
2. **DevTools 能力**：通过 chrome.devtools.* 获取 Console 与 Network 面板记录，供 AI 故障分析。
3. **重写截图工具**：照 `/sp` 模式精简 `get_page_snapshot`，取消 `snapshot_type`。
4. **截图结果展示与自动发送**：卡片内等比缩放显示截图、复制图片到剪贴板、像文本卡片一样自动粘贴发送（发送前确认内容就绪，不靠死等）。

## 已确认的决策

- 截图存储目录：`flask_server/data/screenshots/`（保持不变，`/sp` 已用此目录）。
- `get_page_snapshot`：整体重写，不再支持 `snapshot_type`。
- 执行 JS：允许任意代码。
- DevTools：新增 `devtools_page`，改动扩展结构，确认值得做。

## 关键事实（探查所得，避免重复探查）

- `/sp` 截图链路：内容脚本 → 后台 `chrome.tabs.captureVisibleTab`（直接 PNG）→ 回传抽屉 → `POST /api/bridge/result` → 后端 `_save_data_url` 存盘。无缩放、无二次加工。
- `/sp` 存盘实现：`flask_server/routes/bridge.py` 的 `_save_data_url`，文件名 `shot_年月日_时分秒.png`。
- 现有截图卡死嫌疑：`get_page_snapshot` 的 dom 模式返回整个 `documentElement.outerHTML`；screenshot 模式多一步 canvas 缩放。二者链路都重。
- 文本自动发送：`extend/content/03_bridge.js` 的 `pasteToWebpageAI`，写值 → input 事件 → **硬编码 setTimeout 500ms** → 派发 Enter。
- 现有复制均为 `navigator.clipboard.writeText`（纯文本），无图片复制链路。
- MAIN 世界注入通道已存在：`skills/debug_chrome/extension/content/08_injected_main.js`。

## 进度清单

### 阶段 0：准备
- [ ] 建进度文档（本文件）

### 阶段 1：重写截图工具（task 3）
- [x] 精简截图逻辑（照 /sp，去掉内容脚本侧 canvas 缩放）
      状态：已完成。后台仍用 jpeg/70（更轻），关键是移除页面内解码大图再重绘的缩放步骤。
- [x] 重写 05_tool-handlers.js 中 get_page_snapshot 分支
      状态：已完成。去掉 dom 分支与 snapshot_type，只做截图。
- [x] 更新 tool.json：get_page_snapshot 去掉 snapshot_type 参数
      状态：已完成。
- [x] 截图存盘到 flask_server/data/screenshots/（对齐 /sp 命名）
      状态：已完成。tools.py 新增 _save_screenshot_data_url。
      改动文件：content/05_tool-handlers.js、tool.json、flask_server/routes/tools.py

### 阶段 2：截图结果展示与自动发送（task 4）
> 落点修正：截图卡片属于 chat-bridge（extend/），不是 debug_chrome。
> 曾在 debug_chrome 抽屉加过复制图片按钮，已全部撤销，恢复原状。
- [x] 卡片图片结果等比缩放展示（chat-bridge 07_cards.js）
- [x] 复用「复制结果」按钮复制图片（06_execute.js + 05c_prompt.js 的 copyImage）
- [x] 自动粘贴发送图片（06_execute.js postCardResult → auto_send_image → 03_bridge.js pasteImageToWebpageAI）
- [x] 文本发送去掉死等 500ms，改为「确认输入框内容就绪即发」（waitInputReady，超时 3 秒兜底）
      状态：已完成。图片粘贴依赖站点实现，失败会回传提示。
      改动文件：extend/dialog/parts/07_cards.js、06_execute.js、05c_prompt.js、extend/content/03_bridge.js、05_index.js

### 阶段 3：执行 JS 能力（task 1）
- [x] tool.json 新增 exec_js 工具定义
- [x] MAIN 世界执行入口（08_injected_main.js 的 runCode + 消息监听）
- [x] 结果回传（safeSerialize 安全序列化 + 错误捕获 + 内容脚本 A.execJs 超时兜底）
      状态：已完成。仅支持顶层文档主世界；子页面（iframe）暂不路由。
      改动文件：tool.json、content/08_injected_main.js、content/05_tool-handlers.js

### 阶段 4：DevTools 能力（task 2）
- [x] manifest 增加 devtools_page
- [x] 新建 devtools.html / devtools.js
- [x] 采集 network 记录（devtools.js onRequestFinished → service_worker 缓存）
- [x] console 记录（页面侧 hook，见阶段 3 的 08_injected_main.js）
- [x] 与工具链路对接（新增 get_console_logs / get_network_logs 工具）
      状态：已完成。network 需该页 DevTools 打开过才有数据。
      改动文件：manifest.json、devtools.html、devtools.js、service_worker.js、tool.json、content/05_tool-handlers.js

### 阶段 5：网络请求改造（消除 Private Network Access 拦截）

**背景**：换电脑后 Chrome 版本更新，启用了 Private Network Access 限制——
公网页面（如 chat.deepseek.com）内发起的请求，禁止访问本机回环地址（127.0.0.1）。
调试扩展的 content script 运行在页面源下，直接 fetch 后端被拦截，
表现为「抽屉一直显示未连接」。

**原则**：content script 只保留 DOM 操作，所有后端请求统一交给 service worker 代发
（service worker 是扩展源，不受此限制）。抽屉 iframe 也是扩展源，无需改。

**请求点普查结果**：
- debug_chrome 内容脚本：2 处直连 fetch（心跳、结果回传）→ 需改
- debug_chrome 抽屉 iframe：1 处 fetch（发卡片）→ 扩展源，无需改
- chat-bridge content script：0 处网络请求 → 已干净，无需改
- chat-bridge 抽屉 iframe：全部请求在此（扩展源）→ 无需改

- [x] service_worker.js 新增 `proxy-fetch` 代理通道
- [x] content/01_config.js 新增 `A.proxyFetch`（含超时兜底，默认 15 秒）
- [x] content/03_heartbeat.js 心跳改走 proxyFetch
- [x] content/05_tool-handlers.js 结果回传改走 proxyFetch
- [x] 复查：内容脚本已无直连 fetch / XMLHttpRequest / sendBeacon / WebSocket
- [x] chat-bridge 侧复查：content script 无网络请求，无需改
      状态：已完成。
      改动文件：skills/debug_chrome/extension/service_worker.js、content/01_config.js、content/03_heartbeat.js、content/05_tool-handlers.js

### 阶段 6：实测与修复（task 5）

**背景**：改造完成后逐个实测新工具，发现并修复两个机制性 bug。

- [x] 连接异常排查：换电脑后 Chrome 启用 Private Network Access，
      内容脚本从公网页面直连 127.0.0.1 被拦 → 见阶段 5。
- [x] get_console_logs 返回空：拼的代码是自执行函数、没有 return，
      exec_js 拿到 undefined 被当空。改为 `return (window.__AI_DEBUG_CONSOLE_LOGS || [])`。
- [x] get_page_snapshot 超时：内容脚本用 onMessage 等结果，
      但后台用 sendResponse 回复——响应只进 sendMessage 回调，不触发 onMessage，
      监听器永远等不到。改为用 sendMessage 回调接收。
- [x] custom_tools.yaml 参数过时：后端参数校验读这个缓存文件，
      它仍是旧定义（带 snapshot_type）。修正 get_page_snapshot 条目，
      并同步 6 个工具的 skill_prompt 文案。

**实测结果**：
- 连接状态：✅ 正常
- push_message：✅
- exec_js：✅（读到 localStorage 键、标题、DOM 信息）
- get_network_logs：✅（返回真实请求记录）
- get_element_style：✅（返回 body 样式与 DOM）
- get_console_logs：✅（重载后验证，读到测试日志）
- get_page_snapshot：✅（返回 base64 图片，且存盘到 flask_server/data/screenshots/，
  文件名 shot_年月日_时分秒_毫秒.jpg）

**全部工具实测通过。**

**改动文件**：content/05_tool-handlers.js、flask_server/config/custom_tools.yaml

### 阶段 7：配置分离与截图推送 QQ（task 6）

- [x] 配置密钥分离：remote_bridge.yaml 只留 QQ 凭证（gitignore），
      非密钥配置（指令、开关）拆到 remote_bridge_settings.yaml（入库），
      bridge_store.py 自动迁移旧文件。解决「换机器丢自定义指令」。
- [x] 工具结果推送 QQ：前端上报时带上卡片结果（extractCardResults，
      截图 base64 用 slimCardResult 剥掉、只留本地路径），后端按
      「消息id#卡片id」独立去重推送——正文与结果各自去重，避免结果被
      「消息已推过」挡掉。截图发图（push_image），其余按 Markdown 文本
      （push_text markdown=True，与 AI 回复同通道）。卡片执行完以 'tool'
      来源触发一次上报（此前不触发，导致结果永不进上报数据）。
- [x] 文档：development-guide.md 新增 3.6（网络请求走后台）、3.7（配置密钥分离）。

**改动文件**：remote_bridge/bridge_store.py、remote_bridge/message_router.py、
routes/tools.py、.gitignore、docs/development-guide.md

### 阶段 8：自测与工具结果推送（task 7）

- [x] 工具结果推送 QQ：修正理解——文本结果经「回传网页 AI → 成为一条消息 →
      镜像抓取」本就能到 QQ，无需另推（原通用推送会导致重复）。真正缺的是截图：
      它经 auto_send_image 贴进输入框后，镜像只抓文本块、抓不到图片。
      故 extractCardResults 只提取「含本地图片路径」的截图结果，其余不碰。
- [x] 工具结果按 Markdown 推送：新增 _tool_result_of 识别 bridge-chat-res 消息，
      按 json 代码块发送（此前是纯文本，QQ 端不渲染）。
- [x] 卡片执行后以 'tool' 来源触发上报（此前不触发，结果不进上报数据）。
- [x] 正文与卡片结果各自去重（消息id / 消息id#卡片id），避免结果被「已推过」挡掉。
- [x] debug_chrome 抽屉展示：结果文字剥掉截图 base64，改在下方渲染图片。

**自测结果**：
- 连接状态：✅
- push_message：✅
- exec_js：✅
- get_console_logs：✅
- get_element_style：✅
- get_page_snapshot：✅（存盘正常，抽屉显示图片）

**待用户确认**：QQ 端是否收到工具结果（Markdown 格式）与截图（图片）。

**改动文件**：extend/dialog/parts/01b_bridge.js、06_execute.js、
flask_server/remote_bridge/message_router.py、
skills/debug_chrome/extension/drawer/03_ui-chat.js

### 阶段 9：切换会话时关闭自动开关（task 8）

- [x] 切换会话时，若自动开关开着，自动关掉它（同时清掉已排的倒计时），
      避免新会话里一旦出现待执行卡片就被自动执行——用户此刻只是切了会话，
      并非要执行它，属于误执行。
      改动位置：04_sessions.js 的 applyConversation（所有会话切换的收敛点）。
      仅在「从某个已就绪会话切到另一个会话」时触发，首次加载不误报提示。

**改动文件**：extend/dialog/parts/04_sessions.js

## 已知遗留（未处理，供后续决定）

- `skills/debug_chrome/extension/content/05_tool-handlers.js` 的 `A.downscaleImage`
  与 `00_namespace.js` 的 `MAX_SHOT_WIDTH`：取消缩放后已无人调用，成为未使用代码。
- exec_js 仅支持顶层文档主世界，子页面（iframe）未路由。
- get_network_logs 需该页 DevTools 打开过才有数据。
- 图片粘贴进网页 AI 输入框依赖站点实现，失败会回传提示，无自动重试。

## 风险与待办

- 图片粘贴到网页 AI 输入框无现成链路，需构造 paste 事件 + DataTransfer，属未验证项。
- DevTools 与标签页关联需确认 devtools_page 的 inspectedWindow 用法。
- 自动发送的「内容就绪确认」替代死等，需改 pasteToWebpageAI。
