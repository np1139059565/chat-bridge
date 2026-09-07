# 测试体系改造方案

## 一、目标

为 `chat-bridge` 工程建立分层测试体系，实现：

1. Python 代码行覆盖率达到 80% 以上；
2. JavaScript 代码在 e2e 场景下被真实执行：content.js 采函数覆盖率，app.js 做方法验证，background.js 验证注册；
3. HTML 通过关键元素存在性断言覆盖，CSS 通过视觉快照与静态检查覆盖；
4. 每次提交自动触发测试，不通过则提交失败；
5. CI 环境完整跑通双栈测试与 e2e。

## 二、技术选型

| 层级 | 技术 | 用途 |
|---|---|---|
| Python 单元/API 测试 | pytest + Flask test_client | 覆盖 `tools_impl.py`、`server.py` 路由、`custom_tools.py` |
| Python 覆盖率 | pytest-cov（coverage.py） | 生成行覆盖率报告，设门槛 |
| JS e2e | Playwright（Python 驱动） | 加载扩展、模拟页面交互、采集 JS 覆盖率 |
| JS 覆盖率 | Playwright `browser_context.coverage` + v8 覆盖率 | 采集 e2e 执行时扩展 JS 的行覆盖 |
| HTML 覆盖 | Playwright 元素存在性/可见性断言 | 验证对话框关键 DOM 节点 |
| CSS 覆盖 | Playwright `to_have_screenshot` + stylelint | 视觉回归 + 静态规则检查 |
| 提交拦截 | pre-commit（本地）+ GitHub Actions（CI） | 提交前跑快速测试，CI 跑全套 |

## 三、目录结构

```
chat-bridge/
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # pytest 夹具：Flask client、临时目录、配置隔离
│   ├── test_tools_impl.py             # 内置工具函数测试
│   ├── test_server_api.py             # Flask API 路由测试
│   ├── test_custom_tools.py           # 自定义工具解析/安装/执行测试
│   ├── test_hot_reload.py             # 热重载与自愈流程测试
│   ├── e2e/
│   │   ├── conftest.py                # Playwright 夹具：启动 Flask、加载扩展
│   │   ├── test_extension_loaded.py   # 扩展加载、对话框渲染、HTML 元素断言
│   │   ├── test_tool_call_flow.py     # 端到端工具调用链路
│   │   └── test_visual_snapshot.py    # CSS 视觉回归快照
│   ├── fixtures/
│   │   ├── demo_skill/                # 测试用标准 skill
│   │   └── mock_pages/                # e2e 用的模拟 AI 对话页
├── pytest.ini                         # pytest 配置
├── .coveragerc                        # Python 覆盖率配置
├── .pre-commit-config.yaml            # pre-commit 钩子配置
├── .github/
│   └── workflows/
│       └── tests.yml                  # CI 测试流水线
├── package.json                       # JS 测试依赖（Playwright、stylelint）
└── stylelint.config.js                # CSS 静态检查规则
```

## 四、测试分层

### 1. Python 单元测试

覆盖目标：

- `tools_impl.py` 全部工具函数：
  - 参数校验（缺参、别名参数、空串）
  - 正常路径（文件读写、目录列举、内容搜索、替换）
  - 边界（不存在的路径、不唯一的 old_str、limit/offset）
- `server.py` 路由：
  - `GET /tools` 工具目录（含下线工具过滤）
  - `POST /tool` 调用成功/参数错误/未知工具/下线工具
  - `GET/POST /config` 配置读写、端口变更 requireRestart
  - `POST /hot_fix` 打补丁与回滚
  - 自定义工具路由（scan/install/manage）
- `custom_tools.py`：
  - `parse_skill` 解析各种合法/非法 tool.json
  - `install` / `remove` / `update` / `run`
  - 子进程执行成功/失败/非零退出码

### 2. JS e2e 测试（Playwright）

浏览器加载扩展后，在模拟 AI 对话页面上执行真实流程：

- 扩展加载：manifest 有效、service worker 启动、content script 注入
- 悬浮对话框渲染：关键 HTML 元素存在且可见
- 工具调用链路：在模拟页面生成 tool 代码块 → content.js 提取 → 对话框显示卡片 → 调用 Flask → 结果回显
- 会话隔离：切换会话后消息与卡片状态独立
- CSS 视觉回归：对对话框 UI 截图对比基线

### 3. HTML/CSS 覆盖

- HTML：e2e 断言对话框关键元素（标题、工具列表、卡片容器、设置面板）存在且可见。
- CSS：
  - stylelint 静态检查 `style.css` 规则完整性；
  - Playwright 截图快照验证 UI 渲染无回归。

## 五、覆盖率目标与采集

### Python

- 配置 `.coveragerc`：
  - 源目录：`flask_server/`
  - 排除：`_smoke_ct.py`、`_verify_fixes.py`、`tests/`
  - 设 `fail_under = 80`
- 采集：`pytest --cov=flask_server --cov-report=term-missing --cov-report=xml`

### JavaScript

- Playwright 通过 CDP 启用 v8 覆盖率：
  - `context.new_page()` 前调 `context.new_cdp_session(page)` 启用 `Profiler.enable` 与 `Profiler.startPreciseCoverage`
  - 测试结束时 `Profiler.takePreciseCoverage` 获取覆盖率数据
  - 过滤只统计 `chrome-extension://` 协议下的 JS 文件
- 只对扩展脚本（`content.js`、`dialog/app.js`、`background.js`）统计；`lib/vue.global.prod.js` 排除。
- 门槛：核心扩展 JS 行覆盖 ≥ 60%，在 CI 中通过自定义脚本断言。

## 六、提交拦截

### 本地 pre-commit

`.pre-commit-config.yaml` 包含：

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: python -m pytest tests/ -x --cov=flask_server --cov-fail-under=80
        language: system
        pass_filenames: false
      - id: stylelint
        name: stylelint
        entry: npx stylelint "chrome extension/dialog/style.css"
        language: system
        pass_filenames: false
```

### CI

`.github/workflows/tests.yml`：

- 触发：push、pull_request
- 步骤：
  1. checkout
  2. setup Python 3.11，安装依赖
  3. setup Node 20，安装 Playwright 浏览器
  4. 运行 Python 单测 + 覆盖率
  5. 启动 Flask，运行 Playwright e2e
  6. 运行 stylelint
  7. 上传覆盖率报告

## 七、实施步骤

1. 建立测试目录与 pytest 配置；
2. 编写 Python 单元/API 测试并达标；
3. 搭 Playwright e2e 环境（package.json、模拟页面、扩展加载）；
4. 编写 e2e 用例（扩展加载、工具链路、HTML 断言）；
5. 接入 JS 覆盖率采集脚本；
6. 配 stylelint 与视觉快照基线；
7. 配 pre-commit 与 CI 流水线；
8. 验证提交失败拦截与 CI 通过。

## 八、风险与对策

| 风险 | 对策 |
|---|---|
| Chrome 扩展在 headless 下加载受限 | 使用 `--load-extension` + `channel='chromium'`；必要时启用 `--headless=new` |
| e2e 依赖本地 Flask 服务端口冲突 | 测试用独立端口（如 5100），通过环境变量注入 |
| 视觉快照因平台差异不稳定 | 限定视口尺寸、系统字体；CI 与本地均用 Linux Chromium 基线 |
| JS 覆盖率采集协议在未来 Playwright 版本变动 | 锁定 Playwright 版本，封装覆盖率采集工具函数 |
| 扩展 `content.js` 依赖真实站点 DOM 结构 | e2e 使用本地 fixture 模拟页面，不依赖外网 |
