# R0《配置八跳有效性核查报告》

> 任务：dispatcher-20261118T025047-6d5ccb（R0 配置八跳有效性核查，2026-11-18 02:50 下发）。
> 执行：AI-A @ work/ai-a。核查对象：old = origin/legacy/old-stable 实时尖端、main = origin/main、bus = 32e83dd 独立根冻结态（经本地仓只读取证）。
> 方式：只读取证——blob 矩阵（ls-tree 逐文件）、内容级 diff、提交图可达性（merge-base --is-ancestor）、逐跳 grep 溯源。零实现代码改动。

## 一、八跳 × 三版本 blob 矩阵

| 跳 | 文件 | old | main | bus32 | 分配态 |
|---|---|---|---|---|---|
| 1 定义 | core/tool_config.py | 39c38af | 8d979af | 39c38af | old=bus≠main（old 超 main 13 行布尔严格解析） |
| 1 定义 | config/definition.yaml | 903 行 | 507 行 | 929 行 | 三版各异（见 R3） |
| 1 定义 | parts/00_data.js | 68dac98 | 0fbb849 | 68dac98 | old=bus≠main（DEFAULT_BRIDGE_PUSH check.* 段三树同构） |
| 2 渲染 | parts/08e_toolconf.js | 同 | 同 | 同 | 三版同 blob（独立工具配置页） |
| 2 渲染 | parts/08 系设置页（08/08b/08g/08i/08m） | old=bus | 独立 | =old | old=bus≠main |
| 2 渲染 | parts/08k_config_blocks.js | 同源 | 同源 | 平行自研 | old/main 同源（9e99c37 建）；bus e9054f2 |
| 3 草稿缓存 | parts/08i_config_cache.js | 6914116(204行) | 91df1a1(135行) | 6914116 | old=bus≠main（main 为 v3 cache 版） |
| 3 草稿缓存 | flask_server/config_draft_store.py | d6fa053 | 无此文件 | d6fa053 | main 删 draft 链 |
| 4 POST | routes/config_route.py | 2431b78 | 71b3cbb | 2431b78 | old=bus≠main（main 改 C-3a 寄存 + D2 按档案合并） |
| 4 POST | parts/08j_config_actions.js | 基线 | 独立 | 基线+aed612e | bus 领先 old 一笔（skill-toggle 收敛） |
| 5 规整 | core/config_store.py | 8db1cb6 | ce6642e | 8db1cb6 | old=bus≠main |
| 6 写盘 | core/config_file.py | bd5cead | 382cb27 | bd5cead | old=bus≠main |
| 6 写盘 | core/yaml_utils.py | 36af39b | 36af39b | 36af39b | 三版同 |
| 7 GET 回读 | config_store.py L203 组装 tool_config/system_config | 8db1cb6 | ce6642e | 8db1cb6 | 同跳 5 |
| 8 消费 | screenshot_store / push_pipeline / message_router | 46923bf / e102c50 / 32634f3 | 同左 | 同左 | 三版同 blob，消费端零分叉 |

总述：配置八跳上 old 与 bus 高度同步（唯 08j/09_skills 的 aed612e 与 def.yaml 29 行差）；main 独立演化（C-3a 寄存 + v3 cache + 删 draft 链）。运行时消费端三版零分叉——配置项失效只可能出自跳 1–7。

## 二、五重点项逐项结论（失效清单）

| # | 重点项 | 判定 | 断点与证据 |
|---|---|---|---|
| F1 | 工具返回 JSON 结果长度上限 | 未实现（非失效回归） | 断在跳 1：三版 CONFIG_SCHEMA（tool_config.py）均无此键；跳 8 消费端三版同 blob 无读取；仅 main tools.py:314 提示层建议 head/tail。落地需定义+出口截断+夹具三件，本片不实现 |
| F2 | 质量检测开关 | 无失效 | 全链同构：00_data DEFAULT_BRIDGE_PUSH（check.*）→ 08c_bridge.js:243 区块渲染 → bridge_store.py:72 存放 → 05e_quality/05g_cards 消费；05e/08c/bridge_store 三版同 blob |
| F3 | 配置刷新被还原 | 无失效（已修复） | old/bus 修复链 4e9a457（全局单键刷新不丢）+ 595cd9e（差异即时刷新/切站重建草稿）+ 180f90b（白名单比对/还原不消失）；main 无 draft 链，走 C-3a 客户端注册表 custom_config 寄存，无此故障面 |
| F4 | 独立工具配置页 | 无失效 | 08e 三版同 blob、dialog.html 三版均挂载；定义（CONFIG_SCHEMA）→ GET 回读（config_store.py L203）→ 渲染全链通。注：main 版 tool_config.py 缺 old 布尔严格解析 13 行（见 R2） |
| F5 | yuanbao 识别 | bus 独有修复，old/main 无 | bus def.yaml：yuanbao filePaste:false（Quill 输入框不收 paste，图片改结果直返，2026-11-12 A 批）+ qwen 档案修正 29 行（convIdUrl /c/ 等）；old 无此两块。移交 R1-1《bus→old 余量清单》 |

