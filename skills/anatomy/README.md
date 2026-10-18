# anatomy · 本地适配说明

本技能来自 [wheresryan22/anatomy](https://github.com/wheresryan22/anatomy)，按本工程的 skill 规范做了适配。

## 两层结构

1. **标准 skill 基础**：根目录 `SKILL.md`（含 `name` / `description` 前置元数据与完整正文），承载 Anatomy 的绘图方法论。
2. **自定义工具扩展**：根目录 `tool.json` 声明 `anatomy_illustration`，脚本为 `scripts/anatomy_tool.py`，供网页 AI 调用。

## 工具能做什么

| 动作 | 参数 | 返回 |
| --- | --- | --- |
| `list` | 无 | 全部示例目录，及各自是否带预构建 HTML |
| `export` | `example`（必填）、`file`（可选） | 复制 HTML 到 `flask_server/static/anatomy/`，返回 `/static/anatomy/...` 可访问路径 |

示例导出后可通过 `http://127.0.0.1:5000` 加返回的 `url_path` 在浏览器查看。

## 运行环境

- 本工具只用 Python 标准库，**不需要 Node.js**。
- 因此只能导出 `examples/` 中**已预构建**的 HTML；`spot-plate`、`test-rig` 两个示例没有预构建成品，需本机安装 Node.js 20.10 以上后用 `node build.mjs` 现场构建。
- 生成全新插图的能力来自 `SKILL.md` 的绘图方法论，由宿主 AI 按文档执行，不经过本工具脚本。

## 目录说明

- `examples/`：八个示例，含构建脚本与部分预构建 HTML。
- `kit/`：绘图基础库（车削、管线、几何稽核等）。
- `references/`：方法论参考文档。
- `scripts/`：Anatomy 自带的几何稽核与浏览器自检脚本（需 Node.js），另含本工程新增的 `anatomy_tool.py`。
