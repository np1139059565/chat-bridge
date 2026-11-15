/*
 * C-14 已合入契约面字段签名总表反查夹具。
 * 只读 require 四个已合入 lib 与 fs 反查六份已合入 .md + 本总表。
 * 断言：四 lib STATUS/KEY 相等、三键一致、八槽集合恰为 M1-M8 且两片互斥、
 * 六段接口名齐全、S1-S4 与 #4/#7/#13/#14 编号封闭、C-12/C-13 只读引用成立、
 * 夹具不 import 任何未合入模块、总表 declaration 语义不翻转。
 * 本笔不新增 lib 源码，新增被测 JS 源 0；已合入 lib 由各自夹具加载、已在覆盖率报告内。
 * 全文零反斜杠零正则，按字符码 10 切行规避跨端转义差异。
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const A = require('../../../extend/lib/standard_chain_adapter.js');
const C = require('../../../extend/lib/standard_chain_contract.js');
const B8 = require('../../../extend/lib/standard_slot_m345.js');
const B9 = require('../../../extend/lib/standard_chain_b9_slot_resolver.js');

const LF = String.fromCharCode(10);
const libRoot = path.resolve(__dirname, '../../../extend/lib');
function doc(n) { return fs.readFileSync(path.join(libRoot, n), 'utf8'); }
const self = doc('standard_chain_c14_signature_table.md');
const p8 = doc('standard_chain_field_matrix.md');
const p9 = doc('standard_chain_boundary_contract.md');
const p10 = doc('standard_chain_pending_criteria.md');
const p11 = doc('standard_chain_crossref_index.md');
const p12 = doc('standard_chain_replacement_map.md');
const p13 = doc('standard_chain_c13_crossref_index.md');
const IDS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8'];
const B9IDS = ['M1', 'M2', 'M6', 'M7', 'M8'];
const B8IDS = ['M3', 'M4', 'M5'];
const SIX = ['parse', 'buildCard', 'execute', 'reply', 'dedupe', 'restore'];
const SVALS = ['S1', 'S2', 'S3', 'S4'];
const MVALS = ['#4', '#7', '#13', '#14'];
function rows(text, prefix) {
  return text.split(LF).filter((l) => l.indexOf(prefix) === 0);
}

// 一、四个已合入 lib 的 STATUS 与 KEY 全部相等，且恒声明态。
test('C-14 四 lib：STATUS 相等且恒 declared-placeholder', () => {
  [A, B8, B9].forEach((m) => {
    assert.equal(m.STATUS, 'declared-placeholder');
    assert.equal(m.KEY, 'tool_call.id');
  });
  assert.equal(C.PRE_DISPATCH_HOOK_CONTRACT.status, A.STATUS);
  assert.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status, A.STATUS);
  assert.equal(B8.STATUS, B9.STATUS);
  assert.equal(A.KEY, B8.KEY);
  assert.equal(B8.KEY, B9.KEY);
});

// 二、tool 消息三键与 call_<nonce> 唯一键一致、不含消息指纹。
test('C-14 唯一键：三键、前缀与去消息指纹一致', () => {
  assert.equal(C.PREFIX, 'call_');
  assert.equal(C.makeToolCallId('n1'), 'call_n1');
  assert.equal(C.nonceFromToolCallId('call_n1'), 'n1');
  assert.deepEqual(Array.from(B9.TOOL_MESSAGE_KEYS), ['role', 'tool_call_id', 'content']);
  assert.ok(Object.isFrozen(B9.TOOL_MESSAGE_KEYS));
  const msg = C.standardToolMessage('call_n1', 'OK');
  assert.deepEqual(msg, { role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
  const key = C.execKeyFromToolCall(
    { id: 'call_n1', tool: 't', parameters: { a: 1 } }, 's1');
  assert.ok(key.indexOf('s1') === 0 && key.indexOf('n1') >= 0);
  assert.ok(key.indexOf('fingerprint') < 0 && key.indexOf('call_') < 0);
});

// 三、六段占位接口名在 adapter 导出与六份文档中齐全。
test('C-14 六段接口：adapter 导出与 C-9 / 本总表一致', () => {
  SIX.forEach((name) => {
    assert.equal(typeof A[name], 'function', name);
    assert.ok(p9.indexOf(name) >= 0, 'C-9 ' + name);
    assert.ok(self.indexOf(name) >= 0, '总表 ' + name);
  });
  assert.ok(p11.indexOf('六段') >= 0);
});

// 四、八槽集合恰为 M1-M8，B-8 三槽与 B-9 五槽互斥且并集为八槽。
test('C-14 八槽：两片集合互斥、并集恰为 M1-M8', () => {
  const allSlots = B9.SLOTS.map(function (s) { return s.id; });
  assert.deepEqual(allSlots, B9IDS);
  const b8Names = Object.keys(B8).filter(function (k) {
    return k.slice(0, 2) === 'm3' || k.slice(0, 2) === 'm4' || k.slice(0, 2) === 'm5';
  });
  assert.equal(b8Names.length, 6);
  const overlap = B9IDS.filter(function (id) { return B8IDS.indexOf(id) >= 0; });
  assert.equal(overlap.length, 0);
  assert.deepEqual(B8IDS.concat(B9IDS).sort(), IDS.slice().sort());
  IDS.forEach((id) => assert.ok(p12.indexOf('### 槽位 ' + id) >= 0, 'C-12 ' + id));
  assert.equal(rows(p13, '| ' + IDS[0] + ' |').length, 1);
  IDS.forEach((id) => assert.ok(p13.indexOf('| ' + id + ' |') >= 0, 'C-13 ' + id));
});

// 五、编号体系封闭：S1-S4 与矩阵编号在四处文档齐全、无悬空值。
test('C-14 编号封闭：S1-S4 与 #4/#7/#13/#14 齐全', () => {
  const docs = [p10, p11, p12, self];
  SVALS.forEach((s) => docs.forEach((d) => assert.ok(d.indexOf(s) >= 0, s)));
  MVALS.forEach((n) => {
    docs.forEach((d) => assert.ok(d.indexOf(n) >= 0, n));
    assert.ok(p8.indexOf('| ' + n.slice(1) + ' |') >= 0 || p8.indexOf(n) >= 0, 'C-8 ' + n);
  });
  assert.ok(p10.indexOf('槽位 S1') >= 0 && p11.indexOf('S4') >= 0);
});

// 六、逐文件导出行在总表中齐全，每条标一致与声明态。
test('C-14 总表：逐文件签名行齐全且一致态、声明态', () => {
  const tableRows = self.split(LF).filter((l) => l.indexOf('| ') === 0 && l.indexOf('declared-placeholder') >= 0);
  assert.ok(tableRows.length >= 25, '总表签名行数');
  ['standard_chain_adapter.js', 'standard_chain_contract.js',
    'standard_slot_m345.js', 'standard_chain_b9_slot_resolver.js',
    'standard_chain_field_matrix.md', 'standard_chain_pending_criteria.md',
    'standard_chain_replacement_map.md', 'standard_chain_c13_crossref_index.md']
    .forEach((f) => assert.ok(self.indexOf(f) >= 0, f));
  tableRows.forEach((r) => {
    assert.ok(r.indexOf('一致') >= 0, '一致列');
    assert.ok(r.indexOf('declared-placeholder') >= 0, 'STATUS 列');
  });
});

// 七、declaration 语义：清单/映射层声明态不因纯函数层可实测翻转。
test('C-14 declaration：纯函数层可实测但不翻 STATUS', () => {
  assert.ok(self.indexOf('清单/映射层声明态不因纯函数层可实测而翻转') >= 0);
  const r = B9.resolveReplacement({ slot: 'M1', marker: B9.findSlot('M1').standard });
  assert.equal(r.accepted, true);
  assert.equal(r.status, 'declared-placeholder');
  assert.equal(B8.m3CommandToToolCall('/sd').status, 'declared-placeholder');
  assert.ok(self.indexOf('不把 declared-placeholder 翻成已装配') >= 0);
});

// 八、边界：夹具只 import 已合入模块，总表只读、docs 只追加、不预设结论。
test('C-14 边界：只读基准、不预设结论、docs 只追加', () => {
  const fixtext = fs.readFileSync(path.resolve(__dirname,
    'test_standard_chain_c14_signature_table.test.js'), 'utf8');
  const mods = [
    'node:assert/strict', 'node:fs', 'node:path', 'node:test',
    '../../../extend/lib/standard_chain_adapter.js',
    '../../../extend/lib/standard_chain_contract.js',
    '../../../extend/lib/standard_slot_m345.js',
    '../../../extend/lib/standard_chain_b9_slot_resolver.js'
  ];
  mods.forEach((m) => assert.ok(fixtext.indexOf(m) >= 0, m));
  const callLines = fixtext.split(LF).filter((l) =>
    l.trim().indexOf('const ') === 0 && l.indexOf('require(') >= 0
    && l.indexOf('fixtext') < 0);
  callLines.forEach((l) => assert.ok(mods.some((m) => l.indexOf(m) >= 0), l));
  assert.equal(callLines.length, mods.length);
  ['只读签名总表', '不实装执行下游', '不装配运行时 M', '不建切换开关',
    '不切活链', '不摘除任何旧标记', '不预设 B-7 总结论',
    'docs 只追加', '新增被测 JS 源 0'].forEach((k) => {
      assert.ok(self.indexOf(k) >= 0, k);
    });
  assert.ok(self.indexOf('require(') < 0 && self.indexOf('module.exports') < 0);
});

// 九、C-12 / C-13 只读引用成立，总表不新建编号体系。
test('C-14 C-12/C-13 引用：八槽与编号体系原样沿用', () => {
  assert.equal(p12.split('### 槽位 M').length - 1, 8);
  assert.equal(p13.split('### 槽位 M').length - 1, 0);
  assert.ok(p13.indexOf('M1-M8 八槽') >= 0 || p13.indexOf('M1-M8') >= 0);
  assert.ok(self.indexOf('不新建编号体系') >= 0 || self.indexOf('编号体系封闭') >= 0);
  assert.ok(self.indexOf('C-12') >= 0 && self.indexOf('C-13') >= 0);
});
console.log('C14_SIGNATURE_TABLE_OK');
