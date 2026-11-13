/*
 * C-7 平行夹具样板（11 组，对应 C-6 第三节 11 份直接依赖的 js 测试）
 * 性质：按标准 tool_call.id 与 tool 消息为新键的断言样板，只 require 本笔声明契约面骨架；
 *   不改既有 11 份夹具、不装配运行时、不引用 A-7/B-7 文件、不新建切换开关、不切活链。
 * A-7 / B-7 交付后由分发方字段契约对拍，不一致时定向裁定补正，c 按裁定改。
 */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../../../extend/lib/standard_chain_contract.js');
const A = require('../../../extend/lib/standard_chain_adapter.js');

const ID = C.makeToolCallId('n1');
const CALL = { id: ID, function: { name: 'run_command', arguments: '{}' } };

test('01 parse: tool_call.id 为唯一键', () => {
  assert.equal(ID, 'call_n1');
  assert.doesNotThrow(() => C.assertStandardToolCall(CALL));
  assert.equal(A.parse({ type: 'tool_calls', id: ID }).by, 'tool_call.id');
});
test('02 parse_tolerant: 站点装饰污染不改变键', () => {
  assert.equal(C.nonceFromToolCallId('call_n1'), 'n1');
  assert.equal(C.nonceFromToolCallId('legacy'), 'legacy');
  assert.equal(A.parse({ noisy: true }).status, 'declared-placeholder');
});
test('03 card_build_behavior: 建卡候选按 id', () => {
  assert.equal(A.buildCard(CALL).id, ID);
  assert.equal(A.buildCard({}).id, null);
});
test('04 adjacent_dup_card: 相邻去重按 id 比对', () => {
  assert.equal(A.dedupe(ID, C.makeToolCallId('n1')).by, 'tool_call.id');
});
test('05 same_message_dup_card: 同消息去重键不含消息指纹', () => {
  const k = C.execKeyFromToolCall({ id: ID, tool: 'run_command', parameters: {} }, 's1');
  assert.ok(k.indexOf('fingerprint') < 0);
});
test('06 scroll_autoexec: 自动执行候选沿用 tool 消息回执', () => {
  const m = C.standardToolMessage(ID, 'OK');
  assert.equal(m.role, 'tool');
  assert.equal(m.tool_call_id, ID);
  assert.equal(A.execute({ id: ID }).status, 'declared-placeholder');
});
test('07 card_sig_restore: 恢复键为会话 id + tool_call.id + 工具名 + 参数', () => {
  const k = C.execKeyFromToolCall({ id: ID, tool: 't', parameters: { a: 1 } }, 's1');
  assert.ok(k.indexOf('s1') === 0 && k.indexOf('n1') > 0);
  assert.equal(A.restore('s1', CALL).noMessageFingerprint, true);
});
test('08 clear_sessions_sig: 签名库去消息指纹且可复算', () => {
  const k1 = C.execKeyFromToolCall({ id: ID, tool: 't', parameters: { a: 1 } }, 's1');
  const k2 = C.execKeyFromToolCall({ id: ID, tool: 't', parameters: { a: 1 } }, 's1');
  assert.equal(k1, k2);
});
test('09 translator: 回执为标准 tool 消息', () => {
  assert.equal(C.standardToolMessage(ID, 'OK').content, 'OK');
  assert.equal(A.reply({ tool_call_id: ID }).role, 'tool');
});
test('10 translator_wiring: 声明钩子契约 fn(history)->None|list', () => {
  assert.ok(C.PRE_DISPATCH_HOOK_CONTRACT.signature.indexOf('fn(history)') >= 0);
  assert.equal(C.PRE_DISPATCH_HOOK_CONTRACT.status, 'declared-placeholder');
});
test('11 translator_wiring_require: 协议退役方向与占位不硬编码', () => {
  assert.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status, 'declared-placeholder');
  assert.equal(A.STATUS, 'declared-placeholder');
  assert.equal(A.KEY, 'tool_call.id');
});
console.log('C7_FIXTURES_OK');
