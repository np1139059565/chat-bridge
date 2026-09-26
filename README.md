# AI 工具调用镜像插件（chat-bridge）

Chrome 扩展 + 本地 Flask 工具服务：在网页 AI 对话框与本地工具执行之间架起桥梁。
扩展在网页 AI 对话页与悬浮对话框之间形成**双向镜像**，自动从对话中提取 `bridge-chat-call` 代码块，
调用本地 Flask 服务执行（文件读写、搜索、JSON 校验等），并把结果回灌进对话。

## 特性

- **双向镜像**：网页对话 ↔ 扩展悬浮对话框实时同步。
- **工具调用**：从对话中提取 `bridge-chat-call` 代码块，交给本地工具服务执行，结果写回对话。
- **可上线 / 下线工具**：通过后端 `config.yaml` 控制每个工具是否出现在 System Prompt、是否可调用。
- **自定义工具 / Skill**：以标准 skill 形式扩展工具（`skills/` 下每个目录一个技能），支持安装、上下线与热更新清单。
- **外部工具提供方**：`executor=external` 的工具经提供方通道（如页面调试扩展）转发执行，命令按目标页面定向。
- **错误分类回传**：工具执行失败返回完整堆栈 + 错误分类（origin），便于区分「参数问题」与「工具代码缺陷」。

## 目录结构

```
chat-bridge-main/
├── extend/                    # 镜像插件（Chrome MV3）
│   ├── manifest.json          # 扩展清单（权限、脚本、资源）
│   ├── background.js          # Service Worker（工具栏图标切换抽屉显隐）
│   ├── lib/                   # 公共前端模块
│   │   ├── vue.global.prod.js # 内联 Vue 3
│   │   └── dom-utils.js       # debounce / hashStr / textOf
│   ├── content/               # 内容脚本（按序号加载）
│   │   ├── 00_state.js        # 命名空间、共享 state、站点规则 PROFILES、面板常量
│   │   ├── 01_panel.js        # 面板注入与外观、post 通道
│   │   ├── 02_blocks.js       # 代码块解析、消息构造、extractBlocks
│   │   ├── 03_bridge.js       # 会话识别、sendPage、粘贴发送
│   │   ├── 04_observer.js     # 观察器与生命周期
│   │   └── 05_index.js        # 入口：消息监听、巡检、初始化
│   └── dialog/                # 悬浮对话框 UI
│       ├── dialog.html
│       ├── app.js             # 装配入口（createApp + 组件装配）
│       ├── parts/             # 抽屉逻辑分片（00_data ~ 09_skills）
│       └── styles/            # 样式分片（00_tokens ~ 05_narrow）
├── flask_server/              # 本地 Flask 工具服务
│   ├── server.py              # 兼容入口：委托 app.create_app()
│   ├── app.py                 # 应用装配：create_app() / 蓝图注册 / CORS / 运行期初始化
│   ├── runtime.py             # 运行期全局状态中心
│   ├── config_store.py        # config.yaml 读写与合并
│   ├── error_utils.py         # 错误分类与定位
│   ├── responses.py           # 错误响应辅助
│   ├── tool_helpers.py        # 工具通用辅助（参数校验、路径解析、体积控制）
│   ├── tool_meta.py           # 内置工具元数据声明（描述 + 参数表）
│   ├── tools_impl.py          # 内置工具实现与派发表
│   ├── yaml_utils.py          # YAML 标量原语
│   ├── routes/                # 各功能域蓝图
│   ├── custom_tools/          # 标准 skill 的解析 / 注册 / 执行（包）
│   ├── external_tools.py      # 外部工具提供方注册表与转发
│   ├── card_bus.py            # 外部卡片总线
│   ├── rules.py               # 规则文件读取与优先级
│   ├── prompt_sections.py     # 技能说明与技能清单收集
│   ├── config.yaml            # 配置唯一来源
│   ├── custom_tools.yaml      # 已安装自定义工具清单（自动维护）
│   └── _smoke_ct.py           # 自定义工具子系统冒烟测试
├── skills/                    # 标准 skill（自定义工具来源）
│   ├── json_tool/             # json_validate：校验并格式化 JSON
│   └── debug_chrome/          # 页面探查调试扩展
├── rules/                     # 用户规则（*.md）+ _meta.json（优先级）
├── docs/                      # 文档
├── scripts/                   # 根级运维脚本（check_quality.py）
└── _verify_fixes.py           # 根级校验脚本
```

## 安装与运行

### 1. 启动本地 Flask 工具服务

```bash
cd flask_server
pip install -r requirements.txt
python server.py
```

默认监听 `http://127.0.0.1:5000`。改端口需在 `config.yaml` 把 `flask.port` 改掉并重启服务。

### 2. 加载 Chrome 扩展

1. 打开 `chrome://extensions`，开启「开发者模式」。
2. 点击「加载已解压的扩展程序」，选择本项目的 `extend/` 目录。
3. 点击工具栏图标显示 / 隐藏悬浮对话框。

> 扩展通过后端下发的 `flaskUrl` 连接 Flask，配置不保存在浏览器中（统一由后端 `config.yaml` 管理）。

## 配置说明

- **`flask_server/config.yaml`**：后端配置唯一来源。
  - `flask.host` / `flask.port`：服务地址。
  - `default_profile` / `site_profiles`：按域名选择站点规则（`glm` / `deepseek`）。
  - `tools.<name>.enabled`：工具上下线开关。
  - `tools.run_command.languages`：`run_command` 支持的语言列表。
  - `limits.max_json_chars`：工具结果 JSON 体积上限。
- **`flask_server/custom_tools.yaml`**：自定义工具清单，由插件自动维护。

## 自定义工具 / Skill

通过扩展「设置」页可安装自定义工具：选择某个标准 skill 目录，插件会把它登记到
`custom_tools.yaml` 并生成可调用工具。示例见 `skills/json_tool`（`json_validate`：校验并格式化 JSON）。

内置工具声明在 `tool_meta.py`、实现与派发表在 `tools_impl.py`；改动后需重启服务。

## 开发

- **冒烟测试**：`python flask_server/_smoke_ct.py`。
- **修复验证**：`python _verify_fixes.py`。
- **质量扫描**：`python scripts/check_quality.py`（行数 / 圈复杂度 / 重复块）。

## 许可证

[MIT](LICENSE)
