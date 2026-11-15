
/*
 * B-8 三槽「落点转换 / 拒绝」纯函数层反查夹具（M3 / M4 / M5，方案 A）。
 * 只读依赖：本笔新增的 extend/lib/standard_slot_m345.js、
 * 已合入的 extend/lib/standard_chain_contract.js（C-7，合并 0897e0a）
 * 与 extend/lib/standard_chain_replacement_map.md（C-12，合并 e9e3844）。
 * 断言口径（分发方 2026-11-15 01:07 裁定与同轮广播）：
 * - 旧位输入返回拒绝或标准化结果、新位输入返回规范化结果、
 *   异常输入返回不落盘的拒绝对象（ok:false、无 value、无副作用）；
 * - 三槽唯一键均为标准 tool_call.id（call_ 前缀）与 tool 消息三键，不掺消息指纹；
 * - STATUS 分层：纯函数层只回显映射层 declared-placeholder，不因可实测翻状态；
 * - 被测 JS 源按真实形态计 1（本夹具直接 import 纯函数层），
 *   覆盖率纳入 check_js_tests 的 90/70 阈值，不改 hooks / 阈值 / baseline。
 */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../../../extend/lib/standard_slot_m345.js');
const C = require('../../../extend/lib/standard_chain_contract.js');
const fs = require('node:fs');
const path = require('node:path');

const libDir = path.resolve(__dirname, '../../../extend/lib');
const NL = String.fromCharCode(10);
const mapDoc = fs.readFileSync(
  path.join(libDir, 'standard_chain_replacement_map.md'), 'utf8');

// ---- M3 run-command：旧位 = 指令执行桥接层 ----

test('M3 旧指令 -> 标准 tool_call：斜杠指令落到标准键', () => {
  const r = S.m3CommandToToolCall('/sd');
  assert.equal(r.ok, true);
  assert.equal(r.slot, 'M3');
  assert.equal(r.value.function.name, 'run-command');
  assert.equal(r.value.function.arguments.text, '/sd');
  assert.ok(r.value.id.indexOf('call_m3-') === 0);
});

test('M3 确定性 id：同文本同 id、异文本异 id', () => {
  const a = S.m3CommandToToolCall('/status');
  const b = S.m3CommandToToolCall('/status');
  const c = S.m3CommandToToolCall('/help');
  assert.equal(a.value.id, b.value.id);
  assert.notEqual(a.value.id, c.value.id);
});

test('M3 拒绝：非斜杠 / 空串 / null / undefined / 非串', () => {
  ['status', '', null, undefined, 42].forEach((t) => {
    const r = S.m3CommandToToolCall(t);
    assert.equal(r.ok, false);
    assert.equal(r.slot, 'M3');
    assert.ok(typeof r.reason === 'string' && r.reason.length > 0);
    assert.ok(!('value' in r));
  });
});

test('M3 反向：标准 tool_call -> 旧请求体（端点与字段面对拍）', () => {
  const call = { id: 'call_m3-1',
    function: { name: 'run-command', arguments: { text: '/sd' } } };
  const r = S.m3ToolCallToCommand(call);
  assert.equal(r.ok, true);
  assert.equal(r.value.endpoint, '/api/bridge/run-command');
  assert.equal(r.value.body.text, '/sd');
});

test('M3 反向拒绝：工具名不符 / 缺参数 / 非斜杠 / 空入参', () => {
  assert.equal(S.m3ToolCallToCommand(
    { id: 'c', function: { name: 'other', arguments: { text: '/sd' } } }).ok, false);
  assert.equal(S.m3ToolCallToCommand(
    { id: 'c', function: { name: 'run-command' } }).ok, false);
  assert.equal(S.m3ToolCallToCommand(
    { id: 'c', function: { name: 'run-command', arguments: { text: 'x' } } }).ok, false);
  assert.equal(S.m3ToolCallToCommand(null).ok, false);
});

test('M3 往返：指令文本逐字保持', () => {
  const fwd = S.m3CommandToToolCall('/rall abc def');
  const back = S.m3ToolCallToCommand(fwd.value);
  assert.equal(back.ok, true);
  assert.equal(back.value.body.text, '/rall abc def');
});

// ---- M4 external-call：旧位 = 外部调用包装层 ----

test('M4 旧信封 -> 标准 tool_call：nonce 为标准键来源', () => {
  const env = { type: 'external-call', nonce: 'qq-1731612345678',
    request: '帮我截屏', source: 'qq', openid: 'oX1',
    msg_id: 'm9', from_voice: true, page_url: 'https://p' };
  const r = S.m4EnvelopeToToolCall(env);
  assert.equal(r.ok, true);
  assert.equal(r.slot, 'M4');
  assert.equal(r.value.id, 'call_qq-1731612345678');
  assert.equal(r.value.function.name, 'external-call');
  assert.equal(r.value.function.arguments.request, '帮我截屏');
  assert.equal(r.value.function.arguments.source, 'qq');
  assert.equal(r.value.function.arguments.from_voice, true);
});

