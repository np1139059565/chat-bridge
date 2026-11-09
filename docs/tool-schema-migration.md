# 工具参数格式迁移进度（自定义格式 → 标准 JSON Schema）

> 用途：`docs/split-mirror-and-tools-service.md` 决策 7 要求把参数声明彻底改写为
> 标准 JSON Schema，牵动前后端多处。本文件逐项登记，避免漏改。
>
> 规则：每改一处，把 `[ ]` 改为 `[x]`，并写明验证方式。
> **不允许只改声明不改消费方**——那样会让运行时静默失效。

## 一、格式对照

| 维度 | 现格式 | 标准格式 |
|---|---|---|
| 容器 | 数组 `[{...}]` | 对象 `{"type":"object","properties":{...}}` |
| 单个参数 | `{"name":"path","type":"string","required":true}` | `properties.path = {"type":"string"}` |
| 必填 | 每个参数自带 `required` 布尔 | 顶层 `required: ["path"]` 数组 |
| 说明 | `description` | 同名保留 |
| 联合类型 | `"string | array"` | **标准无此写法**，需逐项决策 |

## 二、联合类型清单（需人工决策）

已全量扫描 `flask_server/` 下全部 `.py` 文件，搜索 `"type": "x | y"`、`"type": ["x"]`、`anyOf`、`oneOf` 四类写法。结论：**联合类型只有一处**。

| 工具 | 参数 | 现声明 | 策略 | 状态 |
|---|---|---|---|---|
| `read_file` | `path` | `"string | array"` | 改用 `anyOf`，两支分别为 `{"type":"string"}` 与 `{"type":"array","items":{"type":"string"},"maxItems":20}`（依据决策 8） | [ ] |

扫描覆盖范围：`flask_server/tools/`、`flask_server/custom_tools/`、`flask_server/routes/`、`flask_server/core/`。不区分大小写。

## 三、后端改动清单

### 3.1 参数声明本体

- [ ] `flask_server/tools/tool_meta.py` — 20 个内置工具的参数声明改写，逐项核对：
      `get_tool_params`、`list_dir`、`search_file`、`search_content`、`read_file`、
      `read_image`、`push_file`、`list_skills`、`read_skill`、`read_lints`、
      `replace_in_file`、`write_to_file`、`delete_file`、`list_rules`、`read_rule`、
      `run_command`、`command_task`、`memory_search`、`memory_inspect`、`memory_refine`
      （其中 `list_skills` 与 `list_rules` 参数为空表，迁移后应为 `{"type":"object","properties":{}}`）
- [ ] `flask_server/custom_tools/loader.py` — skill 工具声明解析（第 265 行 `for p in raw.get("parameters")`）
- [ ] `flask_server/custom_tools/registry.py` — `_normalize_param` 与保存逻辑（113–114、231、241 行）

### 3.2 参数名读取方（改格式后必须同步）

- [ ] `flask_server/tools/tool_param_check.py` L32 — `[p.get("name") for p in entry.get("parameters")]`
      改为从 `properties` 取键名
- [ ] `flask_server/core/error_utils.py` L43、L52 — `_declared_param_names` 同上
- [ ] `flask_server/routes/tool_external.py` L28 — 外部工具参数读取
- [ ] `flask_server/custom_tools/loader.py` L154 — `_dump_params`

### 3.3 对外输出结构（影响前端与 AI）

- [ ] `flask_server/routes/tools.py` L184 — `/tools/all` 输出
- [ ] `flask_server/tools/tools_impl.py` L354、L370 — `get_tool_params` 返回
- [ ] `flask_server/custom_tools/meta.py` L29、L70、L109 — 三处对外视图
- [ ] `flask_server/core/prompt_sections.py` L92 — 技能工具归集

> 注意：`get_tool_params` 是 AI 查询参数的主要入口。改格式后，
> AI 看到的结构会变——需同步确认 System Prompt 里的使用说明是否仍准确。

## 四、前端改动清单

- [ ] `extend/dialog/parts/03_custom_tools.js` L139–140 — 读 `p.type`、`p.required` 组装自定义工具参数
- [ ] `extend/dialog/parts/05c_prompt.js` L180 — 读 `p.name`、`p.type` 生成提示词占位符
- [ ] `extend/dialog/parts/08_settings.js` L56–57、L99–100 — 设置页参数表两处渲染 `p.type`、`p.required`

> 上述三处都按扁平参数项读取（`name` / `type` / `required`）。改为标准格式后，
> 需要一层适配把 `properties` + 顶层 `required` 还原成扁平列表。
>
> **适配层落点**：在 extend/lib/ 下新建 tool-schema-adapter.js（本任务待建），导出
> `toFlatParams(schema)`（对象 schema → 扁平参数数组）。三处调用方改为先取回标准
> schema、再经适配层转换。适配层放 lib/ 而非 parts/，原因是它不持有界面状态，
> 只做纯数据转换，与现有 lib/ 下的工具模块同类。
>
> `extend/dialog/parts/07b_params.js` 处理的是卡片参数**值**（序列化为 JSON 文本供编辑），
> 不读声明字段，无需改动。

## 五、测试改动清单

- [ ] `flask_server/tests/` 中所有构造工具声明的地方（`"parameters": [...]`）
- [ ] `flask_server/scripts/_smoke_ct.py` L84 — 断言 `parameters[0]["name"]`
- [ ] 前端测试中构造卡片参数的地方

## 六、验证方式

每完成一个阶段，按下列顺序验证：

1. **单测**：`python -m pytest tests -q`，全绿（基线 942 项，2026-11-09 于 `a974f83` 实测）。
2. **前端测试**：`node --test flask_server/tests/js/*.test.js`，全绿（基线 380 项，同日实测）。
3. **质量闸门**：`python scripts/quality_rules.py`，无新增违规。
4. **实机冒烟**：
   - 设置页打开「工具」区块，13 个内置工具的参数都能正常展开编辑；
   - 抽屉里执行一张卡片，参数输入框正常渲染、保存后能执行；
   - 网页 AI 调 `get_tool_params` 拿到的结构符合预期。

## 七、进度记录

| 日期 | 完成项 | 验证 |
|---|---|---|
| — | 建立本清单 | — |
| 2026-11-09 | 核实清单事实：工具数 13→20 并列出名单；联合类型全量扫描确认仅 `read_file.path` 一处，策略定为 `anyOf`；基线更新为 py 942 / js 380；前端条目按实测改写并确定适配层落点 | 扫描 + 实测 |
