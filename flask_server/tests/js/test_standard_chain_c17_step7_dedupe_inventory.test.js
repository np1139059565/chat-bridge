/*
 * C-17 九步装配面第 7 步去重逐行取证反查夹具。
 * 只读 require 两个已合入 lib，按字符码 10 切行反查 C-15 / C-9 / C-14 / b10 /
 * 服务端 core 与路由 / 00_data / 05j_card_sig / adapter / 活链递归扫 / 本报告。
 * 覆盖：C-15 第 7 行六列、服务端 pending_tool_calls 配对链、adapter.dedupe 声明回显
 * 与运行期五精确串零调用方、00_data 镜像去重、05j 双查构型、C-9 / C-14 标注对拍、
 * b10 就绪度表、报告六节与复核输入边界。
 * 零反斜杠零正则，普通 indexOf 与 split；无 fs 写 / shell / 网络；新增被测 JS 源 0。
 * require 头部序按 A-10 与同族差异化归零。
 */
'use strict';
const c17Fs = require('node:fs');
const c17Test = require('node:test');
const c17Path = require('node:path');
const c17Assert = require('node:assert/strict');
const AdapterLib = require('../../../extend/lib/standard_chain_adapter.js');
const ContractLib = require('../../../extend/lib/standard_chain_contract.js');

const LF = String.fromCharCode(10);
const rootDir = c17Path.resolve(__dirname, '../../..');
function c17Read(rel) { return c17Fs.readFileSync(c17Path.join(rootDir, rel), 'utf8'); }
function c17Has(text, needle) { return text.indexOf(needle) >= 0; }
function c17Lines(text) { return text.split(LF); }
function c17Count(text, needle) { return text.split(needle).length - 1; }
const c15Doc = c17Read('docs/c15-s2-remaining-surface-inventory.md');
const boundaryDoc = c17Read('extend/lib/standard_chain_boundary_contract.md');
const tableDoc = c17Read('extend/lib/standard_chain_c14_signature_table.md');
const readinessDoc = c17Read('docs/b10-removal-readiness-report.md');
const matrixDoc = c17Read('extend/lib/standard_chain_field_matrix.md');
const corePy = c17Read('flask_server/core/chat_completions.py');
const chatApiPy = c17Read('flask_server/routes/chat_api.py');
const dataPart = c17Read('extend/dialog/parts/00_data.js');
const sigPart = c17Read('extend/dialog/parts/05j_card_sig.js');
const adapterSrc = c17Read('extend/lib/standard_chain_adapter.js');
const reportDoc = c17Read('docs/c17-s2-step7-dedupe-inventory.md');

// 一、C-15 第二节第 7 行六列在文（本片主锚）。
c17Test('C-17 C-15 第 7 行：服务端配对 / 前端声明态 / 双链承担', () => {
  const row7 = c17Lines(c15Doc).filter((l) => l.indexOf('| 7 | 去重：') === 0);
  c17Assert.equal(row7.length, 1);
  c17Assert.ok(c17Has(row7[0], 'adapter.dedupe'));
  c17Assert.ok(c17Has(row7[0], 'core/chat_completions.py pending_tool_calls'));
  c17Assert.ok(c17Has(row7[0], '服务端按 tool_call_id 配对防重放已实交付'));
  c17Assert.ok(c17Has(row7[0], '前端 dedupe 仍声明态'));
  c17Assert.ok(c17Has(row7[0], '00_data.js'));
  c17Assert.ok(c17Has(row7[0], '05j_card_sig.js'));
  c17Assert.ok(c17Has(row7[0], '00_data.js 3 份夹具、05j_card_sig.js 4 份夹具'));
  c17Assert.ok(c17Has(row7[0], 'c6 顺序表步骤 2 / 5'));
});

