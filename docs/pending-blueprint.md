# 进行中的施工蓝图

> 从 `docs/pending-tasks.md` 迁出的批次级实施蓝图，含具体锚点与步骤。
> 施工时直接照此执行。

## 批 5 准备（2026-11-08 收尾登记：下次开工直接照此执行，无需重新取证）

### 任务 A：② 采集/定位字段支持 JS 表达式（主世界求值 + DOM 标记桥接；阶段 1 = 试运行链路）

根因回顾：
- 点击类字段已支持任意 JS 表达式：06_picker.js testProfileField L344-352 click 分支 → A.execClick（L216 起）→ injected_clipboard.js 主世界 new Function 求值（L69），不受扩展 CSP 限制。
- 采集/定位类不支持：locate 分支 L353-383 只做逐行 document.querySelectorAll，完整表达式在 L354 被整体拒绝（提示改走点击测试）。根因 = 隔离世界 CSP 禁 new Function（06_picker.js L197-199、injected_clipboard.js L7-11 注释）。

实施步骤（按序执行，完成后走全闸）：
1. extend/content/injected_clipboard.js：在 click 处理器（L56-93，协议 {source:'ai-mirror-exec', type:'click', reqId, expr, mode}）旁新增 type:'locate' 分支——求值口径同 L69 → collectElements（L43-48）规整 → 命中元素逐个 setAttribute('data-aim-mark', reqId)（先清同 reqId 旧标记）→ 回传 {source:'ai-mirror-exec', type:'locate_result', reqId, ok, reason, count, error}，reason 沿用 invalid / not_found 口径。
2. extend/content/06_picker.js：仿 execClick（含 _execPending 登记与 EXEC_TIMEOUT=3000 看门狗）新增 A.execLocate(expr, onResult)——发 {type:'locate', reqId, expr}；收到 locate_result 后在隔离世界按标记属性（data-aim-mark=本轮 reqId）querySelectorAll 取回元素（DOM 两世界共享，标记可读）；回调 (ok, reason, count, firstEl)；读完即移除标记；超时看门狗同口径。
3. testProfileField locate 分支改造（L353-383）：逐行判定——行内含 document. 或 querySelector（口径同 L344）则该行走 A.execLocate（多行串行，逐行计入 hit/miss，首个命中参与高亮）；纯选择器行保持现行 querySelectorAll 路径不动；删除 L354 的整体拒绝。
4. extend/dialog/parts/08g_site_profiles.js：采集/定位类字段 placeholder 由「每行一条选择器」改为「每行一条选择器，可写完整 JS 表达式」（L196 点击类提示保持）；PROFILE_FIELD_META 相应注释同步。
5. 测试：新增 flask_server/tests/js/test_picker_locate.test.js（node vm + 假 window/document/postMessage 模拟主世界回执与标记读写；断言：表达式行命中统计、标记写入与清理、看门狗超时、纯选择器行不受影响）。
6. definition.yaml 与后端 sanitize_profiles：确认表达式字段（含括号/引号/点号）不被长度与字符校验拦截；definition 内字段提示文案同步「支持完整 JS 表达式」。

阶段 2（消费端，改动面大，单独立项再评估，勿混入下轮）：02_blocks.js extractBlocks / makeAssistant（L216-280）以同步 querySelectorAll 消费 P.item 等字段；表达式求值必须经主世界（异步 postMessage 桥接）→ 需把「档案表达式字段解析」前置为异步标记刷新步骤（或 profile 应用时在主世界预解析），observer 巡检链路需 async 化，牵连 04_observer 与 sendPage，先出设计再动手。

