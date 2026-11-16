/*
 * A-14 reply 单段声明函数边界反查夹具（零代码改动的只读取证片，
 * dispatcher-20261116T232427-ee3d1f）。
 * 只读 require 已合入 adapter（UMD node 分支）；四锚 .md 与活链九文件
 * 按字符码 10 切行、普通 indexOf / split 反查（零反斜杠零正则）。
 * 覆盖：唯一定义与导出、返回形状恰四键、role 硬编码、content 不回显、
 * tool_call_id 回显不吞、缺键归一、不抛错、truthy 不比较不排序、
 * 幂等新对象、falsy 归一与 truthy 直通、常量作用域、运行期四精确串
 * 零调用方与局部变量登记、四锚逐行对拍、报告自反。
 * 新增被测 JS 源 0；无 fs 写 / shell / 网络；不装配 M、不建开关、不切活链、不翻 STATUS。
 */
'use strict';

// 防重窗：require 序与 a11 / a12 / a13 / b14 家族差异化（assert 最前置、单 lib、a14 前缀别名）。
const a14Assert = require('node:assert/strict');
const a14Test = require('node:test');
const a14Fs = require('node:fs');
const a14Path = require('node:path');
const a14Adapter = require('../../../extend/lib/standard_chain_adapter.js');

const LF = String.fromCharCode(10);
const a14Root = a14Path.resolve(__dirname, '../../..');
const relOf = function (rel) { return a14Path.join(a14Root, rel); };
const readOf = function (rel) { return a14Fs.readFileSync(relOf(rel), 'utf8'); };
const hasStr = function (t, n) { return t.indexOf(n) >= 0; };
const cntOf = function (t, n) { return t.split(n).length - 1; };
const rowsOf = function (t, head) { return t.split(LF).filter(function (l) { return l.indexOf(head) === 0; }); };

const a14AdapterSrc = readOf('extend/lib/standard_chain_adapter.js');
const a14C9Doc = readOf('extend/lib/standard_chain_boundary_contract.md');
const a14C14Doc = readOf('extend/lib/standard_chain_c14_signature_table.md');
const a14C15Doc = readOf('docs/c15-s2-remaining-surface-inventory.md');
const a14B10Doc = readOf('docs/b10-removal-readiness-report.md');
const a14ReportDoc = readOf('docs/a14-reply-segment-inventory.md');
const a14LiveRels = [
  'extend/dialog/parts/06_execute.js',
  'extend/dialog/parts/05f_parse.js',
  'extend/dialog/parts/00_data.js',
  'extend/dialog/parts/05g_cards.js',
  'extend/dialog/parts/05j_card_sig.js',
  'extend/dialog/parts/05c_prompt.js',
  'extend/dialog/parts/01b_bridge.js',
  'extend/lib/translator.js',
  'extend/dialog/dialog.html'
];
const FLAT = { by: 'tool_call.id', role: 'tool', tool_call_id: null, status: 'declared-placeholder' };

// 文档快照至此；以下全部只读反查，不写不改

a14Test('A14-01 唯一定义与导出', () => {
  a14Assert.equal(cntOf(a14AdapterSrc, 'function reply('), 1);
  a14Assert.equal(hasStr(a14AdapterSrc, 'reply: reply,'), true);
  a14Assert.equal(typeof a14Adapter.reply, 'function');
  a14Assert.equal(cntOf(a14AdapterSrc, 'EXECUTE_STATUS'), 6);
});