// 二、服务端 pending_tool_calls 配对链在码。
c17Test('C-17 服务端：pending_tool_calls 与 _execute_pending 在码', () => {
  c17Assert.ok(c17Has(corePy, 'def _pending_key(tc, answered, seen):'));
  c17Assert.ok(c17Has(corePy, 'def pending_tool_calls(messages):'));
  c17Assert.ok(c17Has(corePy, 'key not in answered and key not in seen'));
  c17Assert.ok(c17Has(corePy, 'seen.add(key)'));
  c17Assert.ok(c17Has(corePy, 'out.append(tc)'));
  c17Assert.ok(c17Has(chatApiPy, 'for call in cc.pending_tool_calls(history):'));
  c17Assert.ok(c17Has(chatApiPy, 'cc.execute_tool_call(call)'));
  c17Assert.ok(c17Has(chatApiPy, 'cc.tool_message_from_call(call, body)'));
  c17Assert.equal(c17Count(corePy, 'pending_tool_calls'), 1);
  c17Assert.equal(c17Count(chatApiPy, 'pending_tool_calls'), 2);
});

// 三、adapter.dedupe 声明回显：同 / 异 id 不吞并、null 回落、恰四键。
c17Test('C-17 adapter.dedupe：声明回显与 STATUS / KEY 不漂移', () => {
  c17Assert.equal(AdapterLib.STATUS, 'declared-placeholder');
  c17Assert.equal(AdapterLib.KEY, 'tool_call.id');
  const same = AdapterLib.dedupe('call_n1', 'call_n1');
  const diff = AdapterLib.dedupe('call_a', 'call_b');
  const nil = AdapterLib.dedupe(null, 'call_a');
  [same, diff, nil].forEach((r) => {
    c17Assert.equal(r.by, AdapterLib.KEY);
    c17Assert.equal(r.status, AdapterLib.STATUS);
    c17Assert.equal(Object.keys(r).length, 4);
  });
  c17Assert.equal(same.a, 'call_n1');
  c17Assert.equal(same.b, 'call_n1');
  c17Assert.equal(diff.a, 'call_a');
  c17Assert.equal(diff.b, 'call_b');
  c17Assert.equal(nil.a, null);
  c17Assert.equal(nil.b, 'call_a');
  c17Assert.ok(c17Has(adapterSrc, 'function dedupe(a, b)'));
  c17Assert.ok(c17Has(adapterSrc, 'dedupe: dedupe'));
});

// 四、运行期五精确串零调用方（递归扫 parts 下 .js + dialog.html + 两个 lib）。
c17Test('C-17 adapter.dedupe 运行期五精确串零命中', () => {
  const needles = ['AIMirrorStandardChainAdapter.dedupe', 'adapter.dedupe(', 'AD.dedupe(', 'Adapter.dedupe(', '.dedupe('];
  const partsDir = c17Path.join(rootDir, 'extend/dialog/parts');
  const files = c17Fs.readdirSync(partsDir).filter((f) => f.slice(-3) === '.js').map((f) => c17Path.join(partsDir, f));
  files.push(c17Path.join(rootDir, 'extend/dialog/dialog.html'));
  files.push(c17Path.join(rootDir, 'extend/lib/standard_chain_adapter.js'));
  files.push(c17Path.join(rootDir, 'extend/lib/standard_chain_contract.js'));
  needles.forEach((n) => {
    files.forEach((f) => {
      c17Assert.equal(c17Has(c17Fs.readFileSync(f, 'utf8'), n), false, n + ' in ' + f);
    });
  });
});

// 五、00_data.js 镜像区去重实况与命中计数。
c17Test('C-17 00_data.js：nonce 配对、折叠与命中计数', () => {
  c17Assert.ok(c17Has(dataPart, 'D.cardHasMessage = function (conv, card) {'));
  c17Assert.ok(c17Has(dataPart, 'obj.nonce === card.nonce'));
  c17Assert.ok(c17Has(dataPart, 'D.buildTimeline = function (conv, msgKeys, opts) {'));
  c17Assert.ok(c17Has(dataPart, '!D.cardHasMessage(conv, c)'));
  c17Assert.equal(c17Count(dataPart, 'bridge-chat-res'), 3);
  c17Assert.equal(c17Count(dataPart, 'external-call'), 3);
  c17Assert.equal(c17Count(dataPart, 'buildTimeline'), 1);
});

