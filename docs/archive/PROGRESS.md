# 网页 AI 输入适配器·进度纪要

## 任务背景

在 qianwen 页面（https://www.qianwen.com/chat/be908b9836694d32b49e8f3f95dc4d48）调试一个把外部消息投递进网页 AI 输入框的适配器。工具侧已验证的能力：exec_js 在页面主世界执行 JS。

## 已验证事实

1. 目标页面 URL：https://www.qianwen.com/chat/be908b9836694d32b49e8f3f95dc4d48
2 . exec_js 可用：tool=exec_js，parameters 含 page_url + code，返回 success/res。
3. 工具目录已获取（28 个工具），关键项：
   - get_tool_params：调用任何工具前查参数（tool_id=工具名）
   - read_file / write_to_file：读写本地文件（path/content）
   - search_file / search_content：按名/按内容找文件
   - get_page_snapshot：页面截图
   - get_console_logs：读页面 console
   - push_message：向调试扩展抽屉推送进度
4. 三条[总是]规则已读：ANTI-FLATTERY（诚实不奉承）、user-rule（全中文、改写-再回答、代码注释/模块化、方案编号+利弊、及时提交）、Negative-constraint-leakage（交付物只写最终规格，不写否决历史/对话上下文；用户明确要求的纪要例外）。

## 注入机制验证（v2 会话新增）

5. exec_js 返回值机制：代码被 `new Function(code)` 包裹成函数体，**必须显式 `return`** 才有返回值，末尾裸表达式不返回（两次踩坑确认）；报错 stack 来自扩展 content/08_injected_main.js。
6. 编辑器定位（DOM 探测）：
   - 唯一可见输入元素：`div[contenteditable="true"][role="textbox"]`，rect≈x655/y582/w774/h33，placeholder「向千问提问」（textContent 含 BOM `\ufeff`）。
   - 另一个同 class 的 contenteditable div 与一个 `span`（contenteditable=false，placeholder 文本）是预览/占位节点，选择器务必带 role=textbox 区分。
7. 发送按钮：`button[aria-label="发送消息"]`（x≈1397）。空文本时 disabled=true，有文本时解禁——可作注入成功的判据。
8. 注入路径（实测成功）：`ed.focus()` → 构造 `DataTransfer` 并 `setData('text/plain', text)` → 派发 `ClipboardEvent('paste')` → 约 300ms 后 React 状态同步、按钮解禁。
   **对 contenteditable，正确注入路径是 paste 事件。**
9. 清理局限（实测）：`execCommand('selectAll'+'delete')` 只清 DOM 文本（textLen→0），React state 不回退（按钮保持解禁）；paste 空文本 / 零宽占位再删同样无法重置 state。残留无害（空文本点击发送无实际效果）。结论：清理做到 DOM 层即可，state 残留可接受，勿继续扰动页面。
10. 对既有教训的修正：原记录「execCommand 失效，改用原生 value setter + dispatchEvent」仅适用于 `textarea`/`input`（可劫持 value setter）；contenteditable div 无 value，此路不通，须用 paste 事件（见第 8 条）。

## 生成态与全链路（v2 实测收口）

11. 生成态标志：发送按钮 aria-label 在两态间切换——**「发送消息」=空闲，「停止回答」=生成中**。切换稳定，可作轮询判据。
12. 全链路实测通过（2026-11-08）：paste 注入 → 按钮解禁（disabled=false）→ click 发送 → 1.8s 后按钮切「停止回答」→ 消息文本进入会话渲染层（body.innerText 命中）。注入→确认总耗时 <2.5s。

## 适配器交付

