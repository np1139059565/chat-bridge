
/*
 * B-8 三槽协议字段替换位「落点转换 / 拒绝」纯函数层（方案 A）。
 * 槽位：C-12 映射清单 M3 run-command / M4 external-call / M5 is_tool_result。
 *
 * 边界（分发方 2026-11-15 01:07 裁定与同轮广播）：
 * - 只提供可实测的转换 / 拒绝能力：旧位输入返回拒绝或标准化结果，
 *   新位输入返回规范化结果，异常输入返回不落盘的拒绝对象；
 * - 不装配到运行时 M、不建切换开关、不切活链、不新增运行期探测分支；
 * - 三槽对应活链文件零改动（01b_bridge.js / 01g_external_cards.js / bridge.py /
 *   delivery.py / message_parse.py / outbound.py / message_flow.py / message_router.py）；
 * - M4 按 b6-legacy-caller-map.md 结论不新建、不修改三网关包装文件。
 *
 * STATUS 分层：清单 / 映射层恒为 declared-placeholder（描述性、未装配运行时）；
 * 本层返回值中的 status 仅回显该映射层状态，纯函数可测不等于已实装、不翻 STATUS。
 *
 * 唯一键：标准 tool_call.id（call_<nonce>）与 tool 消息三键
 * role / tool_call_id / content；不引入消息指纹作键。
 */
'use strict';

var STATUS = 'declared-placeholder';
var KEY = 'tool_call.id';

/* ---- 公共小件 ---------------------------------------------------- */

/* 统一成功形态：{slot, ok:true, status, value}，value 为标准化结果。 */
function accept(slot, value) {
  return { slot: slot, ok: true, status: STATUS, value: value };
}

/* 统一拒绝形态：{slot, ok:false, status, reason}。纯函数不落盘、无副作用。 */
function refuse(slot, reason) {
  return { slot: slot, ok: false, status: STATUS, reason: reason };
}

/* null / undefined 归空串，其余经 String() 收敛。 */
function textOrEmpty(v) {
  return v == null ? '' : String(v);
}

/* 从标准 tool_call 取参数：兼容顶层 arguments 与 function.arguments 两种摆放。 */
function callArguments(call) {
  if (!call || typeof call !== 'object') return null;
  if (call.arguments && typeof call.arguments === 'object') return call.arguments;
  if (call.function && call.function.arguments) return call.function.arguments;
  return null;
}

/* 标准 id 反解 nonce：call_x 归 x；无前缀原样返回；空值归空串。 */
function nonceOf(id) {
  var s = textOrEmpty(id);
  return s.indexOf('call_') === 0 ? s.slice(5) : s;
}

/* 由文本种子生成确定性 nonce（M3 用：同一指令文本恒得同一 id）。 */
function seedNonce(prefix, seed) {
  var h = 0;
  for (var i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) | 0;
  }
  return prefix + '-' + (h >>> 0).toString(36);
}

/* 组装标准 tool_call：唯一键在 id，意图在 function。 */
function makeCall(nonce, name, args) {
  return { id: 'call_' + nonce, function: { name: name, arguments: args } };
}

/* ---- M3 run-command ---------------------------------------------- */
/* 旧位（当前 main 实测 + b6 调用方地图）：
 *   网页抽屉 runBridgeCommand（01b_bridge.js L396-404）POST
 *   /api/bridge/run-command，请求体 { text }，回执落收件箱、不进 AI 对话流；
 *   Flask 唯一路由 bridge_run_command（routes/bridge.py L294-302）；
 *   三网关 grep 零命中——通道侧指令走 command_dispatch 独立链路
 *   （command_dispatch.py L194-198 隔离铁律：任何情况不得流向 AI）。 */

/* 旧指令文本到标准 tool_call 意图位：非空且以斜杠开头才接受。 */
function m3CommandToToolCall(text) {
  var t = textOrEmpty(text);
  if (t === '' || t.charAt(0) !== '/') {
    return refuse('M3', 'text 必须为非空且以斜杠开头的指令');
  }
  return accept('M3', makeCall(seedNonce('m3', t), 'run-command', { text: t }));
}

/* 标准 tool_call 回旧请求体（对拍用）：工具名与 text 形态同时校验。 */
function m3ToolCallToCommand(call) {
  var args = callArguments(call);
  if (!args) return refuse('M3', '标准意图缺少可读参数');
  var name = (call.function && call.function.name) || call.name || '';
  if (name !== 'run-command') return refuse('M3', '工具名必须为 run-command');
  var t = textOrEmpty(args.text);
  if (t === '' || t.charAt(0) !== '/') {
    return refuse('M3', 'arguments.text 必须为非空斜杠指令');
  }
  return accept('M3', { endpoint: '/api/bridge/run-command', body: { text: t } });
}