### 任务 B（批 4 实机新增问题 4）：GLM 自动执行「粘贴后不回车」
> **批4·k 状态更新（2026-11-09 凌晨）**：推送批4·j 时远端又进 7bf1c3f「fix(content): 富文本编辑器输入框改走 paste 事件」——输入框写入从「原生 value setter + input 事件」（批4·d 取证事实，上文「实现事实」中该项据此过时）改为派发 ClipboardEvent paste。若 GLM 输入框实为富文本编辑器，原生 setter 本就写不进或框架不认——这正是「粘贴后不回车」的最大嫌疑根因，且疑似已被该修复覆盖。现盘复核：写入方式已换：现盘 03_bridge 已含 ClipboardEvent（paste 事件路径），原生 setter 仍并存（迁移未彻底或双路径）。
> **开工顺序调整（覆盖原「下轮首步」）**：先实机验证 7bf1c3f 效果——重载扩展 → 触发一次卡片执行回传，观察粘贴后是否自动发送；若已修复，任务 B 直接关闭，登记验证结果即可；若仍复现，再按原蓝图实机取证定案（控制台三类日志 + 现场截图）与修复方向②（回车落空自检兜底）。
> **锚点提醒**：03_bridge.js 因 7bf1c3f 行号再漂移，回传链定位一律以函数名 grep 为准（writeInputValue / pasteToWebpageAI / waitSendReady / pressEnter），行号仅参考。
> **批4·l 证据更正（2026-11-09，7bf1c3f diff 细读后；上条「疑似已被覆盖」与「现盘复核…迁移未彻底」两表述作废）**：①7bf1c3f 修复对象是千问（Slate）与元宝（Quill）的 contenteditable 编辑器——原症状「setter 抛 Illegal invocation、框里没字、根本没办法输入」；GLM 输入框是 textarea（inputSelector＝「#search-input-box textarea, textarea.scroll-display-none」，isRichEditor 判 false），走原生 setter 分支，该分支 7bf1c3f 仅加 try/catch 兜底（GLM setter 从不抛错，兜底不触发），行为零变化。②用户症状「文本已粘贴进框、仅不发送」与该修复症状不同类——任务 B 未被 7bf1c3f 覆盖；上条「先验证 7bf1c3f、已修复则关闭」顺序作废，恢复原蓝图：实机复现取证定案（控制台三类留痕+现场截图）→ 修复方向②（回车落空自检兜底）首选。③批4·d 实现事实「原生 setter 写入」对 GLM（textarea）仍成立，上条「据此过时」范围收窄为仅富文本站点（现走 paste）。④上条「现盘复核」的「仍并存（迁移未彻底或双路径）」系检测口径误判：ClipboardEvent 在 03_bridge 本就用于附件粘贴，现为按输入框类型分流的既定设计（新增 03c_rich_editor.js：isRichEditor/writeRichEditor/clearRichEditor）。⑤方向② 的「查输入框 value」判据仅对 textarea（GLM）有效，富文本站点需另行判据（参考 03c 的 isRichEditor / clearRichEditor）。



症状：自动回传链路（卡片 auto_send → 05_index.js L84 → A.pasteToWebpageAI）在 GLM 页面经常完成粘贴但发送未触发，间歇复现 → 工具结果停在输入框、GLM 收不到 [TOOL_RESULT]、整条工具调用链中断。

本轮只读取证锚点与实现事实（2026-11-08）：
- pasteToWebpageAI 定义：extend/content/03_bridge.js L184；waitSendReady 定义：extend/content/03_bridge.js L233。
- 实现事实：粘贴用 insertText=无；派发 Enter=有；KeyboardEvent=有；调用 waitSendReady=有；引用 sendButton=有。
- GLM 档案（00_state.js L99-L136）：inputSelector=有（#search-input-box textarea, textarea.scroll-display-none）；sendButton=未配置；sendButtonDisabledMark=未配置（该标记仅 DeepSeek 配置，见 00_state.js L199-202 注释——其他站点不配则 waitSendReady 跳过禁用检查）。

