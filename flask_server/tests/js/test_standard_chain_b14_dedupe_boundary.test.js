/*
 * B-14 dedupe 单点边界反查夹具（零代码改动的只读取证片，dispatcher-20261116T190823-edaafe）。
 * 只读 require 已合入 adapter（node 分支）；契约 .md 与活链文件按字符码 10 切行、
 * 普通 indexOf / split 反查（零反斜杠零正则）。
 * 覆盖：返回形状恰四键、同 id 不吞并、异 id 不排序、null 侧归一、falsy 归一与
 * truthy 直通、幂等新对象、C-9 / C-14 / C-15 / b10 四处标注对拍、运行期零调用方
 * 与唯一定义导出、STATUS / EXECUTE_STATUS / KEY 常量作用域。
 * 新增被测 JS 源 0；无 fs 写 / shell / 网络；不装配 M、不建开关、不切活链、不翻 STATUS。
 */
'use strict';
const scDoc = require('./_standard_chain_doc_snippets.js');
const b14Fs = require('node:fs');
const b14Path = require('node:path');
const b14Test = require('node:test');
const b14Assert = require('node:assert/strict');
const b14Adapter = require('../../../extend/lib/standard_chain_adapter.js');
const LF = String.fromCharCode(10);
const b14Root = b14Path.resolve(__dirname, '../../..');
function b14Read(rel) { return b14Fs.readFileSync(b14Path.join(b14Root, rel), 'utf8'); }
function b14Has(text, needle) { return text.indexOf(needle) >= 0; }
function b14Count(text, needle) { return text.split(needle).length - 1; }
function b14Rows(text, head) { return text.split(LF).filter(function (l) { return l.indexOf(head) === 0; }); }
const b14AdapterSrc = b14Read('extend/lib/standard_chain_adapter.js');
const b14BoundaryDoc = b14Read('extend/lib/standard_chain_boundary_contract.md');
const b14TableDoc = b14Read('extend/lib/standard_chain_c14_signature_table.md');
const b14C15Doc = scDoc.doc('c15');
const b14B10Doc = scDoc.doc('b10');
// 四文档快照至此；以下全部只读反查，不写不改不搬。

b14Test.test('B14-1 返回形状恰四键 by / a / b / status', function () {
  const out = b14Adapter.dedupe('call_a', 'call_b');
  const keys = Object.keys(out).sort();
  b14Assert.deepEqual(keys, ['a', 'b', 'by', 'status']);
  b14Assert.equal(out.by, b14Adapter.KEY);
  b14Assert.equal(out.status, b14Adapter.STATUS);
  b14Assert.equal(out.a, 'call_a');
  b14Assert.equal(out.b, 'call_b');
});

b14Test.test('B14-2 同 call_nonce id 双侧原样回显不吞并', function () {
  const out = b14Adapter.dedupe('call_n1', 'call_n1');
  b14Assert.equal(out.a, 'call_n1');
  b14Assert.equal(out.b, 'call_n1');
  b14Assert.equal(Object.keys(out).length, 4);
});

b14Test.test('B14-3 异 id 原样回显不比较不排序不去重', function () {
  const out = b14Adapter.dedupe('call_b', 'call_a');
  b14Assert.equal(out.a, 'call_b');
  b14Assert.equal(out.b, 'call_a');
});

b14Test.test('B14-4 null 入参缺失侧归一 null 且不抛错', function () {
  b14Assert.doesNotThrow(function () { b14Adapter.dedupe(null, null); });
  const both = b14Adapter.dedupe(null, null);
  b14Assert.equal(both.a, null);
  b14Assert.equal(both.b, null);
  const left = b14Adapter.dedupe(null, 'call_a');
  b14Assert.equal(left.a, null);
  b14Assert.equal(left.b, 'call_a');
});