a14Test('A14-02 返回形状恰四键', () => {
  const full = a14Adapter.reply({ role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
  a14Assert.equal(Object.keys(full).sort().join('|'), 'by|role|status|tool_call_id');
  a14Assert.equal(full.by, 'tool_call.id');
  a14Assert.equal(full.role, 'tool');
  a14Assert.equal(full.tool_call_id, 'call_n1');
  a14Assert.equal(full.status, 'declared-placeholder');
});

a14Test('A14-03 role 硬编码常量不回显入参', () => {
  for (const r of ['assistant', 'user', 'function', '', 42, null]) {
    a14Assert.equal(a14Adapter.reply({ role: r, tool_call_id: 'call_n1' }).role, 'tool');
  }
});

a14Test('A14-04 content 不回显', () => {
  const out = a14Adapter.reply({ role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
  a14Assert.equal(Object.keys(out).indexOf('content'), -1);
  a14Assert.equal(out.content, undefined);
});

a14Test('A14-05 tool_call_id 原样回显不吞', () => {
  a14Assert.equal(a14Adapter.reply({ tool_call_id: 'call_abc' }).tool_call_id, 'call_abc');
  const longId = 'call_000123456789abcdef';
  a14Assert.equal(a14Adapter.reply({ tool_call_id: longId }).tool_call_id, longId);
});

a14Test('A14-06 缺键归一 null', () => {
  for (const c of [null, undefined, {}, { role: 'tool' }]) {
    a14Assert.deepEqual(a14Adapter.reply(c), FLAT);
  }
});

a14Test('A14-07 非对象入参不抛错', () => {
  for (const c of ['x', 42, true, [1, 2]]) {
    a14Assert.doesNotThrow(function () { a14Adapter.reply(c); });
    a14Assert.deepEqual(a14Adapter.reply(c), FLAT);
  }
});
a14Test('A14-08 truthy 不比较不排序', () => {
  const r1 = a14Adapter.reply({ tool_call_id: 'call_b' });
  const r2 = a14Adapter.reply({ tool_call_id: 'call_a' });
  a14Assert.equal(r1.tool_call_id, 'call_b');
  a14Assert.equal(r2.tool_call_id, 'call_a');
  a14Assert.deepEqual(a14Adapter.reply({ tool_call_id: 'call_b' }), r1);
});

a14Test('A14-09 幂等且每次新对象', () => {
  const a = a14Adapter.reply({ tool_call_id: 'call_n1' });
  const b = a14Adapter.reply({ tool_call_id: 'call_n1' });
  a14Assert.deepEqual(a, b);
  a14Assert.equal(a === b, false);
});

a14Test('A14-10 falsy 归一与 truthy 直通', () => {
  for (const v of ['', 0, false]) {
    a14Assert.equal(a14Adapter.reply({ tool_call_id: v }).tool_call_id, null);
  }
  a14Assert.equal(a14Adapter.reply({ tool_call_id: 'call_n1' }).tool_call_id, 'call_n1');
  a14Assert.equal(a14Adapter.reply({}).tool_call_id, null);
});

a14Test('A14-11 常量作用域：STATUS / KEY / EXECUTE_STATUS', () => {
  a14Assert.equal(a14Adapter.STATUS, 'declared-placeholder');
  a14Assert.equal(a14Adapter.KEY, 'tool_call.id');
  a14Assert.equal(a14Adapter.EXECUTE_STATUS, 'implemented-S2-step5');
  const out = a14Adapter.reply({ tool_call_id: 'call_n1' });
  a14Assert.equal(out.status, a14Adapter.STATUS);
  a14Assert.equal(out.status === a14Adapter.EXECUTE_STATUS, false);
});
a14Test('A14-12 运行期四精确串零调用方与局部变量登记', () => {
  const strs = ['.reply(', 'adapter.reply', 'AIMirrorStandardChainAdapter.reply', 'function reply('];
  for (const rel of a14LiveRels) {
    const txt = readOf(rel);
    for (const s of strs) {
      a14Assert.equal(cntOf(txt, s), 0, rel + ' 不应含 ' + s);
    }
  }
  const picker = readOf('extend/content/06_picker.js');
  a14Assert.equal(cntOf(picker, 'function reply('), 0);
  a14Assert.equal(cntOf(picker, 'const reply = function'), 1);
  a14Assert.equal(cntOf(readOf('extend/dialog/parts/05g_cards.js'), 'no_reply'), 1);
  a14Assert.equal(cntOf(readOf('extend/dialog/parts/05e_quality.js'), 'code_only_reply'), 1);
});

a14Test('A14-13 四锚逐行对拍：C-9 / C-14 / C-15 / b10', () => {
  const c9r1 = rowsOf(a14C9Doc, '| 缺 `tool_call_id`');
  a14Assert.equal(c9r1.length, 1);
  a14Assert.equal(hasStr(c9r1[0], 'tool_call_id: null'), true);
  a14Assert.equal(hasStr(c9r1[0], "role: 'tool'"), true);
  const c9r2 = rowsOf(a14C9Doc, '| role 非 tool');
  a14Assert.equal(c9r2.length, 1);
  a14Assert.equal(hasStr(c9r2[0], '不回显入参 role、不抛错'), true);
  const c9r3 = rowsOf(a14C9Doc, '| 完整 `{ role');
  a14Assert.equal(c9r3.length, 1);
  a14Assert.equal(hasStr(c9r3[0], '不在返回形状内'), true);
  const c9st = rowsOf(a14C9Doc, '| reply |');
  a14Assert.equal(c9st.length, 1);
  a14Assert.equal(hasStr(c9st[0], 'declared-placeholder'), true);
  a14Assert.equal(hasStr(c9st[0], 'tool_call.id'), true);
  a14Assert.equal(hasStr(a14C9Doc, '- G1 **STATUS 恒为 `declared-placeholder`**'), true);
  a14Assert.equal(hasStr(a14C9Doc, '- G3 **异常输入不抛错**'), true);
  const c14r = rowsOf(a14C14Doc, '| reply(msg) |');
  a14Assert.equal(c14r.length, 1);
  a14Assert.equal(hasStr(c14r[0], 'by=KEY'), true);
  a14Assert.equal(hasStr(c14r[0], 'role=tool'), true);
  a14Assert.equal(hasStr(c14r[0], 'status=STATUS'), true);
  const c14t = rowsOf(a14C14Doc, '| 六段接口名 |');
  a14Assert.equal(c14t.length, 1);
  a14Assert.equal(hasStr(c14t[0], 'reply'), true);
  const c15r = rowsOf(a14C15Doc, '| reply |');
  a14Assert.equal(c15r.length, 1);
  a14Assert.equal(hasStr(c15r[0], 'role 硬编码常量'), true);
  a14Assert.equal(hasStr(c15r[0], 'content 不回显'), true);
  const c15s6 = rowsOf(a14C15Doc, '| 6 |');
  a14Assert.equal(c15s6.length >= 1, true);
  a14Assert.equal(hasStr(c15s6[0], 'adapter.reply'), true);
  a14Assert.equal(hasStr(c15s6[0], '装配仍占位'), true);
  a14Assert.equal(cntOf(a14B10Doc, '摘除任务书未下发') >= 2, true);
  a14Assert.equal(hasStr(a14B10Doc, '三项缺一不可'), true);
  a14Assert.equal(hasStr(a14B10Doc, 'S4 #14 旧标记摘除'), true);
  a14Assert.equal(cntOf(a14B10Doc, 'adapter.reply'), 0);
});

a14Test('A14-14 报告自反：七节齐全 + 差异登记 + 判态锚引用', () => {
  for (const head of ['## 一、取证范围与方法', '## 二、代码实况：adapter.reply 逐项钉死', '## 三、四锚逐行对拍', '## 四、差异登记（供分发方复核，不代拍板）', '## 五、结论', '## 六、边界与只追加记录', '## 七、验收实测（本机）']) {
    a14Assert.equal(hasStr(a14ReportDoc, head), true);
  }
  for (const item of ['a11 与本片同面复核关系', 'b10 报告无 adapter.reply 字样', '计数漂移', '06_picker.js const reply 局部函数', 'dispatcher-20261116T232427-ee3d1f', '19:45 dispatcher-20261115T194511-c92792', '不构成执行权迁移、不构成新前置、不构成实装授权']) {
    a14Assert.equal(hasStr(a14ReportDoc, item), true);
  }
});