批4·e 证据更新（取证回读，2026-11-08）——三项新事实，已据此修订下方假设与修复方向：
- ① 秒放行实锤：GLM 档案未配置 sendButton → waitSendReady（03_bridge.js L236-237，if (!sel) { done(); return; }）直接放行，连按钮存在性都不检查，回车前唯一缓冲 = pasteToWebpageAI L208 的 500ms 固定延时；原「跳过禁用检查」的表述低估了问题。
- ② 历史死锁关联：00_state.js L127-135 注释记录 2026-11-08 修复的死锁——粘贴多行文本 → 输入区变高触发 .enter.is-main-chat.m-three-row → 误判生成中 → 回车挂起 → 文本滞留 → 持续误判；修复手段 generatingRequireEmptyInput=true（生成中输入框必为空）。当前症状疑为该链残留或姊妹形态，重点排查守卫二挂起与冲刷链路。
- ③ 挂起/冲刷与第二条实现：守卫二（03_bridge.js L213-216）回车前查 isGenerating，命中转 enter_only 挂起；03_bridge.js L345/L348 另有 waitSendReady 引用（批4·f 已证＝附件粘贴流程自身的就绪等待，非冲刷；真正的冲刷在 03b_paste.js）；03b_paste.js L81/L90 另有 pasteToWebpageAI 与 Enter 引用（批4·f 已证＝挂起冲刷模块：L81 冲刷时重放文本粘贴、L90 为 enter_only 补回车）。粘贴写入方式已实锤为原生 value setter + dispatchEvent(input)（03_bridge.js L170-172 writeInputValue）——原假设「粘贴未触发 input 事件」据此排除。
- 下轮取证补看清单（批4·f 证据落定：代码侧取证至此全部闭环，结论如下）：
  · 冲刷机制实锤（03b_paste.js）：挂起条目由周期定时器冲刷（setInterval，_pasteFlushTimer），无挂起时清除定时器（L70）；仍在生成则继续挂起（L74）；到期（PASTE_SUSPEND_MAX_MS＝120000ms，extend/content/03b_paste.js:24）逐条如实上报失败「回传放弃」（L57-68）；enter_only 冲刷时重取输入框——有值补回车（L86-90），空则报失败（L87-88）。
  · 生成态判定实锤（04_observer.js L236-273）：按 BUTTON_POLL_MS＝500ms，extend/content/00_state.js:381 周期轮询生成选择器；generatingRequireEmptyInput（L254-257）：选择器命中且输入框非空 → 判非生成（即死锁修复本身，与多行粘贴场景直接相克）；守卫读的 state.isGenerating 最多陈旧一个轮询周期。
  · GLM 档案 L127 注释载明「GLM 无独立的发送/停止按钮」——sendButton 未配置的根因；修复方向①实施前必须先实机确认 GLM 是否存在可用 DOM 按钮。
  · 「已尝试」式成功回执：附件流程链路启动即回 auto_send_result ok:true（03_bridge.js L372），不等也不验证实际发送；文本主流程（L184-220）成功路径无任何回执（批4·f 全量清点：ok 1 处 / fail 7 处）→ 卡片成功态另有来源，方向②的「发送后验空」可统一补齐此洞。
  · 剩余唯一未取证项＝实机复现观察（控制台日志与现场状态），已并入下方「下轮首步」。

假设（按可能性排序，待实机证实）：
1. 就绪竞速（最可能，代码路径已实锤）：GLM 未配置 sendButton → waitSendReady 直接 done() 放行、无任何轮询，回车前全部缓冲仅 500ms 固定延时；GLM 前端消化输入超过 500ms 时 Enter 落空，机器/页面繁忙度与文本长度差异造成「经常但不总是」。
2. 守卫二挂起 + 冲刷链（批4·f 后降位为次要候选）：该路径自带完整自愈与如实上报——空闲时定时冲刷、到期报「回传放弃」、冲刷时输入框有值即补回车；结局只有「最终补发成功」或「留下明确失败回执」两种。实机控制台若出现「[回传守卫] 冲刷」或「回传放弃」日志即可锁定此路径；若日志干净而文本滞留，则指向主路径回车落空（假设 1 / isTrusted）。唯一静默滞留形态＝冲刷定时器未运转或 isGenerating 长期陈旧为 true，留实机排除。
3. 合成 Enter 的 isTrusted=false 被 GLM 忽略，或派发目标/焦点不对（粘贴后焦点丢失）。