b14Test.test('B14-5 falsy 侧归一 null 与 truthy 原样直通（缺失归一语义实证）', function () {
  b14Assert.equal(b14Adapter.dedupe(undefined, 'call_a').a, null);
  b14Assert.equal(b14Adapter.dedupe('', 'call_a').a, null);
  b14Assert.equal(b14Adapter.dedupe(0, 'call_a').a, null);
  b14Assert.equal(b14Adapter.dedupe(false, 'call_a').a, null);
  // 真值侧（含空对象）按原引用直通：归一只针对 falsy。
  const obj = { id: 'call_x' };
  const out = b14Adapter.dedupe(obj, 'call_y');
  b14Assert.strictEqual(out.a, obj);
});

b14Test.test('B14-6 幂等每次返回新对象且逐字段深相等', function () {
  const first = b14Adapter.dedupe('call_a', 'call_b');
  const second = b14Adapter.dedupe('call_a', 'call_b');
  b14Assert.notEqual(first, second);
  b14Assert.deepEqual(first, second);
});

// C-9 对拍：第五节边界表 + 第二节状态行 + G1-G4 全量串。
b14Test.test('B14-7 C-9 第五节边界段 / 状态行 / G1-G4 逐串对拍', function () {
  b14Assert.equal(b14Rows(b14BoundaryDoc, '### 5. dedupe').length, 1);
  b14Assert.equal(b14Rows(b14BoundaryDoc, '| dedupe | declared-placeholder |').length, 1);
  b14Assert.ok(b14Has(b14BoundaryDoc, '| 同 `call_<nonce>` id'));
  b14Assert.ok(b14Has(b14BoundaryDoc, "（`'call_n1','call_n1'`） | `a` / `b` 原样回显 | 占位期不做判重决策、不吞并 |"));
  b14Assert.ok(b14Has(b14BoundaryDoc, "| 不同 id（`'call_a','call_b'`） |"));
  b14Assert.ok(b14Has(b14BoundaryDoc, '`a` / `b` 原样回显 | 不比较、不排序、不去重 |'));
  b14Assert.ok(b14Has(b14BoundaryDoc, "| null 入参（`(null,null)` / `(null,'call_a')`） |"));
  b14Assert.ok(b14Has(b14BoundaryDoc, '| 缺失侧回落 `null` | 不抛错 |'));
  b14Assert.ok(b14Has(b14BoundaryDoc, '说明：唯一键标准下「同 id 即同一调用」的判定留给后续实装'));
  b14Assert.ok(b14Has(b14BoundaryDoc, 'G1 **STATUS 恒为 `declared-placeholder`**'));
  b14Assert.ok(b14Has(b14BoundaryDoc, 'G2 **唯一键**：标准 `tool_call.id`'));
  b14Assert.ok(b14Has(b14BoundaryDoc, 'G3 **异常输入不抛错**'));
  b14Assert.ok(b14Has(b14BoundaryDoc, 'G4 **刷新恢复键语义**'));
});

// C-14 对拍：签名行 / 六段接口名两行 / 第六节零 dedupe。
b14Test.test('B14-8 C-14 签名行 / 六段接口名行 / 第六节零 dedupe 对拍', function () {
  b14Assert.equal(b14Rows(b14TableDoc, '| dedupe(a,b) |').length, 1);
  b14Assert.ok(b14Has(b14TableDoc, '| dedupe(a,b) | standard_chain_adapter.js | 返回 by=KEY、a、b、status=STATUS | 一致 | declared-placeholder |'));
  b14Assert.equal(b14Count(b14TableDoc, 'parse / buildCard / execute / reply / dedupe / restore'), 2);
  const lines = b14TableDoc.split(LF);
  let sec6Start = -1;
  for (let i = 0; i < lines.length; i += 1) {
    if (lines[i].indexOf('## 六') === 0) { sec6Start = i; break; }
  }
  b14Assert.ok(sec6Start >= 0);
  b14Assert.equal(b14Count(lines.slice(sec6Start).join(LF), 'dedupe'), 0);
});

