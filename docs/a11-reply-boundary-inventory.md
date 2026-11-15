# A-11 reply 段边界反查与 C-9 / C-14 状态标注对拍报告

> 性质：只读取证报告（零代码改动）。逐项核对 adapter.reply 的返回形状与边界语义，
> 并与 C-9 边界契约、C-14 签名总表的 reply 段标注逐行对拍；登记「文档标注 vs 代码实况」
> 差异（若有）仅供分发方复核输入。不实装执行下游、不装配运行时 M、不注册钩子、
> 不建切换开关、不新增运行期探测分支、不切活链、不摘除任何旧标记、不翻任何 STATUS、
> 不改 S1-S4 判态、不预设下一实装面与下发时点。
> 基点：origin/main e87642d（dispatcher-20261115T203520-749f39 任务书提交本身；
> 开工前 fetch --prune 后核对本地 work/ai-a 与其一致、工作区 clean；
> A-10 交付 c227999 经 merge-base --is-ancestor rc=0 实测在其祖先链）。
> 圈定依据：dispatcher-20261115T203520-749f39——六段余面中仅 reply 单段，
> 不扩 restore、不扩其它四段、不扩九步余面。

## 一、取证范围与方法

- 代码对象：extend/lib/standard_chain_adapter.js 的 reply 段（模块内唯一定义，
  'function reply(' 全文恰 1 次）。
- 文档对象：C-9 extend/lib/standard_chain_boundary_contract.md（第一节第 4 段
  reply(msg) 边界表 + 第二节逐段状态标注 reply 行）、
  C-14 extend/lib/standard_chain_c14_signature_table.md（第二节 adapter 表 reply 行 +
  第六节 B-12 只追加登记）。
- 方法：夹具只读 require 已合入 adapter / contract 两个 lib；契约 .md 与活链文件
  按字符码 10 切行、普通 indexOf / split 反查；零反斜杠零正则、无 fs 写 / shell / 网络。
- 运行期取证：extend/ 全目录（.js / .html）扫 '.reply(' 与
  'AIMirrorStandardChainAdapter.reply' 调用方；git grep 佐证 standardToolMessage 与
  adapter.reply 的命中分布。

## 二、代码实况：adapter.reply 逐项钉死

源码定义（standard_chain_adapter.js，全仓唯一定义，逐字引用）：

    function reply(msg) { return { by: KEY, role: 'tool', tool_call_id: (msg && msg.tool_call_id) || null, status: STATUS }; }

其中模块级常量 STATUS = 'declared-placeholder'、KEY = 'tool_call.id'（导出面同值实测）。

八项实测（test_standard_chain_a11_reply_boundary.test.js 逐条断言）：

1. **返回形状恰四键**：by / role / tool_call_id / status，无第五键；
   by 恒 'tool_call.id'，status 恒 'declared-placeholder'。
2. **role 硬编码常量**：入参 role 取 assistant / user / function / 空串 / 42 / null，
   输出 role 恒 'tool'，不回显入参 role。
3. **content 不回显**：带 content 的完整三键入参，返回对象无 content 键。
4. **缺键归一 null**：null / undefined / {} / { role: 'tool' } 四类残缺入参，
   tool_call_id 一律 null，返回深等于扁平形状
   { by: 'tool_call.id', role: 'tool', tool_call_id: null, status: 'declared-placeholder' }。
5. **不抛错**：非对象入参（字符串 / 42 / true / 数组）doesNotThrow，tool_call_id 归一 null。
6. **幂等且每次新对象**：同参两次调用返回深相等的两个新对象，不共享引用。
7. **导出面共存**：reply 在六段导出内；EXECUTE_STATUS = 'implemented-S2-step5'
   独立导出，execute 段实装不触及 reply 段，模块 STATUS 不变。
8. **运行期零调用方**：06_execute.js / 05f_parse.js / 00_data.js / 05g_cards.js /
   dialog.html 五处活链文本均无 '.reply('；dialog.html 装载 standard_chain_adapter.js
   （lib 区末尾）但未装配任何 reply 下游。

## 三、C-9 边界契约对拍（第一节第 4 段 + 第二节状态行）

| 对拍项 | C-9 标注 | 代码实况 | 结论 |
| --- | --- | --- | --- |
| 缺 tool_call_id（null / {} / { role: 'tool' }） | tool_call_id: null、role: 'tool' | 实测一致（第 4 项） | 一致 |
| role 非 tool（assistant 入参示例） | role 仍 'tool'、强制归一、不回显不抛错 | 实测一致（第 2 项） | 一致 |
| 完整三键入参 | role / tool_call_id 回显、content 不在返回形状 | 实测一致（第 1、3 项） | 一致 |
| 说明行「role 是硬编码常量」 | 在文（第一节第 4 段说明） | 在码（函数体字面量 'tool'） | 一致 |
| 第二节状态行 reply | declared-placeholder / tool_call.id + tool 三键 / n/a / 否 | STATUS、KEY 实测一致；无执行下游 | 一致 |