现役失效 0 / 五重点 5：4 项全链健康、1 项改判未实现（F1）、1 项跨线缺额（F5，属 R1-1 范围）。真实风险集中在合流面：

## 三、合流风险清单（八跳取证的直接产出）

- R1 两套缓存与 POST 语义并存：08i（old/bus 204 行 draft 链 vs main 135 行 v3 cache）+ config_route（old/bus 草稿重放整集 vs main D2 按档案 id 合并 + C-3a 寄存）。D2 的后端按档案 id 合并只在 main——old/bus 的 POST 仍是整集替换，多页面互冲（A 改 glm、B 改 deepseek，后提交者冲掉前者）在 old/bus 仍存在，siteKey 草稿隔离只缓解未除根。合流必迁 D2。
- R2 main 缺布尔严格解析：old tool_config.py 13 行（字符串 false→False 兜底，防文本化/草稿回流把关闭误存成开启）；main 无 draft 回流路径故未触发，合并 old 版即消除。
- R3 def.yaml 三版三态：old 903 行（含 12 个 awade 系工具 enabled:false）/ bus 929 行（+qwen 修正、yuanbao filePaste）/ main 507 行（最薄）。合并须按段重放，禁整文件覆盖。
- R4 08k 双源：old/main 同源（9e99c37 建）与 bus e9054f2 平行自研，同职责两实现。

## 四、取证锚核验（任务书四锚）

e57260a / 3235111 / b110f13 / 9e99c37：old 与 main 双仓 merge-base --is-ancestor 全部 exit 0（可达性实证）；bus 独立根四笔 rev-parse --verify 均不存在。任务书断言「old、main 有，bus 一个都没有」在提交图层面成立。内容级补充：bus 经平行笔持有同等修复，blob 级 old=bus 即证：

| v3 锚（old/main 可达） | bus 平行笔 | blob 证据 |
|---|---|---|
| e57260a v3 cache + per-site overwrite | 4e9a457 + 9057e74 + 9c5709c | 08i / config_route / draft_store old=bus |
| 3235111 public diff/restore across UI | 180f90b | 08i / 08m old=bus |
| b110f13 no-diff badges | dbec2bc 徽标批量还原 | 08m old=bus |
| 9e99c37 draft writes track all blocks | cc6fe3d + 9c5709c | 08i / 08j 链 |

## 五、D2 根因（多页面配置隔离）

- v2 缺陷（docs/config-isolation-and-cache-design.md L26/L44）：POST /config 的 profiles 整集替换，A 页改 glm、B 页改 deepseek，后提交者整集快照冲掉前者；时间戳整集粒度判不出单站冲突。
- v3 决策 D2（同文档 L134）：公共配置整份提交；站点配置只提交当前档案 id，后端由整集替换改按档案 id 合并。main 已落地（config_route.py _apply_profiles_section / 寄存通道实证）。
- old/bus：siteKey 草稿隔离 + 白名单比对缓解，POST 语义未迁 D2（见 R1）。

## 六、反查夹具

- 既有：old=bus 侧 test_config_draft（dcb0e15）/ test_config_draft_isolation（74461e5）/ test_config_badge_restore（8f216b7），main 均无（对应其无 draft 链）；main+bus 侧 test_config_diff_noise（aed612e 批）。
- 建议（不落本片）：F1 立项时三件套（CONFIG_SCHEMA 条目 + tools.py 出口截断 + 断言夹具）；R2 直搬 old 布尔解析并补 false 字符串→False 用例。

## 七、分母与查证限度

- 分母：八跳 × 三版本 24 单元格，blob 级取证 22/24（08j 行级差、08k 的 main 后续演化两格为模式级：分叉提交已钉、未逐行比对）；五重点 5/5 定论；四锚 4/4 提交图实证 + bus 平行对照 4/4。
- 限度：① main 08i 135 行未逐行审（D3 全量缓存的浏览器侧存储位置未定位，00_data.js 无 localStorage 标记）；② old 12 个 awade 系禁用工具为区段级定性（样例 awade_control / awade_extract_ts 已核，未全列 12 名）；③ bus 仓无 runtime.yaml（任务书「运行时配置含凭证不碰」不受影响）。
- 挂起：prompt_sections.py L92（任务书原挂起，不并入）；G-B 顺延不自行处理。本片零代码改动，不碰 b/c 范围、基线门、STATUS。