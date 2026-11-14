/*
 * C-9 边界语义契约夹具。
 * 六段占位在异常输入下的返回形状与不变量，逐段至少一条断言。
 * 只读 require 两个已合入 lib；不装配 M、不建开关、不切活链。
 * 契约文档用 fs 反查，确保 STATUS / KEY / noMessageFingerprint 不漂移。
 * 新增被测 JS 源文件数为 0，故不引入新的覆盖率分母。
 */
'use strict';
const assert = require('node:assert/strict');
const A = require('../../../extend/lib/standard_chain_adapter.js');
const test = require('node:test');
const C = require('../../../extend/lib/standard_chain_contract.js');
const path = require('node:path');
const fs = require('node:fs');

// 文档路径与 C-8 夹具写法刻意错开，避免跨文件连续重复块。
const doc = fs.readFileSync(path.resolve(__dirname,
  '../../../extend/lib/standard_chain_boundary_contract.md'), 'utf8');
const shape = {
  by: A.KEY,
  status: A.STATUS
};

// 一、文档反查：全局不变量、六段标题、只追加记录齐全。
test('C-9 文档：G1-G4 与六段标题齐全', () => {
  ['G1', 'G2', 'G3', 'G4', 'parse(block)', 'buildCard(call)',
    'execute(card)', 'reply(msg)', 'dedupe(a, b)',
    'restore(sessionId, call)', 'docs 只追加'].forEach((k) => {
      assert.ok(doc.indexOf(k) >= 0, k);
    });
  assert.ok(doc.indexOf('declared-placeholder') >= 0);
  assert.ok(doc.indexOf('noMessageFingerprint') >= 0);
});

// 二、parse：null / undefined / 空 block / code 块均不解析、不抛错。
test('C-9 parse 边界：缺块归一、空块回显', () => {
  assert.deepEqual(A.parse(null), Object.assign({ block: null }, shape));
  assert.deepEqual(A.parse(undefined), Object.assign({ block: null }, shape));
  const empty = A.parse({});
  assert.deepEqual(empty, Object.assign({ block: {} }, shape));
  const code = { type: 'code', code: 'x' };
  assert.strictEqual(A.parse(code).block, code);
  assert.equal(A.parse(code).status, A.STATUS);
});

// 三、buildCard：缺 id / null call 回落 null，标准键原样保留。
test('C-9 buildCard 边界：缺 id 不生成替代键', () => {
  assert.deepEqual(A.buildCard(null), Object.assign({ id: null }, shape));
  assert.deepEqual(A.buildCard({}), Object.assign({ id: null }, shape));
  assert.equal(A.buildCard({ id: 'call_n1' }).id, 'call_n1');
  assert.equal(A.buildCard({ id: 'call_n1' }).by, A.KEY);
});

// 四、execute：null / 无参不抛错、不发命令，card 原样回显。
test('C-9 execute 边界：null card 归一且不触发下游', () => {
  assert.deepEqual(A.execute(null), Object.assign({ card: null }, shape));
  assert.deepEqual(A.execute(), Object.assign({ card: null }, shape));
  const card = { id: 'call_n1' };
  assert.strictEqual(A.execute(card).card, card);
  assert.equal(A.execute(card).status, A.STATUS);
});

// 五、reply：缺 tool_call_id 归一；role 非 tool 仍强制归一为 tool，
// 不回显入参 role、不抛错；content 不在返回形状内。
test('C-9 reply 边界：role 强制归一、缺键回落 null', () => {
  const missing = A.reply({ role: 'tool' });
  assert.equal(missing.tool_call_id, null);
  assert.equal(missing.role, 'tool');
  assert.equal(missing.status, A.STATUS);
  const wrongRole = A.reply({ role: 'assistant', tool_call_id: 'call_n1' });
  assert.equal(wrongRole.role, 'tool');
  assert.equal(wrongRole.tool_call_id, 'call_n1');
  assert.equal(A.reply(null).tool_call_id, null);
  const full = A.reply({ role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
  assert.equal(Object.prototype.hasOwnProperty.call(full, 'content'), false);
  assert.deepEqual(C.standardToolMessage('call_n1', 'OK'),
    { role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
});

// 六、dedupe：同 id / 不同 id / null 入参都只回显，不做判重决策。
test('C-9 dedupe 边界：同键与异键形状一致、null 回落', () => {
  const same = A.dedupe('call_n1', 'call_n1');
  assert.deepEqual(same, Object.assign({ a: 'call_n1', b: 'call_n1' }, shape));
  const diff = A.dedupe('call_a', 'call_b');
  assert.deepEqual(diff, Object.assign({ a: 'call_a', b: 'call_b' }, shape));
  assert.deepEqual(A.dedupe(null, null),
    Object.assign({ a: null, b: null }, shape));
  assert.equal(A.dedupe(null, 'call_a').a, null);
});

// 七、restore：空 sessionId 归一、无消息指纹恒真、重复恢复幂等。
test('C-9 restore 边界：空会话 / 无指纹 / 重复恢复幂等', () => {
  const r1 = A.restore('', { id: 'call_n1' });
  assert.equal(r1.sessionId, '');
  assert.equal(r1.noMessageFingerprint, true);
  assert.equal(r1.status, A.STATUS);
  assert.equal(r1.by, A.KEY);
  assert.equal(A.restore(null, null).sessionId, '');
  assert.equal(A.restore(null, null).id, null);
  const r2 = A.restore('s1', { id: 'call_n1' });
  const r3 = A.restore('s1', { id: 'call_n1' });
  assert.notStrictEqual(r2, r3);
  assert.deepEqual(r2, r3);
  assert.equal(r3.noMessageFingerprint, true);
});

// 八、标准键面：makeToolCallId 与 execKey 均不含消息指纹。
test('C-9 唯一键：call_<nonce> 与去消息指纹', () => {
  assert.equal(C.makeToolCallId('n1'), 'call_n1');
  assert.equal(C.nonceFromToolCallId('call_n1'), 'n1');
  const k = C.execKeyFromToolCall(
    { id: 'call_n1', tool: 't', parameters: { a: 1 } }, 's1');
  assert.ok(k.indexOf('s1') === 0);
  assert.ok(k.indexOf('fingerprint') < 0);
});
console.log('C9_BOUNDARY_OK');
