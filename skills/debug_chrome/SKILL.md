# debug_chrome

网页样式调试与页面探查扩展，以「外部工具提供方」的形式提供服务。

## 能力

扩展上线后向工具服务轮询命令，为网页 AI 提供以下工具：

| 工具 | 作用 |
|---|---|
| `get_element_style` | 按选择器采集元素样式与 DOM 信息 |
| `get_page_snapshot` | 截取目标页面当前可见区域，返回图片并保存到本地 |
| `get_console_logs` | 读取页面捕获的 console 记录（log/info/warn/error/debug），供故障分析 |
| `get_network_logs` | 读取 DevTools 采集的网络请求记录，供故障分析；**需该页 DevTools 打开过** |
| `exec_js` | 在页面主世界执行任意 JavaScript，可读写 window / document / localStorage、触发点击等，支持 await；**仅支持顶层文档** |
| `push_message` | 向扩展抽屉推送一条文字信息（用于主动联系用户）；必填参数 `message`（推送正文）、`no_reply`（为 true 时不回传执行结果，仅执行推送，用于最后一次总结性推送，避免结果回传再次唤醒 AI）；可选 `title` |

## 交互方式

- **被调用**：网页 AI 生成工具调用代码块 → 工具服务生成工具卡片 → 卡片执行请求工具服务 → 工具服务把命令入队并挂起 → 扩展轮询取走命令、在页面执行、回传结果 → 工具卡片显示结果。
- **主动对话**：在扩展抽屉输入需求并附加已选元素，组装为外部卡片提交工具服务，工具服务渲染卡片并自动发送至网页 AI。

## 外部卡片

外部卡片投递给网页 AI 后即结束，不等待回传。任务进展、结论与方案，由网页 AI 通过 `push_message` 工具主动推送给用户。

## 输入信封

外部卡片以信封结构发往网页 AI： 

```
{
  "type": "external-call",
  "request": ...
}
```

## 处理要求

1. 收到 `type=external-call` 的消息，属于外部调试卡片任务。若本次会话尚未阅读过本技能说明，请先用 `read_skill` 工具读取（参数 `skill=debug_chrome`、`file=SKILL.md`），再按其规定处理；同一会话内只需读取一次。
2. 按 `request` 完成页面调试任务，可调用本技能提供的页面探查工具。按目的选用：
   - 看元素样式与 DOM：`get_element_style`
   - 看页面当前样子：`get_page_snapshot`（截图并保存到本地）
   - 排查报错：`get_console_logs`（页面 console 记录）
   - 排查请求问题：`get_network_logs`（需该页 DevTools 打开过，否则返回 `NETWORK_UNAVAILABLE`）
   - 需要更灵活的操作（读页面内存、点按钮、调用页面函数）：`exec_js`。**该工具能执行任意代码，威力大也危险**，只写必要的最小代码，避免改动页面状态；且仅支持顶层文档，子页面（iframe）会返回 `EXEC_JS_TOP_ONLY`。
3. 调用 `get_element_style` / `get_page_snapshot` / `get_console_logs` / `get_network_logs` / `exec_js` 时必须传入 `page_url`，指向目标元素或页面所在文档的地址（元素选择器对应的页面 URL 见卡片中的「URL：」行）。调试扩展据此把命令路由到正确的文档；若返回 `FRAME_NOT_FOUND`，按返回的 `available` 列表核对 URL 后重试一次。
4. **遇到「需要用户插手」的错误：立即停下，用 `push_message` 邀请用户帮忙。**
   以下错误靠 AI 自己重试或改参数都无法解决，**不要反复重试**，应停下并推送明确的操作指引，等用户处理后回复：
   - `FRAME_TIMEOUT` / `FRAME_QUERY_FAILED`（含 hint「需已安装 iframe 点选补丁」）：目标文档内**尚未安装点选补丁**，或其未在运行。
     → 推送：「请在该文档的控制台执行『iframe 点选补丁』（调试抽屉→设置→补丁，可复制代码），完成后回复我继续。」
   - `ForwardTimeout`：请求已排队但调试扩展未在时限内取走（扩展未打开，或所在页面未加载扩展）。
     → 推送：「请确认调试扩展已打开并停留在目标页面，然后回复我继续。」
   - `ELEMENT_NOT_FOUND` 且返回中带 `page_url`（说明已正确路由进目标文档，但元素此刻不存在）：多为选择器依赖的元素此时不可见（如设置页已关闭），或 `:nth-child` 位置选择器因 DOM 变动而失配。
     → 推送：「目标元素当前不可见或选择器已失效。请让该元素保持显示，或提供更稳定的选择器，然后回复我继续。」
   - `ELEMENT_NOT_UNIQUE`：选择器命中多个元素。
     → 推送命中数量，并请用户提供更精确的选择器或指明第几个。
5. **用 `push_message` 主动联系用户**：在每个关键节点推送一条简明信息，让用户随时掌握进度。典型节点包括：
   - 开始处理：说明你的理解与计划。
   - 取得关键信息：报告探查结果（选择器、样式、快照要点）。
   - 形成方案：给出建议的修改方案与影响范围，必要时请用户确认。
   - 遇到阻塞：说明缺少什么信息或需要用户配合什么。
   - 完成任务：报告最终结论与已执行的改动。
6. 需要读写本地文件、搜索代码时，使用镜像插件提供的本地工具（如 `read_file` / `replace_in_file` / `search_content`），不要臆造工具名。
   - 读取文件用绝对路径；读取 skill 文档请用 `read_skill`（`skill` + `file` 相对路径），不要拼 `skills/...` 相对路径给 `read_file`。
