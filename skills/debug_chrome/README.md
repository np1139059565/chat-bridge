# debug_chrome

网页样式调试与页面探查扩展，以「外部工具提供方」的形式挂靠 chat-bridge 工具服务。

## 组件

- **工具服务**（chat-bridge 后端）：提供卡片接口、外部工具转发、提供方通道。
- **镜像插件**（chat-bridge 扩展）：右侧抽屉渲染外部卡片与工具卡片。
- **本扩展**（debug_chrome）：页面点选、元素探查、快照、消息推送。

## 安装

1. 启动 chat-bridge 工具服务。
2. 在设置页安装并上线本 skill 的工具：`get_element_style`、`get_page_snapshot`、`get_console_logs`、`get_network_logs`、`exec_js`、`push_message`。
3. 打开 Chrome 扩展管理页，以「加载已解压的扩展」方式加载 `extension/` 目录。
4. 打开扩展抽屉，确认与工具服务连接正常。

## 使用

### 页面探查

网页 AI 调用 `get_element_style` / `get_page_snapshot`，工具卡片执行后由本扩展在页面完成采集并回传。`get_page_snapshot` 截取可见区域，图片会存到 `flask_server/data/screenshots/`。

### 故障分析

网页 AI 调用 `get_console_logs` 读取页面 console 记录；调用 `get_network_logs` 读取网络请求记录（需该页 DevTools 打开过，否则返回 `NETWORK_UNAVAILABLE`）。

### 执行脚本

网页 AI 调用 `exec_js`，在页面主世界执行任意 JavaScript，可读写 `window` / `document` / `localStorage`、触发元素点击等，支持 `await`。仅支持顶层文档，子页面会返回 `EXEC_JS_TOP_ONLY`。

### 消息推送

网页 AI 调用 `push_message`，内容会显示在本扩展抽屉中。

### 抽屉对话

在抽屉输入需求并点选页面元素，提交后由工具服务生成外部卡片，自动发送至网页 AI。外部卡片采用「发送即结束」模型：投递完成即结束。任务进展与结论由网页 AI 通过 `push_message` 主动推送到抽屉中。

## 配置

| 项 | 说明 |
|---|---|
| 工具服务地址 | 默认 `http://127.0.0.1:5000` |
| 截图开关 | 选中元素时是否附带整屏截图 |
| 样式列表开关 | 元素卡片是否附带全量计算样式 |
