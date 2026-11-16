/*
 * B-15 buildCard 单点边界反查夹具（零代码改动的只读取证片，dispatcher-20261116T222202-585cde）。
 * 只读 require 已合入 adapter / contract（node 分支）；契约 .md 与活链文件按字符码 10 切行、
 * 普通 indexOf / split 反查（零反斜杠零正则）。
 * 覆盖：返回形状恰三键、缺 call 与缺 id 归一、标准键原样回显、falsy 归一与 truthy 直通、
 * 同 / 异入参回显不比较不排序、幂等每次新对象、C-9 / C-14 / C-15 / b10 四处标注对拍、
 * 运行期零调用方与唯一定义导出、STATUS / EXECUTE_STATUS / KEY 常量与 contract 键映射纯函数。
 * 新增被测 JS 源 0；无 fs 写 / shell / 网络；不装配 M、不建开关、不切活链、不翻 STATUS。
 * require 头部序按 A-10 与同族差异化归零（fs / assert / adapter / contract / path / test）。
 */
'use strict';
const b15Fs = require('node:fs');
const b15Assert = require('node:assert/strict');
const b15Adapter = require('../../../extend/lib/standard_chain_adapter.js');
const b15Contract = require('../../../extend/lib/standard_chain_contract.js');
const b15Path = require('node:path');
const b15Test = require('node:test');
const LF = String.fromCharCode(10);
const b15Root = b15Path.resolve(__dirname, '../../..');
function b15Read(rel) { return b15Fs.readFileSync(b15Path.join(b15Root, rel), 'utf8'); }
function b15Has(text, needle) { return text.indexOf(needle) >= 0; }
function b15Count(text, needle) { return text.split(needle).length - 1; }
function b15Rows(text, head) { return text.split(LF).filter(function (l) { return l.indexOf(head) === 0; }); }
const b15AdapterSrc = b15Read('extend/lib/standard_chain_adapter.js');
const b15ContractSrc = b15Read('extend/lib/standard_chain_contract.js');
const b15BoundaryDoc = b15Read('extend/lib/standard_chain_boundary_contract.md');
const b15TableDoc = b15Read('extend/lib/standard_chain_c14_signature_table.md');
const b15C15Doc = b15Read('docs/c15-s2-remaining-surface-inventory.md');
const b15B10Doc = b15Read('docs/b10-removal-readiness-report.md');
// 五文档与两 lib 快照至此；以下全部只读反查，不写不改不搬。

b15Test.test('B15-1 返回形状恰三键 by / id / status', function () {
  const out = b15Adapter.buildCard({ id: 'call_n1' });
  const keys = Object.keys(out).sort();
  b15Assert.deepEqual(keys, ['by', 'id', 'status']);
  b15Assert.equal(out.by, b15Adapter.KEY);
  b15Assert.equal(out.status, b15Adapter.STATUS);
  b15Assert.equal(out.id, 'call_n1');
});

b15Test.test('B15-2 缺 call（null / undefined）归一 id: null 且不抛错', function () {
  b15Assert.doesNotThrow(function () { b15Adapter.buildCard(null); });
  b15Assert.equal(b15Adapter.buildCard(null).id, null);
  b15Assert.equal(b15Adapter.buildCard(undefined).id, null);
  b15Assert.equal(Object.keys(b15Adapter.buildCard(null)).length, 3);
});

b15Test.test('B15-3 缺 id 回落 null 不生成替代 id', function () {
  b15Assert.equal(b15Adapter.buildCard({}).id, null);
  b15Assert.equal(b15Adapter.buildCard({ id: null }).id, null);
  b15Assert.equal(b15Adapter.buildCard({ id: undefined }).id, null);
  b15Assert.equal(b15Adapter.buildCard({ name: 'write_to_file' }).id, null);
});

b15Test.test('B15-4 标准键原样保留，不校验 function.name 不落消息树', function () {
  const out = b15Adapter.buildCard({ id: 'call_n1', function: { name: 'write_to_file' } });
  b15Assert.equal(out.id, 'call_n1');
  b15Assert.equal(out.by, 'tool_call.id');
  b15Assert.equal(out.status, 'declared-placeholder');
  b15Assert.equal(Object.keys(out).length, 3);
  b15Assert.equal(Object.keys(out).join(',').indexOf('function'), -1);
});

