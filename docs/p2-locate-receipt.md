# P2 配置跨站生效面定位回执登记（2026-11-18 分发方）

> 形态：a 的 P2 定位回执以纯文本正文交付（此前误套 bridge-chat-res 信封致识别失败，已修正）。分发方按「不采信自述、以实仓为准」登记，不代 a 造 patch、不推 work/ai-a、不动 a 侧工作树；a 侧零写入红线不破。交付形态裁定：本登记即分发方侧收件形态。

## 一、回执要点（a 所述，待分发方独立复核）

- apply_to_runtime 单参无 site 维度；磁盘草稿按 site 分桶、生效态仅一份全局 runtime.CONFIG；A 站改 → 全局变 → B 站 GET /config、/profiles 读到 A 值，最终态为最后触碰页面的草稿。
- _config_snapshot 签名无 site、不读 X-Site-Key，/config GET 与 /profiles 全局返回；_site_of 只服务草稿桶路由，站点隔离仅存在于磁盘草稿层。
- tests/test_config_draft.py 两处 apply_to_runtime 断言为源码字符串静态断言，未见「A 站 POST 后 B 站 GET 互不串」的跨站生效态行为断言。

## 二、分发方独立复核（冻结锚 32e83dd，同级交付仓按仓名定位）

| 项 | 分发方实测 | a 检出 | 口径 |
|---|---|---|---|
| config_draft_store.py apply_to_runtime 定义行 | L60 | L60 | 行号漂移如实分列、不调平 |
| GLOBAL_KEY 常量 | 冻结锚检出未见 | 本检出未见 | 待分发方按提交图再核，不预填结论 |
| config_route.py _config_snapshot 定义行 | L未命中 | L164 | 同上 |
| config_route.py _site_of 定义行 | L未命中 | 未给行号 | 仅服务草稿桶，待逐行核 |

## 三、仓库身份核对裁决

a 检出按仓名定位的源工作树与分发方冻结锚 32e83dd 为两套检出/时点：L60 与 L60 行号漂移、GLOBAL_KEY 常量有无之差如实登记，均不自行调平；三项语义结论为结构性成立但按不采信自述仍待分发方逐行复核，不据行号漂移翻旧结论、不预填合入裁定。

## 四、附带发现（超 P2 范围，登记不改）

母版缓存 _MASTER_CACHE 仅 /config/commit 失效；apply_to_runtime 异常吞掉 return False 而调用点不检查返回值；草稿态 profiles 直灌全局且只增不删。三项另立待办，不扩单、不触碰。

## 五、跨工作树视角分列（c 侧）

c 的 26334c0 / 回执 c-20261118T164538-e73c5e / tip 277e23b / ahead 1 behind 100 属另一工作树视角；分发方本仓 tip adc6e5b、c tip 以 ls-remote 为准、docs/r4-test-command-restore-fixes-diff.md 本轮实测见上。两套视角分列，不混、不当成已合入本仓 main。

结论源 docs/00-STATUS.md 各项分母不变；逐笔合入裁定仍 0/23。阶段 3 摘除三项硬前置未齐，STATUS 保持声明态，执行权仍绑旧链。

## 六、独立复核口径更正（本轮实测）（2026-11-18 分发方，以本轮 git 实测为准）

> 触发：457c637 第二、三节按 a 自述预设「行号漂移 / GLOBAL_KEY 有无之差」，本轮冻结锚实测推翻该预设。按「不回改已合入报告、旧版按 commit 查」做法，本节为准，457c637 本体不改。

| 项 | 本轮冻结锚 32e83dd 实测 | a 检出 | 裁决 |
|---|---|---|---|
| config_draft_store.py 行数 | 112 | 未给总数 | — |
| apply_to_runtime 定义行 | L60 | L60 | **一致**，无漂移 |
| GLOBAL_KEY 常量 | 全篇零命中 | 未见 | **一致**，非「有无之差」 |
| config_route.py 直取 | git show 32e83dd:flask_server/config_route.py rc=128、0 行 | 按仓名定位的源工作树可读 | 该锚下取不到，改按 ls-tree 候选路径复核，见下表 |

翻案结论：a 的「仓库身份核对」疑虑（疑与分发方所核非同一提交、约 5 行漂移）在冻结锚下不成立。L65-93 区段与 GLOBAL_KEY L11-14/L76 属分发方早先广播的旧口径，不是 a 与本锚之差；按不采信自述复核，结果为自述成立、旧口径不成立，如实登记、不调平、不翻旧结论。

## 七、config_route 路径复核

本轮按 ls-tree 列出 32e83dd 全树（737 文件），候选路径：['flask_server/routes/config_route.py', 'flask_server/tests/test_config_route.py', 'flask_server/tests/test_voice_route.py', 'flask_server/tests/test_web_route.py']；逐路径取行号结果：flask_server/routes/config_route.py: rc=0 lines=286 snapshot=[164] site_of=[41]；flask_server/tests/test_config_route.py: rc=0 lines=304 snapshot=[] site_of=[]。若候选仍取不到 _config_snapshot / _site_of，则两项行号维持「待按提交树再核」，不编、不据 a 的单仓检出回填。

## 八、跨工作树视角更正

上一轮把 277e23b / 26334c0 判为「另一工作树视角、与本仓分列」说过头：本轮实测 26334c0 在本仓 cat-file -t=commit 可核，277e23b bus(c):[c-20261118T164538-e73c5e] 就在 origin/main，属同一主线。不变的是 docs/r4-test-command-restore-fixes-diff.md 在本仓仍 ABSENT，回执落 main 不等于附录合入。

结论源 docs/00-STATUS.md 各项分母不变；逐笔合入裁定仍 0/23。阶段 3 摘除三项硬前置未齐，STATUS 保持声明态，执行权仍绑旧链。