下轮首步（取证 → 修复）：
- 代码侧取证已闭环（批4·d/e/f 全链路：粘贴→就绪→回车→挂起→冲刷→到期，结论见上方证据块），无需再读代码；
- 实机复现（唯一剩余取证）：触发一次自动回传，盯控制台三类留痕——「[生成态] 翻转」「[回传守卫] 冲刷」「回传放弃」；滞留现场查输入框 value 与页面有无可用发送按钮（成功/失败各截图一次）——据此在假设 1（回车落空）与守卫链之间定案，并直接选定修复方向；
- 修复方向（批4·f 终版排序，首选②，①③④可作组合）：② 回车落空自检兜底（首选）：pressEnter 后 300-500ms 查输入框 value 是否被清空（GLM 发送即清空，04_observer.js L251 注释已背书「生成中输入框必为空（文本已随发送清空）」），未清空重派 Enter（上限 1-2 次、间隔递增）仍失败则如实回 auto_send_result ok:false——一并修掉「已尝试」式假成功；站点差异用档案开关控制，GLM 先行。① GLM 档案补 sendButton + 禁用标记：先实机确认 GLM 有无 DOM 发送按钮（档案 L127 注释称无独立按钮，可行性存疑），有则抓禁用特征（类名 / aria-disabled / disabled 属性，需扩展 waitSendReady L244 判定）。③ 到期强补：PASTE_SUSPEND_MAX_MS 到期先「输入框有值则强制补一次回车」再报失败（现行到期直接放弃，03b_paste.js L57-68）。④ isTrusted 合成事件被 GLM 忽略：仅当实机证明重试也总是无效时升级（改点按钮可绕开，依赖①的按钮存在）。


### 批4·h 合并后核对（2026-11-08 深夜：f4d2ab5 推送被拒，干净 rebase 为 6e6faae 已推送；远端并行工作登记与批 5 锚点校准）

背景：批4·f 推送被拒——远端在 be86914 之后进了并行工作（另一实机调试会话）。本地仅一个纯文档提交，干净 rebase 集成、无冲突（远端只加文档头部千问条目，本地只改文末批 5 准备块）。合并后全文「批 5 准备」计数说明：本块加入后为 5 次＝原有 2 处（状态行引用 1 + 章节标题 1）＋本块自身 3 处引用（背景句、本说明句、锚点校准小节）；批4·h 块本身仅 1 个，不存在块级重复

远端并行提交（be86914..25a30b8）：
- 1c0f8aa fix(debug_chrome): 补千问站点档案，档案热更新同步容器选择器
- f0ecb43 fix(debug_chrome): 修千问历史项选择器非法导致推送整体中断
- f188d61 feat(debug_chrome): 新增腾讯元宝站点档案
- 44f627f fix(debug_chrome): 角色标记支持命中消息项自身（02_blocks.js 改动来源）
- 2942c99 fix(config): site_profiles 改为由档案 hosts 派生，消除双真源漂移（definition.yaml 结构大改，任务 A 步骤 6 的 definition 语境据此更新：site_profiles 不再手写）

对「批 5 准备」的锚点校准（2026-11-08 实测复核；下轮定位一律以函数名/特征文本 grep 为准，行号仅参考）：
1. 任务 A 锚点全部有效——06_picker.js / injected_clipboard.js / 08g_site_profiles.js 远端未改动：
   - 06_picker.js：execClick定义 L216；testProfileField定义 L331；locate整体拒绝行 L354
   - injected_clipboard.js：ai-mirror-exec协议 L37/40/58/60；collectElements L43/77；newFunction求值 L9/69