b15Test.test('B15-5 falsy id 归一 null 与 truthy 原样直通（归一语义实证）', function () {
  b15Assert.equal(b15Adapter.buildCard({ id: '' }).id, null);
  b15Assert.equal(b15Adapter.buildCard({ id: 0 }).id, null);
  b15Assert.equal(b15Adapter.buildCard({ id: false }).id, null);
  const idObj = { nonce: 'n1' };
  const out = b15Adapter.buildCard({ id: idObj });
  b15Assert.strictEqual(out.id, idObj);
  b15Assert.equal(b15Adapter.buildCard({ id: 'call_x' }).id, 'call_x');
});

b15Test.test('B15-6 同 / 异入参原样回显不吞并不比较不排序不合并', function () {
  const a = b15Adapter.buildCard({ id: 'call_b' });
  const b = b15Adapter.buildCard({ id: 'call_a' });
  b15Assert.equal(a.id, 'call_b');
  b15Assert.equal(b.id, 'call_a');
  const same = b15Adapter.buildCard({ id: 'call_n1' });
  b15Assert.equal(same.id, 'call_n1');
  b15Assert.equal(Object.keys(same).length, 3);
});

b15Test.test('B15-7 幂等每次返回新对象且逐字段深相等', function () {
  const first = b15Adapter.buildCard({ id: 'call_n1' });
  const second = b15Adapter.buildCard({ id: 'call_n1' });
  b15Assert.notEqual(first, second);
  b15Assert.deepEqual(first, second);
});

// C-9 对拍：第一节边界段三行 + 说明行 + 第二节状态行 + G1-G4 全量串。
b15Test.test('B15-8 C-9 边界段 / 状态行 / 说明行 / G1-G4 逐串对拍', function () {
  b15Assert.equal(b15Rows(b15BoundaryDoc, '### 2. buildCard(call)').length, 1);
  b15Assert.ok(b15Has(b15BoundaryDoc, '| `buildCard(null)` | `id: null` | 缺 call 不抛错 |'));
  b15Assert.ok(b15Has(b15BoundaryDoc, '| `buildCard({})` / 缺 `id` | `id: null` | 缺 id 回落 null，不生成替代 id |'));
  b15Assert.ok(b15Has(b15BoundaryDoc, "| `buildCard({ id: 'call_n1' })` | `id: 'call_n1'` | 标准键原样保留 |"));
  b15Assert.ok(b15Has(b15BoundaryDoc, '说明：不校验 `function.name`、不把卡片落到消息树、不触发建卡流程。'));
  b15Assert.equal(b15Rows(b15BoundaryDoc, '| buildCard | declared-placeholder |').length, 1);
  b15Assert.ok(b15Has(b15BoundaryDoc, 'G1 **STATUS 恒为 `declared-placeholder`**'));
  b15Assert.ok(b15Has(b15BoundaryDoc, 'G2 **唯一键**：标准 `tool_call.id`'));
  b15Assert.ok(b15Has(b15BoundaryDoc, 'G3 **异常输入不抛错**'));
  b15Assert.ok(b15Has(b15BoundaryDoc, 'G4 **刷新恢复键语义**'));
});

// C-14 对拍：第二节签名行 / 六段接口名两行 / 第六节零 buildCard。
b15Test.test('B15-9 C-14 签名行 / 六段接口名行 / 第六节零 buildCard 对拍', function () {
  b15Assert.equal(b15Rows(b15TableDoc, '| buildCard(call) |').length, 1);
  b15Assert.ok(b15Has(b15TableDoc, '| buildCard(call) | standard_chain_adapter.js | 返回 by=KEY、id、status=STATUS | 一致 | declared-placeholder |'));
  b15Assert.equal(b15Count(b15TableDoc, 'parse / buildCard / execute / reply / dedupe / restore'), 2);
  const lines = b15TableDoc.split(LF);
  let sec6Start = -1;
  for (let i = 0; i < lines.length; i += 1) {
    if (lines[i].indexOf('## 六') === 0) { sec6Start = i; break; }
  }
  b15Assert.ok(sec6Start >= 0);
  b15Assert.equal(b15Count(lines.slice(sec6Start).join(LF), 'buildCard'), 0);
});

