# 参数声明迁移状态列复核附录

> 用途：供分发方维护 docs/tool-schema-migration.md 状态列。本附录只给逐项复核结论，不改结论源 90%（18/20）的数值，不自行勾选。

## 一、口径与分母

- 分发方口径：20 项清单 = 已勾 18 项 + 待勾 2 项（read_file.path anyOf 状态列、规则行）。
- 结论源 docs/00-STATUS.md：参数声明迁移清单勾选 90%（18/20），本附录不翻该数值。
- 实仓计数（origin/main 树）：docs/tool-schema-migration.md 可见 17 个已勾项与 1 个待勾项，合计 18 个 checkbox；与「18 已勾」口径差 1 处，如实登记、不自行调平，由分发方裁定。
- 本附录分母：20/20 行逐项复核。其中 17 行对应实仓已勾项、1 行对应实仓待勾项、2 行对应分发方口径的非 checkbox 项（规则行、状态列复核汇总行）。每行给出文档锚点、实装证据与复核状态。

## 二、逐项复核表（20 行）

| 序号 | 归属 | 文档锚点 / 判据 | 实装证据 | 状态 |
|---|---|---|---|---|
| 1 | 后端 3.1 | L33 tool_meta.py 21 内置工具参数声明改写 | L39 验证行：GET /tools 21 个 schema | 已勾 |
| 2 | 后端 3.1 | L40 custom_tools/loader.py 声明解析 | L41 normalize_params_schema 双输入幂等 | 已勾 |
| 3 | 后端 3.1 | L42 custom_tools/registry.py _normalize_param | L43 schema_param_names 校验 | 已勾 |
| 4 | 后端 3.2 | L47 tool_param_check.py L32 参数名读取 | L49 按 properties 键名拦截 | 已勾 |
| 5 | 后端 3.2 | L50 core/error_utils.py L43 L52 | L51 _declared_param_names 改读 schema | 已勾 |
| 6 | 后端 3.2 | L52 routes/tool_external.py L28 | L53 必填校验经 schema_required_names | 已勾 |
| 7 | 后端 3.2 | L54 custom_tools/loader.py L154 _dump_params | L55 anyOf 摊平为历史联合写法 | 已勾 |
| 8 | 后端 3.3 | L59 routes/tools.py L184 tools/all | L60 21 条 parameters 均为 schema | 已勾 |
| 9 | 后端 3.3 | L61 tools/tools_impl.py L354 L370 | L62 get_tool_params 返回标准 schema | 已勾 |
| 10 | 后端 3.3 | L63 custom_tools/meta.py L29 L70 L109 | L64 三处视图透传 schema | 已勾 |
| 11 | 后端 3.3 | L65 core/prompt_sections.py L92 | L66 管理视图透传、Prompt 注入零变化 | 已勾 |
| 12 | 前端 四 | L73 03_custom_tools.js L139-140 | test_tool_schema_adapter 13 项 | 已勾 |
| 13 | 前端 四 | L74 05c_prompt.js L180 | 6 项模板文案覆盖 | 已勾 |
| 14 | 前端 四 | L75 08_settings.js L56-57 L99-100 | 两处 render 经 toFlatParams | 已勾 |
| 15 | 测试 五 | L90 flask_server/tests 构造声明 | pytest 983/984 波动口径 | 已勾 |
| 16 | 测试 五 | L92 flask_server/scripts/_smoke_ct.py L84 | SMOKE OK | 已勾 |
| 17 | 测试 五 | L94 前端测试卡片参数 | js 380 全绿 | 已勾 |
| 18 | 状态列 | L25 read_file.path anyOf 策略行 | tool_meta.py L94 双分支实装 | 待勾，分发方裁定 |
| 19 | 规则行 | L6-7 规则说明，非 checkbox 项 | 文档规则文字，非改动项 | 待勾，分发方裁定 |
| 20 | 汇总行 | L39 L55 与 flask_server 下 anyOf 命中 20 处 | grep 命中数，复核输入 | 非独立改动项 |

## 三、三处重点实装证据

1. tool_meta.py L89-104：read_file 的 parameters 为 type object 加 properties 加 required 数组；properties.path 用 anyOf，两支分别为 type string 与 type array（items string、maxItems 20）；required 只含 path。对应文档 L25 策略行与 L39 验证行。
2. custom_tools/loader.py L178-192：_dump_params 读 properties 与 required，遇到 anyOf 时把该参数记为历史联合写法；L289 normalize_params_schema 对 raw.parameters 归一。对应文档 L40、L54-55。
3. GET /tools：routes/tools.py L146 声明 GET /tools，L154 起遍历 runtime.TOOLS 逐项透传声明；同文件 L171 声明 GET /tools/all，L180 同样遍历。tool_meta.py L28 起 TOOLS 共 21 个内置工具，parameters 均为标准 schema 对象。对应文档 L39、L59-60。

flask_server 下 anyOf 与 read_file.path 声明相关 grep 命中 20 处（含注释、夹具、实现），仅作状态列复核输入；该 20 处是命中数，与「20 项清单」不是同一分母，不混用。

## 四、复核结论

- 待勾 1（read_file.path anyOf 状态列）：实装证据齐（tool_meta.py L94、文档 L39 验证行、GET /tools 输出 schema），建议分发方按实仓勾状态列；本附录不代勾。
- 待勾 2（规则行）：属文档顶部规则说明，非改动项，建议分发方裁定是否计入清单分母；本附录不代改。
- 结论源 90%（18/20）保持不变；本附录只交复核结论，逐项可核 20/20，供分发方维护状态列。