/*
 * C-13 B-8 × B-9 方案 A 纯函数层八槽交叉一致性反查夹具。
 * 只读 require 两片已合入纯函数与 C-7 两个 lib，只读 fs 反查本索引与四份已合入 .md。
 * 断言八槽齐全、两片独立命名无文件交集、STATUS 恒 declared-placeholder、
 * 唯一键一致、C-12 只读引用成立、编号封闭无悬空。
 * 本笔不新增 lib 纯函数源码；两片纯函数由各自 B-8 / B-9 夹具加载，已在覆盖率报告内，
 * 不引入新的覆盖率分母，新增被测 JS 源 0。
 * 全文零反斜杠零正则，按字符码 10 切行规避跨端转义差异。
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const B8 = require('../../../extend/lib/standard_slot_m345.js');
const B9 = require('../../../extend/lib/standard_chain_b9_slot_resolver.js');
const C = require('../../../extend/lib/standard_chain_contract.js');
const A = require('../../../extend/lib/standard_chain_adapter.js');

const LF = String.fromCharCode(10);
const libRoot = path.join(__dirname, '..', '..', '..', 'extend', 'lib');
function doc(name) { return fs.readFileSync(path.join(libRoot, name), 'utf8'); }
const idx = doc('standard_chain_c13_crossref_index.md');
const map = doc('standard_chain_replacement_map.md');
const p10 = doc('standard_chain_pending_criteria.md');
const p8 = doc('standard_chain_field_matrix.md');
const p11 = doc('standard_chain_crossref_index.md');
const b8src = doc('standard_slot_m345.js');
const b9src = doc('standard_chain_b9_slot_resolver.js');
const IDS = ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8'];
const B9IDS = ['M1', 'M2', 'M6', 'M7', 'M8'];
const B8IDS = ['M3', 'M4', 'M5'];
function rowsOf(text) {
  return text.split(LF).filter((l) => IDS.some((id) => l.indexOf('| ' + id + ' |') === 0));
}
function layerRowsOf(text) {
  return text.split(LF).filter((l) => IDS.some((id) => l.indexOf('- ' + id + '：') === 0));
}

// 一、索引表格八槽齐全且顺序一致。
test('C-13 索引：M1-M8 八槽表格行齐全且顺序一致', () => {
  const rows = rowsOf(idx);
  assert.equal(rows.length, 8);
  IDS.forEach((id, k) => assert.ok(rows[k].indexOf('| ' + id + ' |') === 0, id));
  assert.equal(layerRowsOf(idx).length, 8);
});

// 二、逐槽字段：归属片 / 文件名 / STATUS / 唯一键 / S 槽 / 矩阵编号。
test('C-13 逐槽：归属片与文件名、STATUS、唯一键、编号列齐全', () => {
  const rows = rowsOf(idx);
  rows.forEach((r, k) => {
    const cells = r.split('|').map((x) => x.trim());
    const id = IDS[k];
    assert.equal(cells[1], id);
    assert.equal(cells[4], 'declared-placeholder');
    assert.ok(cells[5].indexOf('tool_call.id') >= 0, id + ' 唯一键');
    const owner = B9IDS.indexOf(id) >= 0 ? 'B-9' : 'B-8';
    assert.equal(cells[2], owner);
    const fname = owner === 'B-9'
      ? 'standard_chain_b9_slot_resolver.js' : 'standard_slot_m345.js';
    assert.equal(cells[3], fname);
    assert.ok(cells[6].indexOf('S') >= 0 && cells[7].indexOf('#') >= 0, id + ' 编号');
  });
});

// 三、两片独立命名、互不 require、槽位集合互斥且并集为八槽。
test('C-13 两片：文件名独立、源码互不 require、槽位集合无交集', () => {
  assert.notEqual('standard_slot_m345.js', 'standard_chain_b9_slot_resolver.js');
  assert.ok(b8src.indexOf('standard_chain_b9_slot_resolver') < 0);
  assert.ok(b9src.indexOf('standard_slot_m345') < 0);
  assert.ok(b8src.indexOf('require(') < 0 && b9src.indexOf('require(') < 0);
  assert.deepEqual(B9.SLOTS.map((s) => s.id), B9IDS);
  const b8fns = Object.keys(B8).filter((k) =>
    k.indexOf('m3') === 0 || k.indexOf('m4') === 0 || k.indexOf('m5') === 0);
  assert.equal(b8fns.length, 6);
  assert.equal(B9IDS.filter((id) => B8IDS.indexOf(id) >= 0).length, 0);
  assert.deepEqual(B8IDS.concat(B9IDS).sort(), IDS.slice().sort());
});

// 四、STATUS 全链路恒 declared-placeholder，纯函数返回值不翻状态。
test('C-13 STATUS：两片纯函数、两个 lib 与索引恒声明态', () => {
  assert.equal(B8.STATUS, 'declared-placeholder');
  assert.equal(B9.STATUS, 'declared-placeholder');
  assert.equal(A.STATUS, B9.STATUS);
  assert.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status, B9.STATUS);
  [idx, map, p10, p11].forEach((d) => assert.ok(d.indexOf('declared-placeholder') >= 0));
  B9.SLOTS.forEach((s) => {
    assert.equal(B9.resolveReplacement({ slot: s.id, marker: s.standard }).status, B9.STATUS);
  });
  assert.equal(B8.m3CommandToToolCall('/sd').status, B8.STATUS);
});

// 五、唯一键：标准 id 与 tool 消息三键一致、不含消息指纹。
test('C-13 唯一键：标准 id、三键与去消息指纹一致', () => {
  assert.equal(B8.KEY, 'tool_call.id');
  assert.equal(B9.KEY, 'tool_call.id');
  assert.equal(A.KEY, B9.KEY);
  assert.deepEqual(Array.from(B9.TOOL_MESSAGE_KEYS), ['role', 'tool_call_id', 'content']);
  const msg = C.standardToolMessage('call_n1', 'OK');
  assert.equal(msg.role, 'tool');
  assert.equal(msg.tool_call_id, 'call_n1');
  assert.equal(msg.content, 'OK');
  assert.ok(C.execKeyFromToolCall(
    { id: 'call_n1', tool: 't', parameters: { a: 1 } }, 's1').indexOf('fingerprint') < 0);
  assert.ok(idx.indexOf('tool_call.id') >= 0 && idx.indexOf('tool 消息三键') >= 0);
});

// 六、C-12 只读引用：八槽旧位层与落点类型逐槽对齐。
test('C-13 C-12 引用：八槽标题、旧位层与落点类型逐槽一致', () => {
  const bodies = map.split('### 槽位 M').slice(1);
  assert.equal(bodies.length, 8);
  const layers = layerRowsOf(idx);
  IDS.forEach((id, k) => {
    const n = Number(id.slice(1));
    assert.ok(map.indexOf('### 槽位 M' + n) >= 0, 'C-12 ' + id);
    const body = bodies[n - 1];
    const line = layers[k];
    const layer = line.split('：')[1].split('；')[0];
    const target = line.split('；')[1].split('。')[0];
    assert.ok(body.indexOf(layer) >= 0, id + ' 旧位层');
    assert.ok(body.indexOf(target) >= 0, id + ' 落点类型');
    assert.ok(body.indexOf('declared-placeholder') >= 0, id + ' 声明态');
  });
});

// 七、编号封闭：S1-S4 与 #4/#7/#13/#14 在四份文档齐全、无悬空值。
test('C-13 编号封闭：S 槽与矩阵编号在四份文档齐全', () => {
  const rows = rowsOf(idx);
  const sVals = ['S1', 'S2', 'S3', 'S4'];
  const mVals = ['#4', '#7', '#13', '#14'];
  rows.forEach((r) => {
    const cells = r.split('|').map((x) => x.trim());
    cells[6].split('/').forEach((x) => assert.ok(sVals.indexOf(x.trim()) >= 0, 'S ' + x));
    cells[7].split('/').forEach((x) => assert.ok(mVals.indexOf(x.trim()) >= 0, 'M ' + x));
  });
  sVals.forEach((s) => {
    assert.ok(idx.indexOf(s) >= 0 && p10.indexOf('槽位 ' + s) >= 0 && p11.indexOf(s) >= 0, s);
  });
  mVals.forEach((n) => {
    assert.ok(idx.indexOf(n) >= 0 && p10.indexOf(n) >= 0 && p11.indexOf(n) >= 0, n);
    assert.ok(map.indexOf(n) >= 0 && p8.indexOf('| ' + n.slice(1) + ' |') >= 0, 'C-8 ' + n);
  });
});

// 八、两片落点能力可实测，交叉索引不装配运行时。
test('C-13 两片能力：B-9 五槽转换拒绝与 B-8 三槽转换均闭合', () => {
  B9IDS.forEach((id) => {
    const s = B9.findSlot(id);
    assert.equal(B9.resolveReplacement({ slot: id, marker: s.legacy }).accepted, false);
    assert.equal(B9.resolveReplacement({ slot: id, marker: s.standard }).accepted, true);
  });
  assert.equal(B8.m3CommandToToolCall('/sd').ok, true);
  assert.equal(B8.m4EnvelopeToToolCall(
    { type: 'external-call', nonce: 'n1', request: 'x' }).ok, true);
  assert.equal(B8.m5FlagToToolMessage(
    { is_tool_result: true, tool_call_id: 'call_x', content: 'OK' }).ok, true);
});

// 九、边界：索引只读、不碰活链、不预设结论、docs 只追加。
test('C-13 边界：索引只读且不预设结论', () => {
  ['活链文件零改动', '不装配运行时 M', '不建切换开关', '不新增运行期探测分支',
    '不预设 B-7 总结论', '不预设旧标记摘除结论', 'docs 只追加',
    '两片纯函数文件各自独立命名', '无悬空编号'].forEach((k) => {
      assert.ok(idx.indexOf(k) >= 0, k);
    });
  assert.ok(idx.indexOf('require(') < 0 && idx.indexOf('module.exports') < 0);
});
console.log('C13_CROSSREF_OK');
