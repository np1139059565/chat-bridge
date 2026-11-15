/*
 * B-12 execute 段实装夹具（S2 装配面九步第 5 步）。
 * 只读 require adapter（node 分支）；不装配 M、不建开关、不切活链。
 * 覆盖：单参声明回显（C-9 兼容）、双参实装成功/失败/异常三路径、
 * 诊断字段复位、running 置位时序、deps 非函数边界、UMD 导出形态。
 */
'use strict';
const assert = require('node:assert/strict');
const A = require('../../../extend/lib/standard_chain_adapter.js');
const test = require('node:test');

// 一、单参 / 无参：声明回显，C-9 边界不变。
test('B-12 单参回显：无 deps 时与 C-9 语义一致', () => {
  assert.deepEqual(A.execute(null), { by: A.KEY, card: null, status: A.STATUS });
  assert.deepEqual(A.execute(), { by: A.KEY, card: null, status: A.STATUS });
  const card = { id: 'call_n1' };
  assert.strictEqual(A.execute(card).card, card);
  assert.equal(A.execute(card).status, A.STATUS);
});

// 二、双参实装：成功路径。callTool 写 done → 影子 executed:true。
test('B-12 双参成功：running→done，影子 executed', async () => {
  const card = { id: 'call_n1', tool: 'run_command' };
  const order = [];
  const shadow = await A.execute(card, {
    callTool: async (c) => {
      order.push(c.status);
      c.status = 'done';
      c.result = { ok: true };
    }
  });
  assert.deepEqual(order, ['running']);
  assert.equal(card.status, 'done');
  assert.equal(shadow.status, A.EXECUTE_STATUS);
  assert.equal(shadow.executed, true);
  assert.equal(shadow.phase, 'execute-done');
  assert.strictEqual(shadow.card, card);
});

// 三、双参实装：失败路径。callTool 写 error → 影子仍 executed:true（对齐旧链无条件判定）。
test('B-12 双参失败：error 状态仍记 executed', async () => {
  const card = { id: 'call_e1' };
  const shadow = await A.execute(card, {
    callTool: async (c) => {
      c.status = 'error';
      c.error = 'tool_failed';
    }
  });
  assert.equal(card.status, 'error');
  assert.equal(card.error, 'tool_failed');
  assert.equal(shadow.executed, true);
  assert.equal(shadow.phase, 'execute-done');
});

// 四、双参实装：异常路径。callTool reject → 兜底写 error、不向调用方抛出。
test('B-12 双参异常：兜底写 error 且 resolve', async () => {
  const card = { id: 'call_x1' };
  const shadow = await A.execute(card, {
    callTool: async () => { throw new Error('boom'); }
  });
  assert.equal(card.status, 'error');
  assert.equal(card.error, 'Error: boom');
  assert.equal(shadow.phase, 'execute-caught');
  assert.equal(shadow.executed, true);
});

// 五、诊断复位：预置旧诊断字段，进 callTool 前全部清空。
test('B-12 诊断复位：七字段预置后清空', async () => {
  const card = {
    id: 'call_r1',
    error: '旧错', result: {旧: 1}, stack: '旧栈',
    errorType: '旧型', origin: '旧源', location: {旧: 2}, hint: '旧提示'
  };
  const seen = {};
  await A.execute(card, {
    callTool: async (c) => {
      seen.error = c.error; seen.result = c.result; seen.stack = c.stack;
      seen.errorType = c.errorType; seen.origin = c.origin;
      seen.location = c.location; seen.hint = c.hint;
      c.status = 'done';
    }
  });
  assert.equal(seen.error, null);
  assert.equal(seen.result, null);
  assert.equal(seen.stack, null);
  assert.equal(seen.errorType, '');
  assert.equal(seen.origin, '');
  assert.equal(seen.location, null);
  assert.equal(seen.hint, '');
});

// 六、deps 非函数边界：callTool 缺失或非函数 → 声明回显，不触碰 card。
test('B-12 deps 边界：非函数回显且 card 原样', () => {
  const card = { id: 'call_b1', status: 'pending' };
  assert.deepEqual(A.execute(card, {}), { by: A.KEY, card: card, status: A.STATUS });
  assert.deepEqual(A.execute(card, { callTool: 'not-a-function' }),
    { by: A.KEY, card: card, status: A.STATUS });
  assert.equal(card.status, 'pending');
});

// 七、UMD 形态：node 分支 require 即导出；EXECUTE_STATUS 与 STATUS 区分。
test('B-12 导出面：EXECUTE_STATUS 独立于 STATUS', () => {
  assert.equal(A.STATUS, 'declared-placeholder');
  assert.equal(A.EXECUTE_STATUS, 'implemented-S2-step5');
  assert.notEqual(A.STATUS, A.EXECUTE_STATUS);
  assert.equal(typeof A.execute, 'function');
});
console.log('B12_EXECUTE_IMPL_OK');
