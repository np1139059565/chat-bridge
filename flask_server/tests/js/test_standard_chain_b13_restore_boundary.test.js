/*
 * B-13 restore 单点边界反查夹具（零代码改动的只读取证片，dispatcher-20261115T222437-661433）。
 * 只读 require 已合入 adapter（node 分支）；契约 .md 与活链文件 fs 只读反查，
 * 按字符码 10 切行、普通 indexOf / split（零反斜杠零正则）。
 * 覆盖：返回形状恰五键、sessionId / id 归一、noMessageFingerprint 恒真、
 * 幂等新对象、C-9 / C-14 两处标注对拍、运行期唯一定义与零调用方。
 * 新增被测 JS 源 0；无 fs 写 / shell / 网络；不装配 M、不建开关、不切活链。
 */
'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const test = require('node:test');
const AD = require('../../../extend/lib/standard_chain_adapter.js');

const LF = String.fromCharCode(10);
const repoRoot = path.resolve(__dirname, '../../..');
function load(rel) { return fs.readFileSync(path.join(repoRoot, rel), 'utf8'); }
function has(text, needle) { return text.indexOf(needle) >= 0; }
function row(text, head) {
  return text.split(LF).filter((l) => l.indexOf(head) === 0);
}
const adapterSrc = load('extend/lib/standard_chain_adapter.js');
const contractSrc = load('extend/lib/standard_chain_contract.js');
const boundary = load('extend/lib/standard_chain_boundary_contract.md');
const table = load('extend/lib/standard_chain_c14_signature_table.md');
const executePart = load('extend/dialog/parts/06_execute.js');
const parsePart = load('extend/dialog/parts/05f_parse.js');
const dataPart = load('extend/dialog/parts/00_data.js');
const cardsPart = load('extend/dialog/parts/05g_cards.js');
const sigPart = load('extend/dialog/parts/05j_card_sig.js');
const dialogHtml = load('extend/dialog/dialog.html');
const FLAT = { by: 'tool_call.id', sessionId: '', id: null,
  noMessageFingerprint: true, status: 'declared-placeholder' };

// 一、导出面：restore 在六段导出内；KEY / STATUS / EXECUTE_STATUS 不漂移。
test('B-13 导出面：restore 在六段导出内且三个常量不漂移', () => {
  assert.equal(typeof AD.restore, 'function');
  ['parse', 'buildCard', 'execute', 'reply', 'dedupe', 'restore'].forEach(function (n) {
    assert.equal(typeof AD[n], 'function');
  });
  assert.equal(AD.KEY, 'tool_call.id');
  assert.equal(AD.STATUS, 'declared-placeholder');
  assert.equal(AD.EXECUTE_STATUS, 'implemented-S2-step5');
});

// 二、返回形状：完整入参恰五键，不含 msgId。
test('B-13 形状：完整入参返回恰五键且指纹恒真', () => {
  const out = AD.restore('sess_b13', { id: 'call_b13' });
  assert.deepEqual(Object.keys(out).sort(),
    ['by', 'id', 'noMessageFingerprint', 'sessionId', 'status']);
  assert.equal(out.by, 'tool_call.id');
  assert.equal(out.sessionId, 'sess_b13');
  assert.equal(out.id, 'call_b13');
  assert.equal(out.noMessageFingerprint, true);
  assert.equal(out.status, 'declared-placeholder');
  assert.equal(Object.prototype.hasOwnProperty.call(out, 'msgId'), false);
});

// 三、缺键归一：空 sessionId、缺 call / 缺 id 深等于扁平形状，不抛错。
test('B-13 缺键归一：空会话与缺 call 深等于扁平形状', () => {
  ['', null, undefined].forEach((s) => {
    assert.deepEqual(AD.restore(s, { id: 'call_n1' }),
      Object.assign({}, FLAT, { id: 'call_n1' }));
  });
  assert.deepEqual(AD.restore('sess_1', null),
    Object.assign({}, FLAT, { sessionId: 'sess_1' }));
  assert.deepEqual(AD.restore('sess_1', {}),
    Object.assign({}, FLAT, { sessionId: 'sess_1' }));
  assert.deepEqual(AD.restore(null, null), FLAT);
});

// 四、幂等与新对象：同参两次不共享引用且深相等；入参对象不被改写。
test('B-13 幂等与新对象：重复恢复等价且不共享引用', () => {
  const call = { id: 'call_same' };
  const first = AD.restore('sess_1', call);
  const second = AD.restore('sess_1', call);
  assert.notEqual(first, second);
  assert.deepEqual(first, second);
  assert.equal(first.status, 'declared-placeholder');
  assert.deepEqual(call, { id: 'call_same' });
  [null, undefined, 42, 'x'].forEach((v) => {
    assert.doesNotThrow(() => AD.restore(v, null));
  });
});

// 五、C-9 对拍：restore 段标题、G4、幂等语义、第二节状态行逐格在文。
test('B-13 C-9 对拍：restore 段两处标注与代码实况一致', () => {
  assert.ok(has(boundary, '### 6. restore(sessionId, call)'));
  assert.ok(has(boundary, 'G4 **刷新恢复键语义**'));
  assert.ok(has(boundary, '恒为 true'));
  assert.ok(has(boundary, '重复恢复幂等'));
  assert.ok(has(boundary, '05j_card_sig.js'));
  const statusRows = row(boundary, '| restore | declared-placeholder |');
  assert.equal(statusRows.length, 1);
  assert.ok(has(statusRows[0], 'tool 三键'));
  assert.ok(has(statusRows[0], 'true（恒真）'));
  assert.ok(has(statusRows[0], '否'));
});

// 六、C-14 对拍：第二节 restore 行逐格一致；第六节 B-12 追加节不含 restore。
test('B-13 C-14 对拍：签名行一致且第六节无 restore 字样', () => {
  const restoreRows = row(table, '| restore(sessionId,call) |');
  assert.equal(restoreRows.length, 1);
  assert.ok(has(restoreRows[0], 'standard_chain_adapter.js'));
  assert.ok(has(restoreRows[0],
    '返回 by=KEY、sessionId、id、noMessageFingerprint=true、status=STATUS'));
  assert.ok(has(restoreRows[0], '一致'));
  assert.ok(has(restoreRows[0], 'declared-placeholder'));
  assert.ok(has(table, '## 六、execute 段实装登记'));
  const sec6 = table.slice(table.indexOf('## 六、'));
  assert.equal(sec6.indexOf('restore') >= 0, false);
});

// 七、运行期取证：adapter 源内唯一定义、活链零调用方、contract 无 restore 面。
test('B-13 运行期取证：唯一定义且活链零调用方', () => {
  assert.equal(adapterSrc.split('function restore(').length - 1, 1);
  [executePart, parsePart, dataPart, cardsPart, sigPart, dialogHtml].forEach(function (src) {
    assert.equal(src.indexOf('.restore(') >= 0, false);
  });
  assert.equal(contractSrc.indexOf('restore') >= 0, false);
  assert.ok(has(dialogHtml, 'standard_chain_adapter.js'));
});
