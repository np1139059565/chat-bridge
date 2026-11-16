/*
 * C-16 九步装配面第 4 步建卡单步只读取证反查夹具。
 * 只读 require 两个已合入 lib，按字符码 10 切行反查 C-8 / C-9 / C-14 / b10 / 05g / 05j / adapter / 本报告。
 * 覆盖：第 4 步推演行、buildCard 声明回显与零运行期调用方、contract 键映射纯函数、
 * C-9 状态行、C-14 签名行与第六节、b10 就绪度表、05g 建卡候选实况、报告六节与复核输入边界。
 * 零反斜杠零正则，普通 indexOf 与 split；无 fs 写 / shell / 网络；新增被测 JS 源 0。
 */
'use strict';
const c16Assert = require('node:assert/strict');
const c16Fs = require('node:fs');
const c16Path = require('node:path');
const c16Test = require('node:test');
const AdapterLib = require('../../../extend/lib/standard_chain_adapter.js');
const ContractLib = require('../../../extend/lib/standard_chain_contract.js');

const LF = String.fromCharCode(10);
const rootDir = c16Path.resolve(__dirname, '../../..');
function c16Read(rel) { return c16Fs.readFileSync(c16Path.join(rootDir, rel), 'utf8'); }
function c16Has(text, needle) { return text.indexOf(needle) >= 0; }
function c16Lines(text) { return text.split(LF); }
function c16Count(text, needle) { return text.split(needle).length - 1; }
const matrixDoc = c16Read('extend/lib/standard_chain_field_matrix.md');
const boundaryDoc = c16Read('extend/lib/standard_chain_boundary_contract.md');
const tableDoc = c16Read('extend/lib/standard_chain_c14_signature_table.md');
const readinessDoc = c16Read('docs/b10-removal-readiness-report.md');
const cardPart = c16Read('extend/dialog/parts/05g_cards.js');
const sigPart = c16Read('extend/dialog/parts/05j_card_sig.js');
const adapterSrc = c16Read('extend/lib/standard_chain_adapter.js');
const reportDoc = c16Read('docs/c16-s2-step4-card-build-inventory.md');

// 一、C-8 第二节第 4 步推演行在文，且标仍占位、依赖 B-7 否。
c16Test('C-16 C-8 第 4 步推演行：仍占位与落点在文', () => {
  const step4 = c16Lines(matrixDoc).filter((l) => l.indexOf('| 4 | 标准 tool_call.id 建卡 |') === 0);
  c16Assert.equal(step4.length, 1);
  c16Assert.ok(c16Has(step4[0], 'extend/lib/standard_chain_adapter.js buildCard'));
  c16Assert.ok(c16Has(step4[0], 'standard_chain_contract.js makeToolCallId'));
  c16Assert.ok(c16Has(step4[0], '仍占位；运行时建卡仍在 extend/dialog/parts/05g_cards.js，旧标记保留'));
  c16Assert.ok(c16Has(step4[0], '| 否 |'));
});

// 二、buildCard 声明回显三入参，且运行期零调用方。
c16Test('C-16 adapter.buildCard：声明回显与零运行期调用方', () => {
  c16Assert.equal(AdapterLib.STATUS, 'declared-placeholder');
  c16Assert.equal(AdapterLib.KEY, 'tool_call.id');
  const n = AdapterLib.buildCard(null);
  const e = AdapterLib.buildCard({});
  const ok = AdapterLib.buildCard({ id: 'call_n1' });
  [n, e, ok].forEach((r) => {
    c16Assert.equal(r.by, AdapterLib.KEY);
    c16Assert.equal(r.status, AdapterLib.STATUS);
  });
  c16Assert.equal(n.id, null);
  c16Assert.equal(e.id, null);
  c16Assert.equal(ok.id, 'call_n1');
  c16Assert.ok(c16Has(adapterSrc, 'function buildCard(call)'));
  c16Assert.equal(c16Has(cardPart, 'AIMirrorStandardChainAdapter.buildCard'), false);
  c16Assert.equal(c16Has(cardPart, '.buildCard('), false);
});

