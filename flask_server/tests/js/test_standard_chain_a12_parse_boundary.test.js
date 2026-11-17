
/*
 * A-12 parse 单点边界反查夹具（零代码改动的只读取证片，dispatcher-20261116T103235-72e379）。
 * 只读 require 已合入 adapter（node 分支）；契约 .md / 余面判定 / 就绪度报告与活链文件
 * fs 只读反查，按字符码 10 切行、普通 indexOf / split（零反斜杠零正则）。
 * 覆盖：导出面、返回形状恰三键、block 引用回显、缺参归一 null、空 block 真值原样回显、
 * truthy 直通与不抛错、幂等新对象、C-9 / C-14 / C-15 / b10 四处标注对拍、
 * 运行期唯一定义与零调用方、JSON.parse 计数恒等。
 * 新增被测 JS 源 0；无 fs 写 / shell / 网络；不装配 M、不建开关、不切活链、不翻 STATUS。
 */
'use strict';
const scDoc = require('./_standard_chain_doc_snippets.js');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const test = require('node:test');
const AD = require('../../../extend/lib/standard_chain_adapter.js');
const LF = String.fromCharCode(10);
const repoRoot = path.resolve(__dirname, '../../..');
function read(rel) { return fs.readFileSync(path.join(repoRoot, rel), 'utf8'); }
function has(text, needle) { return text.indexOf(needle) >= 0; }
function row(text, head) { return text.split(LF).filter((l) => l.indexOf(head) === 0); }
function cnt(text, needle) { return text.split(needle).length - 1; }
const adapterSrc = read('extend/lib/standard_chain_adapter.js');
const contractSrc = read('extend/lib/standard_chain_contract.js');
const boundary = read('extend/lib/standard_chain_boundary_contract.md');
const table = read('extend/lib/standard_chain_c14_signature_table.md');
const c15 = scDoc.doc('c15');
const b10 = scDoc.doc('b10');
const executePart = read('extend/dialog/parts/06_execute.js');
const parsePart = read('extend/dialog/parts/05f_parse.js');
const dataPart = read('extend/dialog/parts/00_data.js');
const cardsPart = read('extend/dialog/parts/05g_cards.js');
const sigPart = read('extend/dialog/parts/05j_card_sig.js');
const dialogHtml = read('extend/dialog/dialog.html');
const liveFiles = [executePart, parsePart, dataPart, cardsPart, sigPart, dialogHtml];
const FLAT = { by: 'tool_call.id', block: null, status: 'declared-placeholder' };

// 一、导出面：parse 在六段导出内；KEY / STATUS / EXECUTE_STATUS 三个常量不漂移。
test('A-12 导出面：parse 在六段导出内且三个常量不漂移', () => {
  assert.equal(typeof AD.parse, 'function');
  const SIX_SEGMENTS = ['parse', 'buildCard', 'execute', 'reply', 'dedupe', 'restore'];
  assert.equal(SIX_SEGMENTS.every(function (name) { return typeof AD[name] === 'function'; }), true);
  assert.equal(AD.EXECUTE_STATUS, 'implemented-S2-step5');
  assert.equal(AD.STATUS, 'declared-placeholder');
  assert.equal(AD.KEY, 'tool_call.id');
});

// 二、返回形状：code 块入参恰三键，不产出 tool_calls、不读 code。
test('A-12 形状：code 块入参恰三键且不读 code', () => {
  const out = AD.parse({ type: 'code', code: 'AIMIRROR-A12' });
  assert.deepEqual(Object.keys(out).sort(), ['block', 'by', 'status']);
  assert.equal(out.by, 'tool_call.id');
  assert.equal(out.status, 'declared-placeholder');
  assert.deepEqual(out.block, { type: 'code', code: 'AIMIRROR-A12' });
  assert.equal(Object.prototype.hasOwnProperty.call(out, 'tool_calls'), false);
  assert.equal(Object.prototype.hasOwnProperty.call(out, 'call'), false);
});

// 三、引用回显与入参不改写：out.block 与入参同一引用，adapter 不改写入参。
test('A-12 引用回显：同一引用且入参不被改写', () => {
  const block = { type: 'code', code: 'REF', nested: { k: 1 } };
  const out = AD.parse(block);
  assert.equal(out.block, block);
  assert.deepEqual(block, { type: 'code', code: 'REF', nested: { k: 1 } });
  assert.equal(Object.keys(block).length, 3);
});

// 四、缺参归一：null / undefined / 0 / 空串 / false 一律 block null，深等于扁平形状。
test('A-12 缺参归一：falsy 入参回落 null 深等于扁平形状', () => {
  [null, undefined, 0, '', false].forEach((v) => {
    assert.deepEqual(AD.parse(v), FLAT);
  });
});

// 五、空 block 真值：{} 原样回显、不补字段、不归一为 null。
test('A-12 空 block 真值：空对象原样回显不补字段', () => {
  const empty = {};
  const out = AD.parse(empty);
  assert.equal(out.block, empty);
  assert.deepEqual(out, { by: 'tool_call.id', block: {}, status: 'declared-placeholder' });
  assert.equal(Object.keys(out.block).length, 0);
});