// 六、05j_card_sig.js 标准键 + 旧 msgId 双查构型与命中计数。
c17Test('C-17 05j_card_sig.js：双查构型与命中计数', () => {
  c17Assert.ok(c17Has(sigPart, 'M._executedSig = function (msgId, call) {'));
  c17Assert.ok(c17Has(sigPart, 'const keyId = stdId || msgId;'));
  c17Assert.ok(c17Has(sigPart, 'store[sigNew] ? sigNew : (store[sigOld] ? sigOld : '));
  c17Assert.ok(c17Has(sigPart, 'M._markExecutedSig = function (card) {'));
  c17Assert.ok(c17Has(sigPart, 'const keyId = card.toolCallId || card.msgId;'));
  c17Assert.equal(c17Count(sigPart, '_executedSig'), 3);
  c17Assert.equal(c17Count(sigPart, 'toolCallId'), 3);
  c17Assert.equal(c17Count(sigPart, 'msgId'), 7);
});

// 七、C-9 第五节边界段与状态行、C-14 签名行（仅标注对拍输入）。
c17Test('C-17 C-9 / C-14：dedupe 标注对拍输入在文', () => {
  c17Assert.ok(c17Has(boundaryDoc, '### 5. dedupe(a, b)'));
  c17Assert.ok(c17Has(boundaryDoc, '占位期不做判重决策、不吞并'));
  c17Assert.ok(c17Has(boundaryDoc, '| dedupe | declared-placeholder |'));
  c17Assert.ok(c17Has(tableDoc, 'dedupe(a,b) | standard_chain_adapter.js | 返回 by=KEY、a、b、status=STATUS | 一致 | declared-placeholder |'));
  c17Assert.ok(c17Has(matrixDoc, '| 7 | 去重 |'));
});

// 八、b10 就绪度表 00_data / 05j 行与 S4 三项前置在文。
c17Test('C-17 b10 就绪度表：双链行与 S4 前置在文', () => {
  c17Assert.ok(c17Has(readinessDoc, '| 00_data.js | 是 | 是 |'));
  c17Assert.ok(c17Has(readinessDoc, '| 05j_card_sig.js | 是 | 是 |'));
  c17Assert.ok(c17Has(readinessDoc, 'cardHasMessage 按 nonce 配对'));
  c17Assert.ok(c17Has(readinessDoc, '旧标记摘除当前不下发，前置未满足'));
  c17Assert.ok(c17Has(readinessDoc, 'c6 九文件顺序表未执行'));
});

// 九、contract 键映射纯函数在码（第 4 / 6 步键落运行期的依赖基线）。
c17Test('C-17 contract 键映射：call_ 前缀与三键在码', () => {
  c17Assert.equal(ContractLib.PREFIX, 'call_');
  c17Assert.equal(ContractLib.makeToolCallId('n1'), 'call_n1');
  c17Assert.deepEqual(ContractLib.standardToolMessage('call_n1', 'OK'), {
    role: 'tool', tool_call_id: 'call_n1', content: 'OK'
  });
});

// 十、本报告六节齐全，差异登记不越复核输入边界。
c17Test('C-17 报告：六节齐全且结论仅为复核输入', () => {
  ['## 一、', '## 二、', '## 三、', '## 四、', '## 五、', '## 六、'].forEach((h) => {
    c17Assert.ok(c17Has(reportDoc, h));
  });
  c17Assert.ok(c17Has(reportDoc, '仅为分发方复核输入'));
  c17Assert.ok(c17Has(reportDoc, '不代拍板'));
  c17Assert.ok(c17Has(reportDoc, '不改 S1-S4 判态'));
  c17Assert.ok(c17Has(reportDoc, '阶段 3 不进入摘除步'));
});
