# B-6 通道泛化取证与旧路径调用方地图

> 2026-11-13 AI-B 交付（对应 docs/work-ai-b.md 当前任务 B-6）。
> 证据来源：git grep 与文件读取，行号对应工作区基线 6691558。
> 原则：只记录当次代码取证所得；清单标注「待真机确认」的项不因代码存在而改判，一律保留待验证状态。

## 一、三项待办取证结论

| 项 | 清单原标注 | 代码证据 | 本次结论 |
|---|---|---|---|
| G10 消息顺序疑似乱序 | 待查（缺证据） | push_pipeline.py:247-260：同批含文本与媒体时先 send_text（:249）后 push_media（:260）；:121-122 after_push 在锁外补推语音 | 清单两条结构性猜测属实。切片顺序是否等于真实时序仍未验证、无时序日志，维持待查 |
| G11 卡片执行状态异常 | 已解决（待核实代码） | 幽灵卡判据 cardMatchesBySig（extend/dialog/parts/05j_card_sig.js）只按工具名+参数比对，注释明确不掺消息指纹；入池硬门槛 isTreeTail=会话树末条（extend/dialog/parts/05l_autoexec.js）；状态文件原子写 bridge_store.py:256-270 | 三处修复均已落地。另发现跨刷新恢复键构型遗留，见本文第四节 |
| G12 企业微信推送重复 | 已改，待验证 | bridge_store.py:270 os.replace 原子替换，:256 注释点名 os._exit(0) 强退场景；会话键 UUID 型（command_dispatch.py:242） | 修复在代码；重启后首条的真机验证未做，维持待验证 |

## 二、旧路径调用方地图

### run-command

| 通道/端 | 调用方 | 证据 |
|---|---|---|
| 网页抽屉 | extend/dialog/parts/01b_bridge.js:400，POST /api/bridge/run-command | :392 注释：与 QQ 里敲指令完全同一条链路 |
| Flask 路由 | flask_server/routes/bridge.py:294 | 唯一入口 |
| 测试 | flask_server/tests/test_bridge_command_routes.py | 路由覆盖 |
| QQ / 微信 / 企微 | 无调用（三网关 grep 零命中） | 通道侧指令走 command_dispatch 独立链路；command_dispatch.py:197 注释：与 AI 工具（external-call 卡片、结果回传 AI）是两条独立链路 |

### external-call 信封的生产与消费

| 通道 | 生产（包装成卡片） | 消费 / 解析 |
|---|---|---|
| QQ | qq_gateway.py:331/338/383 | message_parse.py:53/117（含嵌套穿透），:126 打 source=qq |
| 企业微信 | wecom_gateway.py:343 区段 | 同上公共解析 |
| 微信 | weixin_gateway.py:122 | 同上公共解析 |
| 网页（反向投给网页 AI） | channel/delivery.py:78-89 拼信封、:227-240 deliver_text 投 external-call 卡片 | web_bridge/web_mirror.py:306/379；core/envelope.py:23-62 集中解析；core/memory_distill.py:285/317 蒸馏兼容 |

### is_tool_result

| 层 | 位置 | 说明 |
|---|---|---|
| 构造（三通道共用） | outbound.py:28/46/109/130 | 上报统一打标 |
| 消费 | message_flow.py:219；message_router.py:306 | kind=ai 且非工具结果的公共判定 |

**地图结论**：三条线索均无通道专属实现——run-command 只有网页抽屉一个调用方，三网关零命中；external-call 三通道各自包装，解析全在公共层；is_tool_result 构造单点、消费两点。符合清单改造原则 2/4/5，无需通用化动作。

## 三、G10 复现取证清单

1. 截图企微侧乱序现场，与 QQ 同批消息对照。
2. 开管线日志（G4 已加通道名与接收方），核对同一批 items 的服务端发送顺序与到达顺序。
3. 验证切片顺序：抽屉上报 items 的时间戳 vs 服务端发送日志。
4. 先确认「先文后图」「语音补推」是否已构成用户感知的乱序主体；若否，再查 items 乱序。

## 四、新发现：跨刷新恢复键仍含消息指纹（G11 关联）

- executedSigs 存储键（05j_card_sig.js 的 _executedSig / _markExecutedSig / _restoreExecutedCards）= 会话 id + msgId（消息指纹）+ 工具名 + 参数，即清单所述「版本一」构型，文件头注释亦自称消息指纹。
- 版本二（只按工具名+参数）目前仅落地在幽灵卡判据 cardMatchesBySig。
- 风险：卡片登记后 AI 对同一消息追加内容 → 消息指纹变化 → 刷新后恢复查询失配 → 已执行卡片退回待执行，与 G11 原始症状同向。
- 建议：列入 G11 下次复现核对项。清单已有两项（扩展是否重载、签名匹配失败诊断），再加一项——重判日志出现「恢复=0 而签名库>0」时，比对登记与查询两侧的 msgId 是否一致。

## 五、遗留真机验证项汇总

- G8：企微 markdown 实际渲染（清单已有）。
- G11：扩展重载确认 + 签名匹配失败诊断 + 本文第四节恢复键核对。
- G12：/rall 重启后首条是否仍重复。
