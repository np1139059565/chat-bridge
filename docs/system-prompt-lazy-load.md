# System Prompt 按需加载优化方案（暂不实施）

> 状态：方案已定，**暂不实施**。
> 实施前置：先修复 read_file 工具「模式开关」故障（部分页面不支持粘贴文件），修复并验证通过后再启动本优化。
> 记录：2026-11-11

## 一、问题

前端 `extend/dialog/parts/05c_prompt.js` 的 `generateSystemPrompt()` 把工具全表、规则清单、技能清单与说明段一次拼进 System Prompt，实测约 3693 字符：工具列表 31 项占 1966、技能列表含说明 598、规则 359、调用格式 573。

同时 prompt 正文又要求 AI「先调 list_rules / list_skills / get_tool_params 查看」，与全量清单重复并存：付了全表上下文税，又让 AI 再查一遍。

后端 `flask_server/core/system_prompt.py` 已按 `docs/split-mirror-and-tools-service.md` 3.2 节与 `docs/work-ai-a.md` A-2 交付精简主体 `GET /v1/system_prompt`，实测 1116 字符（身份 101 / 规则 128 / 技能 748 / 先查参数 108），规则只给名+优先级、不塞工具表与方言。前端未接该接口，仍走本地全量拼装。缺的是规格里的阶段 2：翻译员取回标准主体后追加方言。

## 二、目标边界（三层拆分）

**常驻（每轮必带，目标 <= 1.2k）**：身份 1 句；bridge-chat-call 代码块调用格式与回传格式、单块约束（协议，不可省）；一句先查参数通则（不确定工具有哪些用 list_tools，调用前 get_tool_params，规则 read_rule，技能文档 read_skill）；规则只留名字 + 优先级（always 标注「开始前先 read_rule」）；语音约定仅在 bridgePush.voice 开启时注入。

**按需（prompt 只给钥匙）**：工具全表 -> list_tools；参数 schema -> get_tool_params；规则正文 -> read_rule；技能清单 -> list_skills；技能文档与说明段 -> read_skill。

**方言（前端按开关拼）**：调用/回传格式、朗读稿、站点特定提示，不回灌后端主体。

## 三、落地两步

**步骤 1（最小改动，立减约 2.5k）**：`generateSystemPrompt()` 改为取 `/v1/system_prompt` 的 `system_prompt` 主体，前端只追加方言段；删除本地 `listLines / ruleLines / skillLines` 与三段「读取说明」重复文案。`loadRules() / loadPromptSections() / /tools` 仍保留给设置页，但不再进 prompt。接口不可达时回退旧拼法，prompt 不得为空。

**步骤 2（可选，再砍约 500）**：后端 `skills_section()` 目前仍把 `sections()` 统一说明段拼进主体（748 字符的大头），收敛为「技能名 + 摘要 + 工具名」，说明段移到 `read_skill`；`rules_section` 已够瘦不动。`test_system_prompt.py` 补断言「主体不含技能说明正文」。

## 四、验收与回退

1. `/csp` 复制文本 <= 1.5k，含调用格式与先查参数通则，不含 31 项工具名与规则摘要；
2. 新会话 AI 首轮能自发 `list_tools -> get_tool_params -> 调工具` 成功；
3. always 规则被首轮 `read_rule` 读取；
4. 语音开/关时主体一致，仅方言段有无差别；
5. `python -m pytest tests -q` 全绿。

回退：旧函数改名 `generateSystemPromptLegacy()` 保留，配置加开关，异常或对照时一键切回。`/v1/system_prompt` 已在线（实测 200），步骤 1 不依赖后端发版。

## 五、不做

不改工具执行链路、不动 `/v1/chat/completions`、不把指令类工具名混进 AI 清单（`extensions.md` R1）、不复制规则/技能数据到第二真源。