- 文件：`skills/debug_chrome/adapters/qianwen-adapter.js`（挂 `window.__qianwenAdapter`，安装幂等）；扩展副本 `skills/debug_chrome/extension/adapters/qianwen-adapter.js` 同笔部署（扩展沙箱仅能加载自身目录内文件，双副本为有意为之）
- 安装：exec_js 执行该文件全部内容一次；
- 发送：`return await window.__qianwenAdapter.send('文本')`，返回 `{sent, generating}`；
- 状态：`return window.__qianwenAdapter.state()` → `idle | generating`；
- 约束：exec_js 总超时 15s，send 内部等待上限据此收紧（空闲等待默认 8s）；`waitDone` 默认关闭，长生成用两次调用（send 后轮询 state）。
- 扩展侧事实：扩展（skills/debug_chrome/extension）内无任何 qianwen 专属代码；工具经 TOOL_HANDLERS 表分发，新增工具只需注册处理函数；本批已照此新增 09_qianwen-tool.js（注册工具名 send_to_qianwen），扩展 manifest 升至 v1.2.0。

## 待办路线

1. ✅ 定位适配器代码 → 结论：扩展内无现成代码，适配器从零新写。
2. ✅ 注入方式 → paste 事件方案已实现并实测（见第 8、12 条）。
3. ✅ 生成态抓取 → 「停止回答 / 发送消息」双态标志（见第 11 条）。
4. ✅ 全链路实测通过（见第 12 条）。
5. ✅ 已注册为扩展工具（2026-11-08 同笔交付）：09_qianwen-tool.js 进 TOOL_HANDLERS（工具名 send_to_qianwen），扩展 manifest 升至 v1.2.0，适配器双副本随扩展部署——免 exec_js 直接调用。

## 教训记录

- 工具名按猜（list/list_tools/tools）全部 UnknownTool；正确路径是等系统注入工具目录（本条已解决）。
- 卡片书写稳定性：会话早期出现过整轮书写崩溃（乱码、字段幻觉、无限自我作废）。恢复纪律：一页一卡、贴前逐字段自检、失败秒回不恋战。
- execCommand('insertText') 在受控组件页面已知失效。**修正（v2 实测）**：value setter 方案仅适用 textarea/input；contenteditable 用 paste 事件（ClipboardEvent + DataTransfer）；execCommand delete 亦只改 DOM 不同步 React state（详见第 8-10 条）。
- ForwardTimeout（外部工具未在时限内被执行）＝扩展侧瞬态离线，请求已入队未取走；原样重试即恢复，无需改载荷。
- 本地目录搜索 0 命中时先怀疑路径层级猜错（本例实际路径多一层 skills/debug_chrome/），用 search_file 精确文件名先校准路径，再搜内容。

## 链路验证与工具修复（2026-11-08 晚）

- 端到端实机通过：drawer 内 exec_js 卡片完成，适配器 send 成功（sent 全文返回、sendErr null），千问 AI 正常回复。
- 超时（取走前）根因：命令轮询由宿主页面内容脚本承担（content/03_heartbeat.js，抽屉所在页面轮询取命令），宿主标签页后台化遭 Chrome 定时器节流即停摆——非代码缺陷；已登记 pending-tasks。
- send_to_qianwen「未知工具」：前轮判定有误，特此更正——「未知工具」文案不在扩展代码内（来自服务侧目录校验），09 按设计作为内容脚本注册（分发在 05_tool-handlers.js），manifest 移除尝试被 JSON 校验正确拦下；真因为服务侧工具目录未声明，已在 skills/debug_chrome/tool.json 补 send_to_qianwen / qianwen_state（executor: external）。注册表生效（同晚）：install 以 names 过滤仅装入新增两条并启用（13→15 条），绕开裸 install 重装重置既有开关的副作用（已登记 pending-tasks）；load_tools 每次读盘，服务侧无需重启。 端到端实测（同晚）：send_to_qianwen 首呼成功（HTTP 200，sent 回读一致，随后 qianwen_state=idle），qianwen 原生工具链路全通，exec_js 手动注入路径对该页退役。
- editorLeftover 返回「间干间搜间」为反爬混淆 placeholder 误报，已登记待修。
- 运行侧动作（需用户配合）：chrome://extensions 重载 debug_chrome 扩展，确保运行 v1.2.0（旧实例无 09 注册，服务目录放行后仍会报未知）；轮询修复落地前保持宿主页面前台。

> 2026-11-11 清理：`send_to_qianwen` / `qianwen_state` 及扩展适配器、内容脚本、manifest 注册已移除（用户判定无意义）。
