# 代码评审 8 项核验报告（2026-11-09）

> 用途：此前代码评审遗留 8 项待验证问题的逐项核验结论与后续动作登记。
> 核验方式：逐文件读码比对（06_execute / 00e_computed / 05f_parse / 08i / 08j / 08k / 00a / 00c / 01_backend / 00_state / 03_bridge / background.js，及 docs 目录全清单）。
> 注意：本文件为独立落档；pending-tasks.md 待处理区尚未登记指针行，待补。

## 一、总判定

| # | 问题 | 判定 | 说明 |
|---|---|---|---|
| 1 | 06_execute postCardResult 注释矛盾 | ⚠️ 改了一半 | 矛盾注释对仍在，修法见待修 1 |
| 2 | sessionEntries 逐条实时 parseExternalCall | ❌ 未修复 | 现成低成本修法未做，见待修 2 |
| 3 | resolveSelectorExpr 任意 JS 求值 | ❌ 未改动 | 语境变重（档案真源迁后端），需文档声明，见待修 3 |
| 4 | mergeIntoShape 启发式误并 | ✅ 风险降级，可接受 | 提交链走精确回放，启发式只影响预览显示 |
| 5 | token 兜底仅 localhost | ✅ 问题消失 | v3 整体移除客户端鉴权；隐性放宽需文档声明 |
| 6 | 限流触发静默 | ✅ 被架构消除 | 三类风暴源逐一拆除，属消除需求而非打补丁 |
| 7 | background 探测悬挂 fetch | ✅ 已解决 | 探测职责迁入抽屉侧 discoverFlask，init 单次执行 |
| 8 | devtools 告警 5s 重复弹 | ✅ 已解决 | 08i 重写为纯函数库，告警宿主随旧代码删除 |

小结：4 项解决、1 项降级、3 项待修。耦合面未变差且系统性收紧：08i（纯函数）← 08j（动作）← 00a（拦截）三层单向依赖、文件头显式声明；00_state 的 reprobe 用存在性守卫与 04_observer 松耦合。

## 二、已结 5 项（结论留档，不再跟踪）

### ④ mergeIntoShape 启发式（降级为可接受）

函数一字未动、「多数键命中」启发式保留。缓解因素：08j 的 applyConfigOverwrite 提交时按 pending 记录的精确 path + body 逐条回放（seq 排序、__commit 绕过拦截），不经过启发式。启发式只影响 GET 预览合并的显示正确性，不影响提交数据完整性。

### ⑤ token 兜底（功能移除，问题消失）

apiFetch（00a）是全扩展唯一请求辅助，不拼任何 Authorization 头；01_backend 全部请求走它，discoverFlask 探测也是裸 fetch。v3 整个客户端鉴权已移除。对「后端只听 127.0.0.1、抽屉是唯一稳定通道」的现状是合理收缩，但属隐性放宽：后端若改绑局域网，现在零防护。使用前提需写入文档（见待修 3）。

### ⑥ 限流静默（被架构消除）

原限流模块不存在，其防的三类风暴源在 v3 里逐一被拆除：

1. 外部卡片轮询改面板可见性驱动（01_backend 注释明确「不在此启动，见 setPanelVisible」）；
2. 回传改串行队列（00c：800/1800ms 类型化间隔 + 15s 看门狗自愈 + 异常不复位修复 + Proxy 剥壳）；
3. 内容脚本日志改缓冲 + 批量补发（pendingExtLogs / flushPendingExtLogs）。

这是消除需求而非打补丁。注意：未来若新增高频调用方，没有现成限流件可复用，需重建。

### ⑦ background 探测（职责迁移）

探测职责从 background 迁入抽屉侧 discoverFlask（init 单次执行）：候选 = 上次探通地址 → 当前连通地址 → 端口输入框构造地址，不再附带写死的候选端口（顺带修掉「改端口后仍被旧端口悄悄接住」的老毛病），探通地址落盘 chrome.storage。原「外层 30s 超时、inner fetch 悬挂」场景不复存在，功能无丢失。