// 六、truthy 直通与不抛错：真值入参原样引用回显；幂等新对象；任意类型入参不抛错。
test('A-12 不抛错与幂等：truthy 直通、重复调用等价不共享引用', () => {
  [42, 'x', true, [], { any: 1 }].forEach((v) => {
    const out = AD.parse(v);
    assert.equal(out.block, v);
    assert.equal(out.by, 'tool_call.id');
    assert.equal(out.status, 'declared-placeholder');
  });
  const block = { type: 'code', code: 'same' };
  const first = AD.parse(block);
  const second = AD.parse(block);
  assert.notEqual(first, second);
  assert.deepEqual(first, second);
  assert.equal(first.block, block);
  [NaN, {}, 3.14].forEach((v) => { assert.doesNotThrow(() => AD.parse(v)); });
});

// 七、C-9 对拍：第一节 parse 段四行边界、说明行、G1 / G2 / G3、第二节状态行逐格在文。
test('A-12 C-9 对拍：parse 段四行边界与状态行逐格在文', () => {
  assert.ok(has(boundary, '### 1. parse(block)'));
  assert.equal(row(boundary, '| `parse(null)` |').length, 1);
  assert.equal(row(boundary, '| `parse(undefined)` |').length, 1);
  assert.equal(row(boundary, '| `parse({})`').length, 1);
  assert.equal(row(boundary, '| `parse({ type:').length, 1);
  assert.ok(has(boundary, '占位期不解析、不校验 type'));
  assert.ok(has(boundary, 'G1 **STATUS 恒为 `declared-placeholder`**'));
  assert.ok(has(boundary, 'G2 **唯一键**'));
  assert.ok(has(boundary, 'G3 **异常输入不抛错**'));
  const statusRows = row(boundary, '| parse | declared-placeholder |');
  assert.equal(statusRows.length, 1);
  assert.ok(has(statusRows[0], '`tool_call.id` + tool 三键'));
  assert.ok(has(statusRows[0], '| n/a |'));
  assert.ok(has(statusRows[0], '| 否 |'));
});

// 八、C-14 对拍：第二节 parse 签名行逐格一致；第六节 B-12 只追加登记不含 parse 字样。
test('A-12 C-14 对拍：签名行一致且第六节无 parse 字样', () => {
  const rows = row(table, '| parse(block) |');
  assert.equal(rows.length, 1);
  assert.ok(has(rows[0], 'standard_chain_adapter.js'));
  assert.ok(has(rows[0], '返回 by=KEY、block、status=STATUS'));
  assert.ok(has(rows[0], '| 一致 |'));
  assert.ok(has(rows[0], 'declared-placeholder'));
  assert.ok(has(table, '## 六、execute 段实装登记'));
  const sec6 = table.slice(table.indexOf('## 六、'));
  assert.equal(sec6.indexOf('parse') >= 0, false);
});

// 九、C-15 / b10 对拍：逐面基线行与就绪度行在文（b10 为 34e6029 历史快照，差异登记不改写）。
test('A-12 C-15 / b10 对拍：逐面基线与 S2 行在文', () => {
  const r15 = row(c15, '| parse |');
  assert.equal(r15.length, 1);
  assert.ok(has(r15[0], '{ by: KEY, block, status: STATUS }'));
  assert.ok(has(r15[0], '空 block 原样回显'));
  assert.ok(has(r15[0], '| 一致 |'));
  const rb10 = row(b10, '| S2 #7 tool_calls 意图执行 |');
  assert.equal(rb10.length, 1);
  assert.ok(has(rb10[0], 'declared-placeholder'));
});

// 十、运行期取证：源内唯一定义、活链零 adapter.parse 调用方、JSON.parse 计数恒等、contract 无 parse 面。
test('A-12 运行期取证：唯一定义且活链零调用方', () => {
  assert.equal(cnt(adapterSrc, 'function parse('), 1);
  assert.equal(cnt(adapterSrc, '.parse('), 0);
  assert.equal(cnt(adapterSrc, 'JSON.parse('), 0);
  assert.equal(cnt(contractSrc, 'parse'), 0);
  ['AD.parse(', 'Adapter.parse(', 'AIMirrorStandardChainAdapter.parse', 'adapter.parse'].forEach(function (nd) {
    liveFiles.forEach(function (src) { assert.equal(cnt(src, nd), 0); });
  });
  liveFiles.forEach(function (src) { assert.equal(cnt(src, '.parse('), cnt(src, 'JSON.parse(')); });
  assert.equal(cnt(parsePart, 'JSON.parse('), 5);
  assert.equal(cnt(dataPart, 'JSON.parse('), 1);
  assert.equal(cnt(cardsPart, 'JSON.parse('), 1);
  assert.ok(has(dialogHtml, 'standard_chain_adapter.js'));
});
