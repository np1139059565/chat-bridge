# G-B/G-C 验收面三缺口逐项判据清单

> 用途：按 docs/00-STATUS.md 复核块，为配置刷新、yuanbao 识别、独立工具配置页三缺口定义判据、取证路径与 pass/fail 分母栏，供分发方按规格第七节逐项脚本化复核。本附录只定义怎么验、去哪取证，不替分发方判定 pass/fail，不改结论源 0%（0/3）的数值。

## 一、口径与分母

- 结论源 docs/00-STATUS.md L6 与 L38：配置刷新 / yuanbao 识别 / 独立工具配置页 0/3 缺口并入 G-B / G-C 验收面；L60 写明收口后按规格第七节逐项脚本化复核，产出 pass/fail 分母与缺口清单。
- 上位口径：docs/split-mirror-and-tools-service.md 第七节阶段 2 五项（L275-285，验收为网页 AI 全流程可用、行为与改造前一致）；docs/work-ai-c.md L597 的 G-C 任务书把 yuanbao 识别与独立工具配置页并入缺口面。
- 本附录分母：三缺口 3/3 逐项成行；每行含判据、取证路径、pass/fail 分母栏三列，列齐 3/3。pass/fail 栏留空由分发方逐项脚本化复核填写，本附录不预填结论。
- 自带实测分母：取证路径在 origin/main 树实存核验 16/18 命中，2 处 MISSING 如实登记在第三节，不编造路径。

## 二、逐项判据表（3 行，3/3）

| 序号 | 缺口 | 判据（怎么验） | 取证路径（main 实存） | pass/fail 分母栏 |
|---|---|---|---|---|
| 1 | 配置刷新 | 设置页改值后草稿态即时生效、点覆盖后回写母版、重启仍按新值生效；逐跳留痕：草稿落盘、apply 灌运行时内存、GET 回读、commit 回写 yaml 母版；与 P1 工具结果体积上限即时值同源判定。 | extend/dialog/parts/08j_config_actions.js、08i_config_cache.js、00a_api.js；flask_server/routes/config_route.py、core/config_file.py | 待分发方填：__ / __ |
| 2 | yuanbao 识别 | 站点识别把 yuanbao.tencent.com 映射到正确档案，不串成 glm；刷新初期 siteKey 为空时不落 unknown-site 桶；同 host 多 URL 与 www 子域按现有站点键口径隔离；客户端注册信息取回与该档案一致。 | extend/dialog/parts/00_data.js、01_backend.js、01b_bridge.js、08g_site_profiles.js、05k_log_message.js、07_render.js；flask_server/routes/clients.py、core/client_registry.py | 待分发方填：__ / __ |
| 3 | 独立工具配置页 | 工具配置区块独立渲染与折叠；CONFIG_SCHEMA 声明到控件、草稿、写盘、GET 回读整链可核；limits.max_json_chars 改值后实际工具出口按新值受限；系统级与工具级分区不互污。 | extend/dialog/parts/08e_toolconf.js、08_settings.js、08i_config_cache.js、08j_config_actions.js、08k_config_blocks.js；flask_server/core/tool_config.py、routes/config_route.py、tools/tool_meta.py | 待分发方填：__ / __ |

每行判据取数锚点统一为 origin/main 当前尖端；冻结树侧（old 1e80680、bus 32e83dd）如需对拍，由分发方按冻结引用另行解析，本附录不预写。

## 三、口径差与外部材料（如实登记）

1. flask_server/tools/tool_config.py 与 flask_server/config_draft_store.py 在 origin/main 树 MISSING：前者出现在 a 方 P2 派单的 CONFIG_SCHEMA 描述里，属冻结树或当时描述；main 真实落点为 flask_server/core/tool_config.py（CONFIG_SCHEMA L24 起）。附录第二节只写 main 实存路径，避免引用不存在文件。
2. 随回传附的 10 个页面链接解析服务全部失败，站点集属 a 的 P2 配置跨站现场样本范围（a.com / b.com / new.com / kimi.com 与 www.kimi.com / 127.0.0.1:5000 / qianwen.com / chat.deepseek.com / yuanbao.tencent.com / hf-mirror.com），与 c 本笔判据清单无关，不据此推断任何页面事实。本附录取证路径只写工程内相对路径与结论源文档，不依赖外部页面解析。
3. 三缺口当前结论源仍为 0/3；本附录交的是判据与分母栏，不等于缺口已补齐或验收通过。

## 四、复核结论

- 三缺口 3/3 行判据、取证路径、pass/fail 分母栏齐备，逐项可核。
- 判据行 3/3、每行三列 3/3、取证路径实存核验 16/18（2 处 MISSING 已登记）。
- docs/00-STATUS.md 的 0%（0/3）保持不变；pass/fail 分母栏由分发方按规格第七节逐项脚本化复核后填写，本附录不代勾、不代判。
