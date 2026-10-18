# anatomy · 本地适配说明

本技能来自 [wheresryan22/anatomy](https://github.com/wheresryan22/anatomy)，按本工程的 skill 规范做了适配。

## 两层结构

1. **标准 skill 基础**：根目录 `SKILL.md`（含 `name` / `description` 前置元数据与完整正文），承载 Anatomy 的绘图方法论。
2. **自定义工具扩展**：根目录 `tool.json` 声明 `anatomy_illustration`，脚本为 `scripts/anatomy_tool.py`，供网页 AI 调用。

## 工具能做什么

| 动作 | 参数 | 返回 |
| --- | --- | --- |
| `list` | 无 | 全部示例目录，及各自是否有预构建 HTML、是否可构建 |
| `export` | `example`（必填）、`file`（可选） | 复制 HTML 到 `flask_server/static/anatomy/`，返回 `/static/anatomy/...` 可访问路径 |
| `build` | `example`（必填）、`file`（可选） | 先用 Node 执行该示例的 `build.mjs` 重新生成，再导出并返回路径 |

产物导出后可通过 `http://127.0.0.1:5000` 加返回的 `url_path` 在浏览器查看。

## 运行环境

- `export` 只用 Python 标准库，不需要 Node.js。
- `build` 需要 Node.js 20.10 以上。脚本按「工程 `runtime/node/` 下的便携版 → 系统 PATH」的顺序查找，找到即用。
- 构建子进程有 50 秒上限（自定义工具单次执行上限为 60 秒）。示例越大越容易超时；超时会明确提示改用 `export` 导出已预构建的成品。

## 示例可构建性

| 示例 | 预构建 HTML | 可构建 |
| --- | --- | --- |
| `arcade-cabinet` | 有 | 是 |
| `desk-computer` | 有 | 是 |
| `dial-indicator` | 有 | 是 |
| `raptor-engine` | 有 | 是 |
| `ripple-tank` | 有 | 是 |
| `turning-dial` | 有 | 是 |
| `spot-plate` | 无 | 否，React 组件形式，无 `build.mjs` |
| `test-rig` | 无 | 否，React 组件形式，无 `build.mjs` |

生成全新插图的能力来自 `SKILL.md` 的绘图方法论，由宿主 AI 按文档执行，不经过本工具脚本。

## 目录说明

- `examples/`：八个示例，含构建脚本与部分预构建 HTML。
- `kit/`：绘图基础库（车削、管线、几何稽核等）。
- `references/`：方法论参考文档。
- `scripts/`：Anatomy 自带的几何稽核与浏览器自检脚本（需 Node.js），另含本工程新增的 `anatomy_tool.py`。