零差异：第一节第 4 段表格三行与第二节 reply 行逐格与实仓一致。

## 四、C-14 签名总表对拍（第二节 reply 行 + 第六节 B-12 只追加登记）

- 第二节 adapter 表 reply 行「reply(msg) | standard_chain_adapter.js |
  返回 by=KEY、role=tool、tool_call_id、status=STATUS | 一致 | declared-placeholder」
  逐格对拍：by=KEY ✓、role=tool ✓（硬编码）、tool_call_id ✓（缺键归一）、
  status=STATUS ✓（'declared-placeholder'）——「一致」判定经本片实测复核成立。
- 第六节 B-12 只追加登记：只涉 execute 段（EXECUTE_STATUS / 执行权迁移 / 装载行 /
  新增夹具），全节无 reply 字样——reply 段不受 B-12 影响、STATUS 不翻面——一致。
- 交叉引用：C-14 第一节 G2 唯一键（tool_call.id 与三键、不含消息指纹）与
  contract 侧 standardToolMessage 实测三键输出一致（见第五节）。

## 五、运行期下游取证（reply 段纯声明、零装配）

- extend/ 全目录 '.reply(' / 'AIMirrorStandardChainAdapter.reply' 调用方扫描：0 命中。
  06_execute.js 文内 reply 字样仅为卡片级 noReply / mustReply 标志与自动回传注释，
  与 adapter.reply 无调用关系；其 B-12 委托面是 adapter.execute（执行权），不涉 reply。
- tool 消息运行期唯一产出面：standard_chain_contract.js 的 standardToolMessage，
  实测返回恰三键 role / tool_call_id / content、无 msgId 键（不含消息指纹）；
  adapter.reply 只声明键位，与 C-9 第一节第 4 段说明一致。
- git grep 佐证（基点 e87642d 工作树，-l 文件清单）：standardToolMessage 21 文件命中
  （extend/lib 6 + docs 2 + flask_server/tests/js 13）；adapter.reply 4 文件命中且全部为
  文档（boundary_contract.md / field_matrix.md / docs/bus/dispatcher.md /
  docs/c15-s2-remaining-surface-inventory.md），代码零命中——文档标注面与运行期零装配实况相符。

## 六、差异登记与结论

- 「文档标注 vs 代码实况」差异登记：**零差异**。C-9 第一节第 4 段三行 + 第二节状态行、
  C-14 第二节 reply 行 + 第六节（不涉 reply）逐项与实仓一致；STATUS 恒
  declared-placeholder、KEY 恒 tool_call.id、唯一键与 tool 消息三键不含消息指纹全部实测钉死。
- S1-S4 判态不变（以 dispatcher 19:45 / 20:31 判态为准）：S2 第 5 步单点已闭合、
  整体未齐备 / 待对拍；S4 旧标记摘除三项硬前置仍未全满足，阶段 3 不进入摘除步。
- 本片仅为分发方复核输入：不代拍板、不改判态、不自行圈定下一实装面、不预设下发时点。

## 七、边界与只追加记录

- 交付三件（独立命名）：本报告 docs/a11-reply-boundary-inventory.md（新增）、
  flask_server/tests/js/test_standard_chain_a11_reply_boundary.test.js（新增，8 用例）、
  docs/work-ai-a.md 只追加完成记录；不碰 C-15 报告 / C-15 夹具 / B-12 实装面 / B-8 / B-9 先例文件。
- 零代码改动：不改任何已合入 .py / .js / .html / .md 源码本体；新增被测 JS 源 0
  （夹具只读 require 已合入 adapter / contract，二者已在覆盖率报告内，不引入新分母）。
- 夹具沿用 C-14 / C-15 形态：零反斜杠零正则、按字符码 10 切行、普通 indexOf / split、
  无 fs 写 / shell / 网络；不改 hooks / 90-70 阈值 / js_coverage_baseline.json、
  不用 --update-baseline；本机 node v24 覆盖率报告前缀差异不作达标依据，
  分发方环境直跑为准。
- docs 只追加：不动 docs/bus 他人消息；交付回执由 send report 追加到 docs/bus/a.md。
- 提交：基于实时 origin/main e87642d 新建提交、未 amend 已合入历史、一次提交收口、
  正常跑钩子不用 --no-verify、force-with-lease 更新 origin/work/ai-a；
  send report 回提交 hash 与实测；验收以分支提交为准。