2. 任务 B 行号漂移（远端改了 03_bridge / 04_observer / 05_index / 00_state / 02_blocks；03b_paste.js 未改）：
   - 03_bridge.js：writeInputValue L175；pasteToWebpageAI定义 L194；waitSendReady调用 L217/355；守卫二 L219；pressEnter调用 L227/365；waitSendReady定义 L243；秒放行if(!sel) L156/247；禁用判定 L248；pressEnter定义 L263；_pasteFilesToWebpageAI L315；守卫四 L358；假成功上报 L382
   - 03b_paste.js（远端未改，原行号仍准）：_suspendPaste L30；_flushPendingPaste L48；PASTE_SUSPEND_MAX_MS L24
   - 00_state.js：glm档案块 L99；generatingRequireEmptyInput L135；BUTTON_POLL_MS L393；qianwen档案 未命中；yuanbao档案 未命中
   - 04_observer.js：startButtonWatch L243；generatingRequireEmptyInput消费 L257/261；翻转日志 L274
   - 05_index.js：pasteToWebpageAI引用 L84
   - 02_blocks.js（阶段 2 注记；44f627f 改的是角色标记判定，不碰主链路）：extractBlocks L268；makeAssistant L202
3. 交叉核对（下轮首查）：远端在文档头部新增「千问站点档案缺失…容器选择器不随档案刷新（P1，根因待修）」条目；但 1c0f8aa 提交信息即「档案热更新同步容器选择器」，且随提交新增 test_apply_profiles_container.test.js（111 行）——修复疑似已落地。本轮实测（批4·i 更正）：首轮取证窗口只截到 applyProfiles 的 L262-307 清洗段，未覆盖其后 L313-327 的刷新段，故误报「未见」——实锤修复已由 1c0f8aa 落地：applyProfiles 末尾按新档案重算 A.state.currentSel、容器选择器变化即 reprobe（远端 diff hunk @@ -313,4 +313,16 @@；现盘 grep 实证 00_state.js L321/L322；配套 test_apply_profiles_container.test.js 111 行回归）。文档头部千问 P1「根因待修」据此过时：勿重复实现，仅剩实机复验

### 批4·j 闸门归因（2026-11-09 凌晨：合并树首次全量闸失败 → 归因远程并行代码；本提交按轻闸+归因豁免放行）

**首次对合并树（6e6faae = 本地批4·f + 远端 1c0f8aa…25a30b8）本地全量闸结果**（mw82nhhz 实测）：
- quality exit 1：新增违规 2 处——skills\debug_chrome\extension\content\01_config.js L74/L75 与 05_tool-handlers.js L317/L318 重复（另有 L73↔L316 为 [已知] 存量）；
- js-tests：# tests 279 / # pass 279 / # fail 0（含远端随提交新增 test_apply_profiles_container 与 test_item_marks_mark 系测试文件，266→279），但红 12 文件，基线外新红 = extend/content/00_state.js、extend/content/02_blocks.js（恰为远端并行会话改动的两文件）；
- pytest 893 全绿（888→893，远端新增 test_config_store 用例）。

**归因结论**：本会话暂存仅 docs/pending-tasks.md，全部失败项所在文件本会话零触碰；quality 另经 stash 实证（暂存收起后在干净 HEAD 复跑，失败一致复现）→ 闸债 100% 来自远端并行合并（1c0f8aa/f0ecb43/f188d61/44f627f/2942c99），非本会话引入；js 项为逻辑归因（.md 不参与覆盖率，红文件零触碰）。

**批 5 首项（P0 闸债，先于任务 A/B 执行）**：
1. 消重复：skills\debug_chrome\extension\content\01_config.js L73/L74/L75 ↔ 05_tool-handlers.js L316/L317/L318 三对（含已知存量 L73↔L316）一并收敛（提取共享常量或改单处引用），修后 quality_rules.py 应回 exit 0；
2. 覆盖率回基线：00_state.js（applyProfiles 的 currentSel/reprobe 新段）、02_blocks.js（itemMatchesMark）——先看 check_js_tests 覆盖明细定位未覆盖行再补测（新函数理应带动覆盖，红＝存在未测路径；勿简单调基线掩盖）；
3. 清偿后再开任务 A（②蓝图施工）与任务 B（GLM 粘贴不回车实机复现定案）。

**本提交口径**：复用批4·d/e 文档轮轻闸判定（本会话新增违规＝0）+ 归因实证豁免；闸债登记在案，批 5 首项清偿。