test('M4 最小信封：可选字段归默认值不阻断', () => {
  const r = S.m4EnvelopeToToolCall(
    { type: 'external-call', nonce: 'n1', request: 'hi' });
  assert.equal(r.ok, true);
  assert.equal(r.value.function.arguments.page_url, '');
  assert.equal(r.value.function.arguments.from_voice, false);
});

test('M4 拒绝：非对象 / type 不符 / request 缺失 / nonce 缺失', () => {
  assert.equal(S.m4EnvelopeToToolCall(null).ok, false);
  assert.equal(S.m4EnvelopeToToolCall(7).ok, false);
  assert.equal(S.m4EnvelopeToToolCall(
    { type: 'drawer-command', nonce: 'n', request: 'x' }).ok, false);
  assert.equal(S.m4EnvelopeToToolCall(
    { type: 'external-call', nonce: 'n' }).ok, false);
  assert.equal(S.m4EnvelopeToToolCall(
    { type: 'external-call', request: 'x' }).ok, false);
  const r = S.m4EnvelopeToToolCall({});
  assert.equal(r.ok, false);
  assert.ok(!('value' in r));
});

test('M4 反向：标准 tool_call -> 旧信封形态', () => {
  const r = S.m4ToolCallToEnvelope({ id: 'call_wx-42',
    function: { name: 'external-call',
      arguments: { request: 'hi', page_url: 'https://q' } } });
  assert.equal(r.ok, true);
  assert.equal(r.value.type, 'external-call');
  assert.equal(r.value.nonce, 'wx-42');
  assert.equal(r.value.request, 'hi');
});

test('M4 反向拒绝：request 缺失 / id 缺失', () => {
  assert.equal(S.m4ToolCallToEnvelope(
    { id: 'call_x', function: { arguments: {} } }).ok, false);
  assert.equal(S.m4ToolCallToEnvelope(
    { function: { arguments: { request: 'x' } } }).ok, false);
});

test('M4 往返与 C-7 契约互认：nonce/request 保持、call_ 前缀语义一致', () => {
  const fwd = S.m4EnvelopeToToolCall(
    { type: 'external-call', nonce: 'qq-abc', request: '问天气' });
  const back = S.m4ToolCallToEnvelope(fwd.value);
  assert.equal(back.value.nonce, 'qq-abc');
  assert.equal(back.value.request, '问天气');
  assert.equal(C.nonceFromToolCallId(fwd.value.id), 'qq-abc');
  assert.equal(C.makeToolCallId('qq-abc'), fwd.value.id);
});

test('M4 id 前缀容错：无 call_ 前缀的 id 原样作为 nonce', () => {
  const r = S.m4ToolCallToEnvelope(
    { id: 'plain-9', function: { arguments: { request: 'r' } } });
  assert.equal(r.ok, true);
  assert.equal(r.value.nonce, 'plain-9');
});

// ---- M5 is_tool_result：旧位 = 结果识别标记层 ----

test('M5 旧标记 -> tool 消息三键', () => {
  const r = S.m5FlagToToolMessage(
    { is_tool_result: true, tool_call_id: 'call_n1', text: 'ok done' });
  assert.equal(r.ok, true);
  assert.equal(r.slot, 'M5');
  assert.equal(r.value.role, 'tool');
  assert.equal(r.value.tool_call_id, 'call_n1');
  assert.equal(r.value.content, 'ok done');
});

test('M5 content 优先、text 兜底', () => {
  const a = S.m5FlagToToolMessage(
    { is_tool_result: true, tool_call_id: 'c1', content: 'A', text: 'B' });
  assert.equal(a.value.content, 'A');
  const b = S.m5FlagToToolMessage(
    { is_tool_result: true, tool_call_id: 'c1', text: 'B' });
  assert.equal(b.value.content, 'B');
});

test('M5 拒绝：非 true 标记（严格 true）/ 缺 tool_call_id / 非对象', () => {
  assert.equal(S.m5FlagToToolMessage(
    { is_tool_result: false, tool_call_id: 'c' }).ok, false);
  assert.equal(S.m5FlagToToolMessage(
    { is_tool_result: 1, tool_call_id: 'c' }).ok, false);
  assert.equal(S.m5FlagToToolMessage({ is_tool_result: true }).ok, false);
  assert.equal(S.m5FlagToToolMessage('x').ok, false);
  assert.equal(S.m5FlagToToolMessage(null).ok, false);
});