// C-15 对拍：第一节 buildCard 行与第二节第 4 步行仅作标注对拍输入（任务书口径）。
b15Test.test('B15-10 C-15 第一节 buildCard 行与第二节第 4 步行标注对拍', function () {
  const rows1 = b15Rows(b15C15Doc, '| buildCard |');
  b15Assert.equal(rows1.length, 1);
  b15Assert.ok(b15Has(rows1[0], '{ by: KEY, id, status: STATUS }'));
  b15Assert.ok(b15Has(rows1[0], 'id 缺参回落 null'));
  const rows4 = b15Rows(b15C15Doc, '| 4 |');
  b15Assert.equal(rows4.length, 1);
  b15Assert.ok(b15Has(rows4[0], 'standard_chain_adapter.js buildCard'));
  b15Assert.ok(b15Has(rows4[0], 'standard_chain_contract.js makeToolCallId'));
  b15Assert.ok(b15Has(rows4[0], 'buildCard 仍 declared-placeholder 回显'));
  b15Assert.ok(b15Has(rows4[0], '05g_cards.js'));
  b15Assert.ok(b15Has(rows4[0], '_translateToolCalls'));
});

// b10 对拍 + 运行期零调用方：就绪度表零 buildCard 字样；四探针串 59 文件零命中。
b15Test.test('B15-11 b10 零 buildCard / 运行期零调用方 / 唯一定义导出', function () {
  b15Assert.equal(b15Count(b15B10Doc, 'buildCard'), 0);
  b15Assert.ok(b15Has(b15B10Doc, '| S2 #7 tool_calls 意图执行'));
  b15Assert.equal(b15Count(b15AdapterSrc, 'function buildCard('), 1);
  b15Assert.equal(b15Count(b15AdapterSrc, 'buildCard: buildCard'), 1);
  b15Assert.equal(b15Count(b15AdapterSrc, 'buildCard'), 3);
  b15Assert.ok(b15Has(b15AdapterSrc, 'window.AIMirrorStandardChainAdapter = adapter;'));
  b15Assert.ok(b15Has(b15AdapterSrc, 'module.exports = adapter;'));
  const partsDir = b15Path.join(b15Root, 'extend/dialog/parts');
  const names = b15Fs.readdirSync(partsDir).filter(function (n) { return n.slice(-3) === '.js'; });
  b15Assert.equal(names.length, 56);
  const targets = names.map(function (n) { return b15Path.join(partsDir, n); });
  targets.push(b15Path.join(b15Root, 'extend/lib/standard_chain_adapter.js'));
  targets.push(b15Path.join(b15Root, 'extend/lib/standard_chain_contract.js'));
  targets.push(b15Path.join(b15Root, 'extend/dialog/dialog.html'));
  const probes = ['AIMirrorStandardChainAdapter.buildCard', 'adapter.buildCard(', 'AD.buildCard(', 'Adapter.buildCard('];
  targets.forEach(function (p) {
    const text = b15Fs.readFileSync(p, 'utf8');
    probes.forEach(function (s) {
      b15Assert.equal(text.indexOf(s), -1, 'runtime caller hit: ' + s + ' in ' + p);
    });
  });
});

// 常量作用域对拍 + contract 键映射纯函数：STATUS / EXECUTE_STATUS / KEY 与 makeToolCallId。
b15Test.test('B15-12 STATUS / EXECUTE_STATUS / KEY 常量与 contract 键映射纯函数对拍', function () {
  b15Assert.equal(b15Adapter.STATUS, 'declared-placeholder');
  b15Assert.equal(b15Adapter.EXECUTE_STATUS, 'implemented-S2-step5');
  b15Assert.equal(b15Adapter.KEY, 'tool_call.id');
  b15Assert.equal(b15Count(b15AdapterSrc, "var STATUS = 'declared-placeholder';"), 1);
  b15Assert.equal(b15Count(b15AdapterSrc, "var EXECUTE_STATUS = 'implemented-S2-step5';"), 1);
  b15Assert.equal(b15Count(b15AdapterSrc, "var KEY = 'tool_call.id';"), 1);
  b15Assert.equal(b15Count(b15AdapterSrc, 'EXECUTE_STATUS'), 6);
  const out = b15Adapter.buildCard({ id: 'call_n1' });
  b15Assert.equal(out.status, b15Adapter.STATUS);
  b15Assert.notEqual(out.status, b15Adapter.EXECUTE_STATUS);
  b15Assert.equal(b15Contract.PREFIX, 'call_');
  b15Assert.equal(b15Contract.makeToolCallId('n1'), 'call_n1');
  b15Assert.equal(b15Count(b15ContractSrc, 'function makeToolCallId('), 1);
  b15Assert.equal(b15Count(b15ContractSrc, "var PREFIX = 'call_';"), 1);
});
