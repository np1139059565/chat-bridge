/*
 * C-8 配套契约断言夹具。
 * 校验 A-7 × C-7 对拍矩阵文档与两个已合入 lib 的契约面一致。
 * 只读：不装配运行时、不注册钩子、不新建切换开关、不切活链、不改他笔文件。
 * 不新增被测 JS 源文件，故不引入新的覆盖率分母。
 * 矩阵状态标签计数与装配面九步落点由 fs 读文档断言，避免文档漂移。
 */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const C = require('../../../extend/lib/standard_chain_contract.js');
const A = require('../../../extend/lib/standard_chain_adapter.js');

// 矩阵文档位于 extend/lib/ 下，只读取不改写。
const MD = path.join(__dirname, '..', '..', '..',
  'extend', 'lib', 'standard_chain_field_matrix.md');
const doc = fs.readFileSync(MD, 'utf8');

// 一、矩阵：14 条逐项对拍，状态分布应与文档汇总一致。
test('C-8 对拍矩阵：一致 10 / 待对拍 4 / 不一致 0', () => {
  assert.equal(doc.split('| 一致 |').length - 1, 10);
  assert.equal(doc.split('| 待对拍 |').length - 1, 4);
  assert.equal(doc.split('| 不一致 |').length - 1, 0);
  assert.ok(doc.indexOf('不一致：0 条') >= 0);
});

// 二、装配面九步的关键落点必须都在文档里（只读推演，不含运行期装配）。
test('C-8 装配面：九步落点与 B-7 依赖登记齐全', () => {
  assert.ok(doc.indexOf('## 二、端到端装配面只读推演') >= 0);
  const keys = [
    'model_reply_hook', '_normalize_item', '_run_pre_dispatch_hooks',
    'buildCard', 'standardToolMessage', 'dedupe', '05j_card_sig.js',
    '06_execute.js', 'B-7', 'call_<nonce>'
  ];
  keys.forEach((k) => assert.ok(doc.indexOf(k) >= 0, k));
});

// 三、A-7 钩子签名面：C-7 占位声明与实交付同形、同名字。
test('C-8 A-7 钩子面：签名与名字一致（零调整）', () => {
  const h = C.PRE_DISPATCH_HOOK_CONTRACT;
  assert.ok(h.signature.indexOf('fn(history)') >= 0);
  assert.equal(h.status, 'declared-placeholder');
  ['register_pre_dispatch_hook', 'clear_pre_dispatch_hooks',
    '_run_pre_dispatch_hooks'].forEach((n) => assert.ok(h.names.indexOf(n) >= 0, n));
});

// 四、标准字段面：tool_call.id 生成 / 剥前缀、tool 消息三键、契约校验。
test('C-8 标准字段面：id 与 tool 消息三键', () => {
  assert.equal(C.makeToolCallId('n1'), 'call_n1');
  assert.equal(C.nonceFromToolCallId('call_n1'), 'n1');
  assert.equal(C.nonceFromToolCallId('legacy'), 'legacy');
  assert.deepEqual(C.standardToolMessage('call_n1', 'OK'),
    { role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
  assert.equal(C.assertStandardToolCall(
    { id: 'call_a', function: { name: 'f', arguments: '{}' } }), true);
  assert.throws(() => C.assertStandardToolCall({ id: 'call_a' }),
    /name required/);
  const k = C.execKeyFromToolCall(
    { id: 'call_n1', tool: 't', parameters: { a: 1 } }, 's1');
  assert.ok(k.indexOf('s1') === 0 && k.indexOf('fingerprint') < 0);
});

// 五、C-7 六段占位：函数名、唯一键、未装配状态。
test('C-8 六段占位：以 tool_call.id 为唯一键且仍为声明态', () => {
  assert.equal(A.KEY, 'tool_call.id');
  assert.equal(A.STATUS, 'declared-placeholder');
  const segs = ['parse', 'buildCard', 'execute', 'reply', 'dedupe', 'restore'];
  segs.forEach((s) => assert.equal(typeof A[s], 'function', s));
  assert.equal(A.parse({ type: 'tool_calls' }).by, A.KEY);
  assert.equal(A.buildCard({ id: 'call_n1' }).id, 'call_n1');
  assert.equal(A.execute({ id: 'call_n1' }).by, A.KEY);
  assert.equal(A.reply({ tool_call_id: 'call_n1' }).role, 'tool');
  assert.equal(A.dedupe('call_a', 'call_b').by, A.KEY);
  assert.equal(A.restore('s1', { id: 'call_n1' }).noMessageFingerprint, true);
});

// 六、协议字段退役方向：B-7 未交付，保持声明占位、不硬编码替换位。
test('C-8 协议退役：B-7 未交付，保持声明占位', () => {
  const p = C.PROTOCOL_RETIREMENT_CONTRACT;
  assert.equal(p.status, 'declared-placeholder');
  assert.ok(p.legacy.indexOf('bridge-chat-call') >= 0);
  assert.ok(p.legacy.indexOf('bridge-chat-res') >= 0);
  assert.ok(p.direction.indexOf('tool_calls') >= 0);
});
console.log('C8_FIELD_MATRIX_OK');
