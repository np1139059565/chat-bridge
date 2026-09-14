# AI 工具调用镜像插件（chat-bridge）

Chrome 扩展 + 本地 Flask 工具服务：在网页 AI 对话框与本地工具执行之间架起桥梁。
扩展在网页 AI 对话页与悬浮对话框之间形成**双向镜像**，自动从对话中提取 `tool` 代码块，
调用本地 Flask 服务执行（文件读写、搜索、JSON 校验等），并把结果回灌进对话。

## 特性

- **双向镜像**：网页对话 ↔ 扩展悬浮对话框实时同步。
- **工具调用**：从对话中提取 `tool` 代码块，交给本地工具服务执行，结果写回 System Prompt。
- **可上线 / 下线工具**：通过后端 `config.yaml` 控制每个工具是否出现在 System Prompt、是否可调用。
- **自定义工具 / Skill**：通过标准 skill 安装自定义工具（如 `skills/json_tool`），支持热重载。
- **AI 自愈**：工具执行失败返回完整堆栈 + 错误分类，便于 AI 区分「参数问题」与「代码缺陷」。

## 目录结构

```
chat-bridge/
├── chrome extension/          # Chrome MV3 扩展
│   ├── manifest.json          # 扩展清单（权限、脚本、资源）
│   ├── background.js          # Service Worker（后台）
│   ├── content.js             # 内容脚本（注入网页、提取代码块）
│   ├── dialog/                # 悬浮对话框 UI
│   │   ├── dialog.html
│   │   ├── app.js             # 对话框逻辑（Vue 3）
│   │   └── style.css
│   └── lib/
│       └── vue.global.prod.js # 内联 Vue 3
├── flask_server/              # 本地 Flask 工具服务
│   ├── server.py              # 主服务（API、热重载、CORS）
│   ├── tools_impl.py          # 内置工具实现（可热重载）
│   ├── custom_tools.py        # 自定义工具安装 / 查询
│   ├── custom_tools.yaml      # 自定义工具清单（自动维护）
│   ├── config.yaml            # 后端配置（唯一来源）
│   ├── requirements.txt       # Python 依赖
│   └── _smoke_ct.py           # 冒烟测试
├── skills/                    # 自定义工具 skill
│   └── json_tool/
├── graphify-out/              # 知识图谱产物（由 graphify 生成，见 .gitignore）
├── README.md
└── LICENSE
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
2. 点击「加载已解压的扩展程序」，选择本项目的 `chrome extension/` 目录。
3. 点击工具栏图标显示 / 隐藏悬浮对话框。

> 扩展通过后端下发的 `flaskUrl` 连接 Flask，配置不保存在浏览器中（统一由后端 `config.yaml` 管理）。

## 配置说明

- **`flask_server/config.yaml`**：后端配置唯一来源。
  - `flask.host` / `flask.port`：服务地址。
  - `default_profile` / `site_profiles`：按域名选择站点规则（`glm` / `deepseek`）。
  - `tools.<name>.enabled`：工具上下线开关。
- **`flask_server/custom_tools.yaml`**：自定义工具清单，由插件自动维护。

## 自定义工具 / Skill

通过扩展「设置」页可安装自定义工具：选择某个标准 skill 目录，插件会把它登记到
`custom_tools.yaml` 并生成可调用工具。示例见 `skills/json_tool`（`json_validate`：校验并格式化 JSON）。

内置工具实现放在 `tools_impl.py`，支持热重载——改动后无需重启服务即可生效。

## 开发

- **知识图谱**：运行 `graphify` 可生成 `graphify-out/`（架构概览、社区、上帝节点等），
  辅助理解代码关系，产物已加入 `.gitignore`。
- **冒烟测试**：`python flask_server/_smoke_ct.py`。

## 许可证

[MIT](LICENSE)