test('M5 反向：tool 消息 -> 旧标记（kind=ai 面）', () => {
  const r = S.m5ToolMessageToFlag(
    { role: 'tool', tool_call_id: 'call_n1', content: 'ok' });
  assert.equal(r.ok, true);
  assert.equal(r.value.kind, 'ai');
  assert.equal(r.value.is_tool_result, true);
  assert.equal(r.value.tool_call_id, 'call_n1');
  assert.equal(r.value.text, 'ok');
  assert.equal(r.value.markdown, true);
});

test('M5 反向拒绝：role 不符 / 缺 tool_call_id / 空入参', () => {
  assert.equal(S.m5ToolMessageToFlag(
    { role: 'assistant', tool_call_id: 'c' }).ok, false);
  assert.equal(S.m5ToolMessageToFlag({ role: 'tool', content: 'x' }).ok, false);
  assert.equal(S.m5ToolMessageToFlag(null).ok, false);
  assert.equal(S.m5ToolMessageToFlag({}).ok, false);
});

test('M5 往返：content 与 tool_call_id 逐字保持', () => {
  const fwd = S.m5FlagToToolMessage(
    { is_tool_result: true, tool_call_id: 'call_zz', text: 'result body' });
  const back = S.m5ToolMessageToFlag(fwd.value);
  assert.equal(back.value.text, 'result body');
  assert.equal(back.value.tool_call_id, 'call_zz');
});

// ---- 分层与不变量 ----

test('STATUS 分层：纯函数层回显映射层状态、不翻 STATUS', () => {
  assert.equal(S.STATUS, 'declared-placeholder');
  assert.equal(S.KEY, 'tool_call.id');
  const rs = [
    S.m3CommandToToolCall('/x'),
    S.m3ToolCallToCommand(
      { id: 'c', function: { name: 'run-command', arguments: { text: '/x' } } }),
    S.m4EnvelopeToToolCall({ type: 'external-call', nonce: 'n', request: 'r' }),
    S.m4ToolCallToEnvelope(
      { id: 'call_n', function: { arguments: { request: 'r' } } }),
    S.m5FlagToToolMessage(
      { is_tool_result: true, tool_call_id: 'c', text: 't' }),
    S.m5ToolMessageToFlag({ role: 'tool', tool_call_id: 'c', content: 't' })
  ];
  rs.forEach((r) => assert.equal(r.status, 'declared-placeholder'));
});

test('拒绝无残留：拒绝结果一律无 value 且 reason 非空', () => {
  const bad = [
    S.m3CommandToToolCall(''), S.m3CommandToToolCall(null),
    S.m3ToolCallToCommand(null), S.m3ToolCallToCommand({}),
    S.m4EnvelopeToToolCall({}), S.m4EnvelopeToToolCall('s'),
    S.m4ToolCallToEnvelope({}),
    S.m5FlagToToolMessage({}), S.m5ToolMessageToFlag({})
  ];
  bad.forEach((r) => {
    assert.equal(r.ok, false);
    assert.ok(!('value' in r), '拒绝结果不得携带 value');
    assert.ok(typeof r.reason === 'string' && r.reason.length > 0);
    assert.equal(r.status, 'declared-placeholder');
  });
});

test('不掺消息指纹：三槽键均落在标准键位', () => {
  const m4 = S.m4EnvelopeToToolCall(
    { type: 'external-call', nonce: 'nn-1', request: 'x' });
  assert.equal(m4.value.id, 'call_nn-1');
  const m5 = S.m5FlagToToolMessage(
    { is_tool_result: true, tool_call_id: 'call_t1', text: 'y' });
  assert.equal(m5.value.tool_call_id, 'call_t1');
});

test('参数摆放兼容：顶层 arguments 与 function.arguments 等价、call.name 兜底', () => {
  const top = S.m3ToolCallToCommand(
    { id: 'c1', arguments: { text: '/sd' }, function: { name: 'run-command' } });
  const nested = S.m3ToolCallToCommand(
    { id: 'c1', function: { name: 'run-command', arguments: { text: '/sd' } } });
  const byName = S.m3ToolCallToCommand(
    { id: 'c1', name: 'run-command', arguments: { text: '/sd' } });
  assert.equal(top.ok, true);
  assert.equal(nested.ok, true);
  assert.equal(byName.ok, true);
  assert.deepEqual(top.value, nested.value);
  assert.deepEqual(byName.value, nested.value);
});

// ---- C-12 基线对齐（只读引用，供分发方对拍） ----

test('C-12 基线对齐：M3/M4/M5 槽位与三类旧字段已登记', () => {
  const heads = mapDoc.split(NL)
    .filter((l) => l.indexOf('### 槽位 M') === 0);
  ['M3', 'M4', 'M5'].forEach((m) => {
    assert.ok(heads.some((h) => h.indexOf(m) >= 0), m);
  });
  ['run-command', 'external-call', 'is_tool_result'].forEach((k) => {
    assert.ok(mapDoc.indexOf(k) >= 0, k);
  });
});

console.log('B8_M345_SLOT_OK');