### ⑧ devtools 告警（随 v3 重构消失）

08i 已从行为模块重写为 v3 纯函数库（configCacheGet/Set、configFieldToText、profileFieldDiff、configPublicToBody），草稿拦截迁 00a、动作层在 08j。四个嫌疑文件（08i/08j/00a/00c）全部核查，无任何定时器轮询告警。原 5s 重复弹告警的宿主行为随旧代码删除，问题不再成立。

## 三、待修 3 项

### 1. 06_execute.js postCardResult 矛盾注释对（小）

postCardResult 内部两段同主题注释紧邻且结论相反：第一段「指令来源一律跳过（结果仍留在卡片上）」，第二段「只拦异常、正常结果一律放行——/rr 重跑、/sa on 带起的卡片本就该给 AI 看」。实现取后者。本轮修复在 executeCard 的 _cmdTriggered 注释、JSDoc、三处 docs/command-tool-isolation.md 引用（文件存在，引用不悬空）上都下了功夫，唯独没删矛盾对——补了新墙没拆旧墙。

修法：删第一段，保留与实现一致的第二段。

### 2. sessionEntries 逐条实时 parseExternalCall（小，收益最明确）

00e_computed.js 的 sessionEntries 对每个条目实时调用 !!(self.parseExternalCall && self.parseExternalCall(node))；05f_parse.js 的 parseExternalCall 为纯函数、逐块 charAt(0)==='{' 后 JSON.parse，无缓存、不读节点字段。长会话流式期间树持续变动，computed 反复全量解析。

修法（照同文件现成范式）：05f_parse.js 里 msgSource 的注释明写「建节点时算一次、存到节点上，之后所有地方读字段即可」——isExternalCall 照抄即可，建节点时算一次存字段。约 10 行。

### 3. resolveSelectorExpr 能力边界无文档声明（文档活）

dom-utils.js 的 new Function 未改（当时建议即文档级声明）。站点档案真源迁后端后（00_state 的 applyProfiles 整体替换 PROFILES），regenerateExpr / retrySendExpr 等完整 IIFE 表达式字段经 08g 可视化编辑 UI 供给，「表达式即任意 JS」的面比本地配置时代更宽。applyProfiles 清洗扎实（id 正则、逐字段类型校验、hosts 规整），但字符串表达式字段原样放行。docs/ 下 26 个文件无对应声明。

落点与内容：development-guide.md（或 api-reference.md）声明「档案表达式字段＝可执行任意 JS，等同指令表达式能力，仅限本机受信配置」；顺带写明⑤的「后端仅限本机、无鉴权」使用前提。

## 四、编辑残留 3 处（顺带发现，无功能影响）

| 文件 | 问题 |
|---|---|
| 03_bridge.js | pasteToWebpageAI 新旧两份 JSDoc 并存（旧的单参数版未删）；waitSendReady 前 /** /** 双开头笔误 |
| 05f_parse.js | _stripNumberLines 前挂孤儿 JSDoc（实为 _stripLineNumbers 的重复描述） |
| 00c_sendqueue.js | files 分支同一句注释连写两遍 |

## 五、建议动作（按性价比排序）

1. 待修 2：照 msgSource 范式落 isExternalCall 字段——约 10 行，收益最明确；
2. 待修 1：删 postCardResult 矛盾注释对，保留与实现一致的那段；
3. 待修 3：development-guide 声明表达式字段能力边界 + README 写明「后端仅限本机、无鉴权」前提；
4. 编辑残留：3 处批量清一轮。

优先级：P2。均为小活/文档活，按 pending-tasks.md 的伴随式原则穿插在批 5（任务 A / 任务 B / P0 闸债清偿）间隙处理，不占独立排期。

## 六、一句话结论

这轮改动的重心是 v3 架构重构，清单上 5 项问题被重构顺带解决或消除，解得比原建议更彻底；但清单里明确给出低成本修法的两项（①②）恰恰没做，属于「大工程做完了，顺手活漏了」——补上即可收口。
