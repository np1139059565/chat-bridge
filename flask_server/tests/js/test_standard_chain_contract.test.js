/* C-7 契约断言：只锁声明契约面；不引用 A-7/B-7 文件、不探测其存在、不切活链。可由 node 直接执行，亦由 check_js_tests 收录。 */
'use strict';
var assert = require('assert');
var C = require('../../../extend/lib/standard_chain_contract.js');
assert.strictEqual(C.makeToolCallId('n1'), 'call_n1');
assert.strictEqual(C.nonceFromToolCallId('call_n1'), 'n1');
assert.strictEqual(C.nonceFromToolCallId('legacy'), 'legacy');
var msg = C.standardToolMessage('call_n1', '{"ok":true}');
assert.strictEqual(msg.role, 'tool');
assert.strictEqual(msg.tool_call_id, 'call_n1');
var key = C.execKeyFromToolCall({ id: 'call_n1', tool: 'run_command', parameters: { cmd: 'x' } }, 'sess1');
assert.ok(key.indexOf('fingerprint') < 0 && key.indexOf('call_n1'.slice(5)) >= 0);
assert.ok(C.PRE_DISPATCH_HOOK_CONTRACT.signature.indexOf('fn(history)') >= 0);
assert.strictEqual(C.PRE_DISPATCH_HOOK_CONTRACT.status, 'declared-placeholder');
assert.strictEqual(C.PROTOCOL_RETIREMENT_CONTRACT.status, 'declared-placeholder');
assert.strictEqual(C.assertStandardToolCall({ id: 'call_a', function: { name: 'f', arguments: '{}' } }), true);
assert.throws(function () { C.assertStandardToolCall({ function: { name: 'f' } }); });
console.log('C7_CONTRACT_OK');

/* C-7 适配层六段占位契约断言（本笔新增，不引用他笔文件、不切活链） */
var A = require('../../../extend/lib/standard_chain_adapter.js');
['parse','buildCard','execute','reply','dedupe','restore'].forEach(function (k) {
  assert.strictEqual(typeof A[k], 'function', k + ' must be function');
});
assert.strictEqual(A.KEY, 'tool_call.id');
assert.strictEqual(A.parse({ type: 'tool_calls' }).status, 'declared-placeholder');
assert.strictEqual(A.buildCard({ id: 'call_n1' }).id, 'call_n1');
assert.strictEqual(A.reply({ tool_call_id: 'call_n1' }).role, 'tool');
assert.strictEqual(A.dedupe('call_n1', 'call_n2').by, 'tool_call.id');
assert.strictEqual(A.restore('sess1', { id: 'call_n1' }).noMessageFingerprint, true);
console.log('C7_ADAPTER_OK');