### 批4·l 收尾补正（2026-11-09 凌晨终轮；本会话到此停手——用户指示暂停实施，代码零变更）

- **任务 B 状态最终定版**（详见任务 B 段内「批4·l 证据更正」）：7bf1c3f 修复的是千问（Slate）/元宝（Quill）contenteditable 编辑器「写不进」问题；GLM 输入框为 textarea，走原生 setter 分支零变化——**任务 B 未被覆盖、维持开放**，批4·k「先验证 7bf1c3f、已修复则关闭」作废；原蓝图（实机复现取证定案）与修复方向②（回车落空自检兜底）恢复首选。附带更正：批4·k「迁移未彻底」为检测口径误判（分流为既定设计）；批4·d「实现事实」过时范围收窄为仅富文本站点。
- 096151c feat(profiles): 讯飞星火站点档案（批4·k 推送被拒 fetch 所得，rebase 集成为 631bf01）：flask_server/config/definition.yaml——未触及 00_state.js，任务 A/B 锚点不受影响。
- 闸债现值复测（本轮探针，相对批4·j 登记）：quality 新增 3 处（出现 2 处：skills\debug_chrome\extension\content\01_config.js L73  skills\debug_；出现 2 处：skills\debug_chrome\extension\content\01_config.js L74  skills\debug_；出现 2 处：skills\debug_chrome\extension\content\01_config.js L75  skills\debug_；L73 对由「已知」转「新增」，两次运行间 skills/scripts 零变更，L73 转新增机制待下轮复核 quality 基线判定逻辑）；js-tests # tests 287 / # pass 287 / # fail 0；红 13 文件（基线外：extend\content\00_state.js、extend\content\02_blocks.js、extend\content\03_bridge.js）；pytest .............................                                            [100%] / 893 passed in 33.70s。P0 清偿范围不变：01_config.js↔05_tool-handlers.js 重复对以实测清单为准全部收敛 + 00_state/02_blocks（含远端新增代码）覆盖率回基线，勿调基线掩盖。
- **开工顺序（终版）**：1) 任务 B 实机复现取证——重载扩展 → 触发一次卡片执行 → 观察粘贴后是否自动发送、控制台三类留痕（[生成态] 翻转 / [回传守卫] 冲刷 / 回传放弃），零代码随时可做；2) P0 闸债清偿；3) 任务 A（②表达式桥接蓝图施工，06_picker/injected_clipboard/08g 未受远端影响，锚点以函数名 grep 为准）；4) 任务 B 按实机结果实施（方向②首选；「查 value」判据仅适用 textarea 站点）。
- 批4·d~l 收尾链全部落档。03_bridge 现锚点（批4·l 实测）：writeInputValue L176、pasteToWebpageAI L210、waitSendReady L259、pressEnter L279；03c_rich_editor：isRichEditor L26、writeRichEditor L43、clearRichEditor L68。

- **超时行为补记（批4·m，2026-11-09 真终轮）**：上上轮工具上报「60 秒超时」时，脚本并未中止——子进程在后台继续执行直至完成：批4·l 双编辑落盘、轻闸通过（提交 3d7acb2 的存在即反证 gate_ok——脚本仅在闸门通过时提交）；后台推送未确认（本轮 fetch 未见同步），由本轮随提交补推。教训三条：①工具超时是上报层超时≠脚本未执行，重跑前必须实测现场（log/status/文档计数），不可假设「未动」——上一轮「拆分第 1/2 轮」判「现场与预期不符」并只读不写，处置正确，避免了重复写入，但其收尾报告「文档编辑已落盘、未提交」有误：实际已由后台进程提交（现 HEAD 3d7acb2，本条一并更正）；②重闸与双套测试须拆分多轮调用（60 秒上报预算）；③任务 B 段内证据更正标题 1 处 + 收尾补正交叉引用 1 处 = 全文原 2 处，加本补记再引用后为 3 处——均非重复事故，勿误判为需清理。
