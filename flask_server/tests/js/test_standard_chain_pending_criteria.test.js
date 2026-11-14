/*
 * C-10 待对拍判据清单反查夹具。
 * 同时读 C-8 矩阵与 C-10 清单，校验 4 槽位与 #4/#7/#13/#14 对齐。
 * 每槽三段齐全、三态判据齐全、STATUS 仍为声明态、不预设 B-7 结论。
 * 只读：不改 lib 源码、不装配 M、不建开关、不切活链、不改他笔文件。
 * 新增被测 JS 源文件数为 0，故不引入新的覆盖率分母。
 * 全文避免反斜杠转义，按字符码 10 切行，规避跨端字符串转义差异。
 */
'use strict';
const fs = require('node:fs');
const test = require('node:test');
const path = require('node:path');
const A = require('../../../extend/lib/standard_chain_adapter.js');
const assert = require('node:assert/strict');
const C = require('../../../extend/lib/standard_chain_contract.js');

// 两份文档都在 extend/lib/ 下，只读不改写。
const libDir = path.resolve(__dirname, '../../../extend/lib');
const matrix = fs.readFileSync(
  path.join(libDir, 'standard_chain_field_matrix.md'), 'utf8');
const doc = fs.readFileSync(
  path.join(libDir, 'standard_chain_pending_criteria.md'), 'utf8');
const NL = String.fromCharCode(10);
const mLines = matrix.split(NL);
const dLines = doc.split(NL);
const heads = dLines.filter((l) => l.indexOf('## 槽位 S') === 0);
const bodies = doc.split('## 槽位 S').slice(1);

// 一、矩阵反查：C-8 仍是 4 条待对拍，编号与汇总不变。
test('C-10 矩阵：待对拍 4 条且编号 #4/#7/#13/#14', () => {
  const pend = mLines.filter((l) => l.indexOf('| 待对拍 |') >= 0);
  assert.equal(pend.length, 4);
  ['| 4 |', '| 7 |', '| 13 |', '| 14 |'].forEach((n) => {
    assert.ok(pend.some((l) => l.indexOf(n) >= 0), n);
  });
  assert.ok(matrix.indexOf('待对拍 4 条') >= 0);
});

// 二、清单槽位数 = 4，且与矩阵编号一一对应。
test('C-10 清单：槽位数 = 4 且 S1-S4 对齐矩阵编号', () => {
  assert.equal(heads.length, 4);
  assert.equal(bodies.length, 4);
  const pairs = [['S1', '#4'], ['S2', '#7'], ['S3', '#13'], ['S4', '#14']];
  pairs.forEach((p, k) => {
    assert.ok(heads[k].indexOf(p[0]) >= 0, p[0]);
    assert.ok(heads[k].indexOf(p[1]) >= 0, p[1]);
  });
});

// 三、每槽三段齐全：判据 / 替换位 / 收口条件。
test('C-10 清单：每槽三段（判据 / 替换位 / 收口条件）', () => {
  const tags = ['### 判据', '### 协议字段替换位',
    '### 收口条件与旧标记摘除前置'];
  bodies.forEach((b, k) => {
    tags.forEach((t) => assert.ok(b.indexOf(t) >= 0,
      'S' + (k + 1) + ' ' + t));
  });
});

// 四、每槽判据段三态齐全，且不预设结论。
test('C-10 清单：判据段一致 / 待对拍 / 不一致三态齐全', () => {
  bodies.forEach((b, k) => {
    const seg = b.split('### 判据')[1]
      .split('### 协议字段替换位')[0];
    ['- 一致', '- 待对拍', '- 不一致'].forEach((s) => {
      assert.ok(seg.indexOf(s) >= 0, 'S' + (k + 1) + ' ' + s);
    });
  });
  assert.ok(doc.indexOf('不预设 B-7 结论') >= 0);
  assert.ok(doc.indexOf('只描述分发方判定口径') >= 0);
});

// 五、替换位段：旧位到新位、协议字段与三网关均显式登记。
test('C-10 清单：替换位显式列旧位到新位与 B-7 面', () => {
  assert.ok(doc.indexOf('旧位→新位') >= 0);
  ['bridge-chat-call', 'bridge-chat-res', 'run-command',
    'external-call', 'is_tool_result', '三网关'].forEach((k) => {
      assert.ok(doc.indexOf(k) >= 0, k);
    });
});

// 六、收口条件：三笔齐备、另行下发、c 不自行摘除。
test('C-10 清单：三笔齐备与旧标记摘除前置', () => {
  assert.ok(doc.indexOf('三笔对拍齐备') >= 0);
  assert.ok(doc.indexOf('另行下发') >= 0);
  assert.ok(doc.indexOf('不自行摘除') >= 0);
  assert.ok(doc.indexOf('分发方只验收合入') >= 0);
});

// 七、B-7 拆片兼容：判定时点不预设结论。
test('C-10 判定时点：拆片兼容且不预设 B-7 结论', () => {
  assert.ok(doc.indexOf('B-8/B-9') >= 0);
  assert.ok(doc.indexOf('判定时点') >= 0);
  assert.ok(doc.indexOf('不预设 B-7 是否拆片') >= 0);
});

// 八、STATUS 仍为声明态：adapter 与契约退役面均未实装。
test('C-10 STATUS：六段与协议退役仍 declared-placeholder', () => {
  assert.equal(A.STATUS, 'declared-placeholder');
  assert.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status,
    'declared-placeholder');
  assert.equal(A.KEY, 'tool_call.id');
  assert.ok(doc.indexOf('declared-placeholder') >= 0);
  assert.equal(A.execute({ id: 'call_n1' }).status, A.STATUS);
});

// 九、唯一键面：call_<nonce> 与 tool 消息三键，不含消息指纹。
test('C-10 唯一键：标准键与 tool 消息三键', () => {
  assert.equal(C.makeToolCallId('n1'), 'call_n1');
  assert.deepEqual(C.standardToolMessage('call_n1', 'OK'),
    { role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
  const k = C.execKeyFromToolCall(
    { id: 'call_n1', tool: 't', parameters: { a: 1 } }, 's1');
  assert.ok(k.indexOf('fingerprint') < 0);
});
console.log('C10_PENDING_CRITERIA_OK');
