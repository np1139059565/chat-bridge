# debug_chrome 工具改造进度

> 本文件记录本轮改造的完整清单与进度，供中断后恢复。
> 每完成一项，把对应复选框改为 [x]，并在该条目下补一行「状态：已完成」+ 改动文件。

## 任务总览

1. **执行 JS 能力**：AI 可执行任意 JS，读写页面内存（window / document / localStorage 等），可对指定对象触发 click 等操作。
2. **DevTools 能力**：通过 chrome.devtools.* 获取 Console 与 Network 面板记录，供 AI 故障分析。
3. **重写截图工具**：照 `/sp` 模式精简 `get_page_snapshot`，取消 `snapshot_type`。
4. **截图结果展示与自动发送**：卡片内等比缩放显示截图、复制图片到剪贴板、像文本卡片一样自动粘贴发送（发送前确认内容就绪，不靠死等）。

## 已确认的决策

- 截图存储目录：`flask_server/screenshots/`（保持不变，`/sp` 已用此目录）。
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
- [x] 截图存盘到 flask_server/screenshots/（对齐 /sp 命名）
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
- get_page_snapshot：✅（返回 base64 图片，且存盘到 flask_server/screenshots/，
  文件名 shot_年月日_时分秒_毫秒.jpg）

**全部工具实测通过。**

**改动文件**：content/05_tool-handlers.js、flask_server/custom_tools.yaml

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
