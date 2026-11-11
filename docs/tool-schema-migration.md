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

- [x] `flask_server/tools/tool_meta.py` — 21 个内置工具的参数声明改写，逐项核对：
      `list_tools`、`get_tool_params`、`list_dir`、`search_file`、`search_content`、`read_file`、
      `read_image`、`push_file`、`list_skills`、`read_skill`、`read_lints`、
      `replace_in_file`、`write_to_file`、`delete_file`、`list_rules`、`read_rule`、
      `run_command`、`command_task`、`memory_search`、`memory_inspect`、`memory_refine`
      （其中 `list_skills` 与 `list_rules` 参数为空表，迁移后应为 `{"type":"object","properties":{}}`）
      验证：实测 GET /tools 21 个内置工具全为 schema；`list_skills`/`list_rules` 为空 schema；`read_file.path` 为 anyOf 双分支。
- [x] `flask_server/custom_tools/loader.py` — skill 工具声明解析（第 265 行 `for p in raw.get("parameters")`）
      验证：`normalize_params_schema` 兼容 schema/数组双输入且对 schema 幂等；`_smoke_ct.py` 数组输入冒烟通过。
- [x] `flask_server/custom_tools/registry.py` — `_normalize_param` 与保存逻辑（113–114、231、241 行）
      验证：声明与必填校验改经 `schema_param_names` 与 `schema_required_names`，test_custom_tools_registry 全绿。

### 3.2 参数名读取方（改格式后必须同步）

- [x] `flask_server/tools/tool_param_check.py` L32 — `[p.get("name") for p in entry.get("parameters")]`
      改为从 `properties` 取键名
      验证：读取辅助双格式兼容；未知参数拦截实测按 properties 键名返回声明列表。
- [x] `flask_server/core/error_utils.py` L43、L52 — `_declared_param_names` 同上
      验证：`_declared_param_names` 改读 schema 键名；错误提示实测列出正确参数名。
- [x] `flask_server/routes/tool_external.py` L28 — 外部工具参数读取
      验证：外部工具必填校验经 `schema_required_names`；py_compile 与相关测试通过。
- [x] `flask_server/custom_tools/loader.py` L154 — `_dump_params`
      验证：schema 摊平为历史条目写出、anyOf 记为 "string | array"；空兜底字面量与 schema 形态对齐（无行为变化）。

### 3.3 对外输出结构（影响前端与 AI）

- [x] `flask_server/routes/tools.py` L184 — `/tools/all` 输出
      验证：实测 GET /tools/all 21 条 parameters 均为 schema，缺失兜底空 schema。
- [x] `flask_server/tools/tools_impl.py` L354、L370 — `get_tool_params` 返回
      验证：实测 `get_tool_params` 返回标准 schema，顶层 required 与 properties 可正确取键。
- [x] `flask_server/custom_tools/meta.py` L29、L70、L109 — 三处对外视图
      验证：三处视图透传 schema、缺失兜底空 schema；相关测试全绿。
- [x] `flask_server/core/prompt_sections.py` L92 — 技能工具归集
      验证：仅设置页管理视图透传 schema，System Prompt 注入路径文本零变化；A-2 消费面复核不受影响。

> 注意：`get_tool_params` 是 AI 查询参数的主要入口。改格式后，
> AI 看到的结构会变——需同步确认 System Prompt 里的使用说明是否仍准确。

## 四、前端改动清单

- [x] `extend/dialog/parts/03_custom_tools.js` L139–140 — 读 `p.type`、`p.required` 组装自定义工具参数 — 验证：C-4 f4fa5b5 经 toFlatParams 读取；test_tool_schema_adapter 13 项 + 399 项前端全绿（分发方验收 2026-11-11）
- [x] `extend/dialog/parts/05c_prompt.js` L180 — 读 `p.name`、`p.type` 生成提示词占位符 — 验证：C-4 f4fa5b5 usageOf 经适配层；test_05c_prompt_schema_coverage 6 项覆盖模板文案（分发方验收 2026-11-11）
- [x] `extend/dialog/parts/08_settings.js` L56–57、L99–100 — 设置页参数表两处渲染 `p.type`、`p.required` — 验证：C-4 f4fa5b5 两处 render 经 toFlatParams；08b 仅补说明不重复摊平（分发方验收 2026-11-11）

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

- [x] `flask_server/tests/` 中所有构造工具声明的地方（`"parameters": [...]`）
      验证：pytest 983/984（唯一失败为既有波动，stash 基线对照证实与本次无关）；`_smoke_ct.py` L56 数组输入有意保留覆盖兼容路径。
- [x] `flask_server/scripts/_smoke_ct.py` L84 — 断言 `parameters[0]["name"]`
      验证：断言改为 schema 口径，SMOKE OK。
- [x] 前端测试中构造卡片参数的地方
      验证：卡片参数为调用值对象，不随声明迁移变化；js 380 全绿。`test_toolconf_swallow.test.js` 的声明夹具仍为数组格式，随第四节前端适配任务迁移。

## 六、验证方式

每完成一个阶段，按下列顺序验证：

1. **单测**：`python -m pytest tests -q`，全绿（基线 949 项，2026-11-09 于 B-1 合入后实测）。
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
| 2026-11-09 | 合入 `list_tools` 后复核：工具数 20→21，基线 py 942→949 | 实测 |
| 2026-11-10 | B-3 完成：第三节与第五节 py 侧全部勾选；loader 与 `_smoke_ct.py` 保留数组输入作兼容路径；js 声明夹具随第四节前端任务迁移；`has_params` 漂移登记 work-ai-b Q-7 | 实测 |

| 2026-11-11 | C-4 前端适配层验收通过并合入 `8313824`，第四节三项由分发方逐项勾选；`05c_prompt.js` System Prompt 模板同步已在 f4fa5b5 落地并随本次验收确认；阶段 1b 前端部分收口 | 分发方 |

| 2026-11-11 | B-4 Q-7 补丁合入 `790af6e`，后端 `has_params` 语义与前端三项全部到位，阶段 1b 整体收口 | 分发方 |