/* ---- M4 external-call -------------------------------------------- */
/* 旧位（当前 main 实测 + b6 地图）：
 *   生产两侧——三通道各自包装（qq_gateway / wecom_gateway / weixin_gateway）
 *   与网页反向投递 _text_envelope（channel/delivery.py L77-100）：
 *   { type:'external-call', nonce, request, source?, openid?, msg_id?, from_voice? }；
 *   前端侧 01g_external_cards.js L238-246 同构信封经统一发送队列回传；
 *   消费解析全在公共层 message_parse.py L50-55 / L103-120
 *   （嵌套穿透 + 裸 JSON 兜底）。 */

/* 旧信封到标准 tool_call 意图位：nonce 即标准键来源，request 移入参数。 */
function m4EnvelopeToToolCall(env) {
  if (!env || typeof env !== 'object') return refuse('M4', '信封必须为对象');
  if (env.type !== 'external-call') return refuse('M4', '信封 type 必须 external-call');
  if (textOrEmpty(env.request) === '') return refuse('M4', '信封 request 缺失');
  if (textOrEmpty(env.nonce) === '') return refuse('M4', '信封 nonce 缺失');
  var args = {
    request: env.request,
    page_url: textOrEmpty(env.page_url),
    source: textOrEmpty(env.source),
    openid: textOrEmpty(env.openid),
    msg_id: textOrEmpty(env.msg_id),
    from_voice: !!env.from_voice
  };
  return accept('M4', makeCall(textOrEmpty(env.nonce), 'external-call', args));
}

/* 标准 tool_call 回旧信封形态（对拍用）。 */
function m4ToolCallToEnvelope(call) {
  var args = callArguments(call);
  if (!args || textOrEmpty(args.request) === '') {
    return refuse('M4', '标准意图参数 request 缺失');
  }
  var n = nonceOf(call && call.id);
  if (n === '') return refuse('M4', '标准 id 缺失，无法回填信封 nonce');
  return accept('M4', {
    type: 'external-call',
    nonce: n,
    request: args.request,
    page_url: textOrEmpty(args.page_url)
  });
}

/* ---- M5 is_tool_result ------------------------------------------- */
/* 旧位（当前 main 实测 + b6 地图）：
 *   构造单点 outbound.py：build_body 三分支 L44-47（普通正文 false）、
 *   L105-111（纯工具结果 true）、L128-131（思考折叠 false）；
 *   消费两点 message_flow.py L219 与 message_router.py L306，
 *   均为 kind=ai 且非工具结果的公共判定（语音等附加能力据此跳过）。 */

/* 旧标记结构到 tool 消息三键：仅 is_tool_result=true 进入迁移；
 * content 缺省时回退出站 text 字段。 */
function m5FlagToToolMessage(obj) {
  if (!obj || typeof obj !== 'object') return refuse('M5', '出站结构必须为对象');
  if (obj.is_tool_result !== true) {
    return refuse('M5', 'is_tool_result 必须为 true 才进入迁移');
  }
  var cid = textOrEmpty(obj.tool_call_id);
  if (cid === '') return refuse('M5', '缺少 tool_call_id，无法落到标准键');
  var body = obj.content == null ? textOrEmpty(obj.text) : String(obj.content);
  return accept('M5', { role: 'tool', tool_call_id: cid, content: body });
}

/* tool 消息三键回旧标记形态（对拍用）。 */
function m5ToolMessageToFlag(msg) {
  if (!msg || typeof msg !== 'object') return refuse('M5', 'tool 消息必须为对象');
  if (msg.role !== 'tool') return refuse('M5', 'role 必须为 tool');
  var cid = textOrEmpty(msg.tool_call_id);
  if (cid === '') return refuse('M5', '缺少 tool_call_id，无法回放旧标记');
  return accept('M5', {
    kind: 'ai', is_tool_result: true, tool_call_id: cid,
    text: textOrEmpty(msg.content), markdown: true, skip: false
  });
}

module.exports = {
  STATUS: STATUS, KEY: KEY,
  m3CommandToToolCall: m3CommandToToolCall,
  m3ToolCallToCommand: m3ToolCallToCommand,
  m4EnvelopeToToolCall: m4EnvelopeToToolCall,
  m4ToolCallToEnvelope: m4ToolCallToEnvelope,
  m5FlagToToolMessage: m5FlagToToolMessage,
  m5ToolMessageToFlag: m5ToolMessageToFlag
};