// C-15 对拍：第 7 行仅取前端 dedupe 声明态标注（任务书口径）。
b14Test.test('B14-9 C-15 第 7 行仅取前端 dedupe 声明态标注对拍', function () {
  const rows = b14Rows(b14C15Doc, '| 7 |');
  b14Assert.equal(rows.length, 1);
  const row7 = rows[0];
  b14Assert.ok(b14Has(row7, 'adapter.dedupe'));
  b14Assert.ok(b14Has(row7, '前端 dedupe 仍声明态'));
  b14Assert.ok(b14Has(row7, '00_data.js'));
  b14Assert.ok(b14Has(row7, '05j_card_sig.js'));
  b14Assert.ok(b14Has(row7, 'pending_tool_calls'));
});

// b10 对拍：就绪度表零 dedupe 字样，S2 行原样在文。
b14Test.test('B14-10 b10 就绪度表零 dedupe 单列槽对拍', function () {
  b14Assert.equal(b14Count(b14B10Doc, 'dedupe'), 0);
  b14Assert.ok(b14Has(b14B10Doc, '| S2 #7 tool_calls 意图执行'));
});

// 零调用方对拍：56 份 parts + 两 lib + dialog.html 四探针串全零。
b14Test.test('B14-11 运行期零调用方与唯一定义导出', function () {
  b14Assert.equal(b14Count(b14AdapterSrc, 'function dedupe('), 1);
  b14Assert.equal(b14Count(b14AdapterSrc, 'dedupe: dedupe'), 1);
  b14Assert.equal(b14Count(b14AdapterSrc, 'dedupe'), 3);
  b14Assert.ok(b14Has(b14AdapterSrc, 'window.AIMirrorStandardChainAdapter = adapter;'));
  b14Assert.ok(b14Has(b14AdapterSrc, 'module.exports = adapter;'));
  const partsDir = b14Path.join(b14Root, 'extend/dialog/parts');
  const names = b14Fs.readdirSync(partsDir).filter(function (n) { return n.slice(-3) === '.js'; });
  b14Assert.equal(names.length, 56);
  const targets = names.map(function (n) { return b14Path.join(partsDir, n); });
  targets.push(b14Path.join(b14Root, 'extend/lib/standard_chain_adapter.js'));
  targets.push(b14Path.join(b14Root, 'extend/lib/standard_chain_contract.js'));
  targets.push(b14Path.join(b14Root, 'extend/dialog/dialog.html'));
  const probes = ['AIMirrorStandardChainAdapter.dedupe', 'adapter.dedupe(', 'AD.dedupe(', 'Adapter.dedupe('];
  targets.forEach(function (p) {
    const text = b14Fs.readFileSync(p, 'utf8');
    probes.forEach(function (s) {
      b14Assert.equal(text.indexOf(s), -1, 'runtime caller hit: ' + s + ' in ' + p);
    });
  });
});

// 常量作用域对拍：STATUS / EXECUTE_STATUS / KEY 三常量与返回 status 取值。
b14Test.test('B14-12 STATUS / EXECUTE_STATUS / KEY 常量与作用域对拍', function () {
  b14Assert.equal(b14Adapter.STATUS, 'declared-placeholder');
  b14Assert.equal(b14Adapter.EXECUTE_STATUS, 'implemented-S2-step5');
  b14Assert.equal(b14Adapter.KEY, 'tool_call.id');
  b14Assert.equal(b14Count(b14AdapterSrc, "var STATUS = 'declared-placeholder';"), 1);
  b14Assert.equal(b14Count(b14AdapterSrc, "var EXECUTE_STATUS = 'implemented-S2-step5';"), 1);
  b14Assert.equal(b14Count(b14AdapterSrc, "var KEY = 'tool_call.id';"), 1);
  const out = b14Adapter.dedupe('call_a', 'call_b');
  b14Assert.equal(out.status, b14Adapter.STATUS);
  b14Assert.notEqual(out.status, b14Adapter.EXECUTE_STATUS);
});
