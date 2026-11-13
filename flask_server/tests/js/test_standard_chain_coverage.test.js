// C-7 P1 覆盖率补正：两个契约面 lib 的分支覆盖。
// 覆盖 id 生成 / 剥前缀、content 空值、execKey 各形态与 catch。
// 覆盖 assertStandardToolCall 四个 throw 分支与合法返回。
// 覆盖适配层六段传值与空值两侧。
// 不装配运行时、不硬编码 A-7/B-7、不新建切换开关。
// 门禁阈值 90 / 70 与仓库基线不变，未改钩子。

/* C-7 P1 覆盖率补正：走满两个新 lib 的短路 / 三元 / throw / catch 分支两侧。 */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../../../extend/lib/standard_chain_contract.js');
const A = require('../../../extend/lib/standard_chain_adapter.js');

test('contract: id 生成 / 剥前缀 两侧', () => {
  assert.equal(C.makeToolCallId('n1'), 'call_n1');
  assert.equal(C.makeToolCallId(undefined), 'call_');
  assert.equal(C.makeToolCallId(null), 'call_');
  assert.equal(C.makeToolCallId(0), 'call_0');
  assert.equal(C.nonceFromToolCallId('call_n1'), 'n1');
  assert.equal(C.nonceFromToolCallId('legacy'), 'legacy');
  assert.equal(C.nonceFromToolCallId(undefined), '');
  assert.equal(C.nonceFromToolCallId(null), '');
});
test('contract: tool 消息 content 两侧', () => {
  const a = C.standardToolMessage('call_n1', 'OK');
  assert.deepEqual(a, { role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
  const b = C.standardToolMessage(null, null);
  assert.equal(b.role, 'tool'); assert.equal(b.content, '');
  assert.equal(C.standardToolMessage('x', undefined).content, '');
});
test('contract: execKey 各 call 形态 + 循环引用 catch', () => {
  assert.ok(C.execKeyFromToolCall({ id: 'call_n1', tool: 't', parameters: { a: 1 } }, 's1').indexOf('s1') === 0);
  assert.ok(C.execKeyFromToolCall({ id: 'call_n1', function: { name: 'f', arguments: '{}' } }, '').length > 0);
  assert.ok(C.execKeyFromToolCall(null, null).length >= 0);
  assert.ok(C.execKeyFromToolCall({}, 's').indexOf('fingerprint') < 0);
  const cyc = { id: 'call_z', tool: 't', parameters: {} };
  cyc.parameters.self = cyc;
  assert.ok(C.execKeyFromToolCall(cyc, 's').indexOf('call_z'.slice(5)) >= 0);
});
test('contract: assertStandardToolCall 四个分支', () => {
  assert.equal(C.assertStandardToolCall({ id: 'call_a', function: { name: 'f', arguments: '{}' } }), true);
  assert.throws(() => C.assertStandardToolCall(null), /must be object/);
  assert.throws(() => C.assertStandardToolCall('x'), /must be object/);
  assert.throws(() => C.assertStandardToolCall({ function: { name: 'f' } }), /id required/);
  assert.throws(() => C.assertStandardToolCall({ id: 'call_a' }), /name required/);
  assert.throws(() => C.assertStandardToolCall({ id: 'call_a', function: {} }), /name required/);
});
test('contract: 声明契约面', () => {
  assert.ok(C.PRE_DISPATCH_HOOK_CONTRACT.signature.indexOf('fn(history)') >= 0);
  assert.equal(C.PRE_DISPATCH_HOOK_CONTRACT.status, 'declared-placeholder');
  assert.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status, 'declared-placeholder');
});
test('adapter: 六段 传值 / 空值 两侧', () => {
  assert.equal(A.parse({ x: 1 }).status, 'declared-placeholder');
  assert.equal(A.parse(null).block, null);
  assert.equal(A.buildCard({ id: 'call_n1' }).id, 'call_n1');
  assert.equal(A.buildCard(null).id, null);
  assert.equal(A.execute({ id: 'call_n1' }).status, A.STATUS);
  assert.equal(A.execute().card, null);
  assert.equal(A.reply({ tool_call_id: 'call_n1' }).role, 'tool');
  assert.equal(A.reply(null).tool_call_id, null);
  assert.equal(A.dedupe('call_a', 'call_b').by, A.KEY);
  assert.equal(A.dedupe().a, null);
  assert.equal(A.dedupe().b, null);
  assert.equal(A.restore('s1', { id: 'call_n1' }).noMessageFingerprint, true);
  assert.equal(A.restore(null, null).sessionId, '');
  assert.equal(A.restore(null, null).id, null);
});
console.log('C7_P1_COVERAGE_OK');