// 三、contract 键映射纯函数在码：call_ 前缀、三键、去消息指纹。
c16Test('C-16 contract 键映射：前缀、反解、三键与恢复键', () => {
  c16Assert.equal(ContractLib.PREFIX, 'call_');
  c16Assert.equal(ContractLib.makeToolCallId('n1'), 'call_n1');
  c16Assert.equal(ContractLib.nonceFromToolCallId('call_n1'), 'n1');
  c16Assert.deepEqual(ContractLib.standardToolMessage('call_n1', 'OK'), {
    role: 'tool', tool_call_id: 'call_n1', content: 'OK'
  });
  const k = ContractLib.execKeyFromToolCall({ id: 'call_n1', tool: 't', parameters: { a: 1 } }, 's1');
  c16Assert.ok(k.indexOf('s1') === 0 && k.indexOf('n1') >= 0);
  c16Assert.equal(k.indexOf('fingerprint') < 0, true);
});

// 四、C-9 buildCard 段与第二节状态行在文。
c16Test('C-16 C-9 buildCard 边界段与状态行在文', () => {
  c16Assert.ok(c16Has(boundaryDoc, '### 2. buildCard(call)'));
  c16Assert.ok(c16Has(boundaryDoc, 'id: null'));
  c16Assert.ok(c16Has(boundaryDoc, '| buildCard | declared-placeholder |'));
  c16Assert.ok(c16Has(boundaryDoc, '## 四、execute 段实装登记'));
});

// 五、C-14 第二节 buildCard 行与第六节只追加登记在文。
c16Test('C-16 C-14 签名行与 B-12 只追加登记在文', () => {
  c16Assert.ok(c16Has(tableDoc, '返回 by=KEY、id、status=STATUS | 一致 | declared-placeholder |'));
  c16Assert.ok(c16Has(tableDoc, '## 六、execute 段实装登记'));
  c16Assert.ok(c16Has(tableDoc, 'implemented-S2-step5'));
  c16Assert.ok(c16Has(tableDoc, 'parse / buildCard / execute / reply / dedupe / restore'));
});

// 六、b10 就绪度表 05g_cards.js 行与步骤 4 前置描述在文。
c16Test('C-16 b10 就绪度表：05g 行与步骤 4 描述在文', () => {
  c16Assert.ok(c16Has(readinessDoc, '| 05g_cards.js | 是 | 是 |'));
  c16Assert.ok(c16Has(readinessDoc, 'bridge-chat-call 1 处'));
  c16Assert.ok(c16Has(readinessDoc, '_translateToolCalls 落 card.toolCall/toolCallId'));
  c16Assert.ok(c16Has(readinessDoc, '步骤 4：state.toolCalls 有执行期'));
  c16Assert.ok(c16Has(readinessDoc, '旧标记摘除当前不下发，前置未满足'));
});

// 七、运行期建卡实况：05g 关键串与命中计数、05j 下游读回。
c16Test('C-16 05g 建卡实况：关键串、命中计数与 05j 读回', () => {
  c16Assert.ok(c16Has(cardPart, 'this._translateToolCalls(holder, m, blocks, state);'));
  c16Assert.ok(c16Has(cardPart, 'M._translateToolCalls = function (holder, m, blocks, state) {'));
  c16Assert.ok(c16Has(cardPart, 'tool: card.tool'));
  c16Assert.ok(c16Has(cardPart, 'card.toolCall = calls[0]; card.toolCallId = calls[0].id;'));
  c16Assert.ok(c16Has(cardPart, 'state.toolCalls = (state.toolCalls || []).concat(tr.calls);'));
  c16Assert.equal(c16Count(cardPart, 'bridge-chat-call'), 1);
  c16Assert.equal(c16Lines(cardPart).filter((l) => l.indexOf('toolCalls') >= 0).length, 3);
  c16Assert.equal(c16Lines(cardPart).filter((l) => l.indexOf('toolCall') >= 0).length, 10);
  c16Assert.ok(c16Has(sigPart, 'card.toolCallId || card.msgId'));
});

// 八、本报告六节齐全，差异登记不越复核输入边界。
c16Test('C-16 报告：六节齐全且结论仅为复核输入', () => {
  ['## 一、', '## 二、', '## 三、', '## 四、', '## 五、', '## 六、'].forEach((h) => {
    c16Assert.ok(c16Has(reportDoc, h));
  });
  c16Assert.ok(c16Has(reportDoc, '仅为分发方复核输入'));
  c16Assert.ok(c16Has(reportDoc, '不代拍板'));
  c16Assert.ok(c16Has(reportDoc, '不改 S1-S4 判态'));
  c16Assert.ok(c16Has(reportDoc, '阶段 3 不进入摘除步'));
});
