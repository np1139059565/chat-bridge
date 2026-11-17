/*
 * C-18 九步装配面第 8 步刷新恢复键逐行取证反查夹具（dispatcher-20261116T220220-a65876）。
 * 只读 require 两个已合入 lib，按字符码 10 切行反查 C-15 / C-9 / C-14 / C-8 / b10 / c7 / c6 /
 * contract / adapter / 05j / 05g / 活链递归扫 / 本报告。
 * 覆盖：C-15 第 8 行六列、C-9 restore 边界段与状态行、C-14 签名行与第六节、
 * C-8 九步表第 8 行、adapter.restore 声明回显、contract.execKeyFromToolCall 纯函数、
 * 05j 双查恢复链、05g 落标准键、运行期零调用方、b10 / c7 / c6 就绪度、报告六节与复核输入边界。
 * 零反斜杠零正则，普通 indexOf 与 split；无 fs 写 / shell / 网络；新增被测 JS 源 0。
 * require 头部序按 A-10 与 a11 / a12 / b13 / b14 / c16 / c17 同族差异化归零。
 */
'use strict';
const scDoc = require('./_standard_chain_doc_snippets.js');
const c18Test = require('node:test');
const c18Assert = require('node:assert/strict');
const c18Fs = require('node:fs');
const c18Path = require('node:path');
const AdapterLib = require('../../../extend/lib/standard_chain_adapter.js');
const ContractLib = require('../../../extend/lib/standard_chain_contract.js');

const LF = String.fromCharCode(10);
const rootDir = c18Path.resolve(__dirname, '../../..');
function c18Read(rel) { return c18Fs.readFileSync(c18Path.join(rootDir, rel), 'utf8'); }
function c18Has(text, needle) { return text.indexOf(needle) >= 0; }
function c18Lines(text) { return text.split(LF); }
function c18Count(text, needle) { return text.split(needle).length - 1; }
function c18LineCount(text, needle) { return c18Lines(text).filter((l) => c18Has(l, needle)).length; }
const c15Doc = scDoc.doc('c15');
const boundaryDoc = c18Read('extend/lib/standard_chain_boundary_contract.md');
const tableDoc = c18Read('extend/lib/standard_chain_c14_signature_table.md');
const matrixDoc = c18Read('extend/lib/standard_chain_field_matrix.md');
const readinessDoc = scDoc.doc('b10');
const c7Doc = scDoc.doc('c7');
const c6Doc = scDoc.doc('c6');
const contractSrc = c18Read('extend/lib/standard_chain_contract.js');
const adapterSrc = c18Read('extend/lib/standard_chain_adapter.js');
const sigPart = c18Read('extend/dialog/parts/05j_card_sig.js');
const cardsPart = c18Read('extend/dialog/parts/05g_cards.js');
const reportDoc = scDoc.doc('c18');

// 一、C-15 第二节第 8 行六列在文（本片主锚）。
c18Test('C-18 C-15 第 8 行：刷新恢复键六列', () => {
  const row8 = c18Lines(c15Doc).filter((l) => l.indexOf('| 8 | 刷新恢复') === 0);
  c18Assert.equal(row8.length, 1);
  c18Assert.ok(c18Has(row8[0], '05j_card_sig.js'));
  c18Assert.ok(c18Has(row8[0], '05g_cards.js'));
  c18Assert.ok(c18Has(row8[0], '已实改并保持：标准键优先、旧 msgId 兼容双查、去消息指纹'));
  c18Assert.ok(c18Has(row8[0], 'contract.js execKeyFromToolCall'));
  c18Assert.ok(c18Has(row8[0], '运行期恢复仍走旧双查'));
  c18Assert.ok(c18Has(row8[0], '4 份夹具'));
  c18Assert.ok(c18Has(row8[0], 'c6 顺序表步骤 5'));
});

// 二、C-9 restore 边界段（实仓 ### 6）与状态行、G4 在文。
c18Test('C-18 C-9：restore 边界段与状态行标注对拍输入', () => {
  c18Assert.ok(c18Has(boundaryDoc, '### 6. restore(sessionId, call)'));
  c18Assert.ok(c18Has(boundaryDoc, 'G4 **刷新恢复键语义**'));
  c18Assert.ok(c18Has(boundaryDoc, '恒真'));
  c18Assert.ok(c18Has(boundaryDoc, '| restore | declared-placeholder |'));
  c18Assert.ok(c18Has(boundaryDoc, '本段只钉声明语义，不改运行时'));
});

// 三、C-14 restore 签名行 / execKey 行 / 第六节仅 execute 登记。
c18Test('C-18 C-14：restore 签名行与第六节边界', () => {
  c18Assert.ok(c18Has(tableDoc, 'restore(sessionId,call) | standard_chain_adapter.js | 返回 by=KEY、sessionId、id、noMessageFingerprint=true、status=STATUS | 一致 | declared-placeholder |'));
  c18Assert.ok(c18Has(tableDoc, 'execKeyFromToolCall(call,sessionId) | standard_chain_contract.js'));
  c18Assert.ok(c18Has(tableDoc, '| 六段接口名 | standard_chain_adapter.js | parse / buildCard / execute / reply / dedupe / restore |'));
  c18Assert.ok(c18Has(tableDoc, '## 六、execute 段实装登记'));
  const sec6 = tableDoc.split('## 六、execute 段实装登记')[1] || '';
  c18Assert.equal(c18Has(sec6, 'restore'), false);
});

// 四、C-8 九步表第 8 行与对拍矩阵 #8 / #12 编号口径区分。
c18Test('C-18 C-8：九步表第 8 行与矩阵编号区分', () => {
  c18Assert.ok(c18Has(matrixDoc, '| 8 | 刷新恢复 call_<nonce> 键'));
  c18Assert.ok(c18Has(matrixDoc, '| 8 | 规范化追加'));
  c18Assert.ok(c18Has(matrixDoc, '| 12 | restore 段（刷新恢复键）'));
});

// 五、adapter.restore 声明回显：五键、归一、noMessageFingerprint 恒真、幂等。
c18Test('C-18 adapter.restore：声明回显与 STATUS / KEY 不漂移', () => {
  c18Assert.equal(AdapterLib.STATUS, 'declared-placeholder');
  c18Assert.equal(AdapterLib.KEY, 'tool_call.id');
  const r1 = AdapterLib.restore('s1', { id: 'call_n1' });
  const r2 = AdapterLib.restore(null, null);
  const r3 = AdapterLib.restore('s1', { id: 'call_n1' });
  c18Assert.equal(Object.keys(r1).length, 5);
  c18Assert.equal(r1.by, AdapterLib.KEY);
  c18Assert.equal(r1.sessionId, 's1');
  c18Assert.equal(r1.id, 'call_n1');
  c18Assert.equal(r1.noMessageFingerprint, true);
  c18Assert.equal(r1.status, AdapterLib.STATUS);
  c18Assert.equal(r2.sessionId, '');
  c18Assert.equal(r2.id, null);
  c18Assert.equal(r2.noMessageFingerprint, true);
  c18Assert.deepEqual(r1, r3);
  c18Assert.ok(r1 !== r3);
  c18Assert.ok(c18Has(adapterSrc, 'function restore(sessionId, call)'));
  c18Assert.ok(c18Has(adapterSrc, 'restore: restore'));
});

// 六、contract.execKeyFromToolCall 纯函数在码、不含消息指纹。
c18Test('C-18 contract：execKeyFromToolCall 纯函数与键映射', () => {
  c18Assert.ok(c18Has(contractSrc, 'function execKeyFromToolCall(call, sessionId)'));
  c18Assert.ok(c18Has(contractSrc, '不含消息指纹'));
  c18Assert.equal(ContractLib.makeToolCallId('n1'), 'call_n1');
  c18Assert.equal(ContractLib.nonceFromToolCallId('call_n1'), 'n1');
  const k = ContractLib.execKeyFromToolCall({ id: 'call_n1', tool: 'run_command', parameters: { x: 1 } }, 'sess1');
  c18Assert.equal(c18Count(k, '|'), 3);
  c18Assert.ok(c18Has(k, 'sess1'));
  c18Assert.ok(c18Has(k, 'n1'));
  c18Assert.ok(c18Has(k, 'run_command'));
  c18Assert.equal(c18Has(k, 'msgId'), false);
});

// 七、05j 运行期刷新恢复双查构型与命中计数。
c18Test('C-18 05j_card_sig.js：双查恢复链与命中计数', () => {
  c18Assert.ok(c18Has(sigPart, 'M._restoreExecutedCards = function (conv, convId) {'));
  c18Assert.ok(c18Has(sigPart, 'const keyId = card.toolCallId || card.msgId;'));
  c18Assert.ok(c18Has(sigPart, 'JSON.stringify(card.parameters || {})'));
  c18Assert.ok(c18Has(sigPart, 'const keyId = stdId || msgId;'));
  c18Assert.ok(c18Has(sigPart, 'sigNew'));
  c18Assert.ok(c18Has(sigPart, 'sigOld'));
  c18Assert.ok(c18Has(sigPart, 'M._markExecutedSig = function (card) {'));
  c18Assert.ok(c18Has(sigPart, 'M.cardMatchesBySig = function (card) {'));
  c18Assert.ok(c18Has(sigPart, '不掺消息指纹'));
  c18Assert.equal(c18Count(sigPart, 'toolCallId'), 3);
  c18Assert.equal(c18Count(sigPart, 'msgId'), 7);
  c18Assert.equal(c18Count(sigPart, '_restoreExecutedCards'), 1);
  // git grep 按行计 4；split 字面子串 5（L62 同行两次），两种口径都坐实。
  c18Assert.equal(c18LineCount(sigPart, 'executedSigs'), 4);
  c18Assert.equal(c18Count(sigPart, 'executedSigs'), 5);
});

// 八、05g 建卡侧落标准 call_ 键与签名恢复。
c18Test('C-18 05g_cards.js：落 card.toolCallId 与命中恢复', () => {
  c18Assert.ok(c18Has(cardsPart, 'card.toolCallId = calls[0].id;'));
  c18Assert.ok(c18Has(cardsPart, '标准 tool_call.id 优先'));
  c18Assert.ok(c18Has(cardsPart, 'cid ? cid(nonce) :'));
  c18Assert.ok(c18Has(cardsPart, 'const doneSig = this._executedSig(this.msgId(m), call);'));
  c18Assert.equal(c18Count(cardsPart, 'card.toolCallId'), 1);
});

// 九、运行期零命中：execKeyFromToolCall 未接入 + adapter.restore 五精确串零调用方。
c18Test('C-18 运行期：execKey 未接入且 restore 五精确串零命中', () => {
  const partsDir = c18Path.join(rootDir, 'extend/dialog/parts');
  const partFiles = c18Fs.readdirSync(partsDir).filter((f) => f.slice(-3) === '.js').map((f) => c18Path.join(partsDir, f));
  const liveFiles = partFiles.concat([
    c18Path.join(rootDir, 'extend/dialog/dialog.html'),
    c18Path.join(rootDir, 'flask_server/core/chat_completions.py'),
    c18Path.join(rootDir, 'flask_server/routes/chat_api.py')
  ]);
  liveFiles.forEach((f) => {
    c18Assert.equal(c18Has(c18Fs.readFileSync(f, 'utf8'), 'execKeyFromToolCall'), false, 'execKey in ' + f);
  });
  const libFiles = liveFiles.concat([
    c18Path.join(rootDir, 'extend/lib/standard_chain_adapter.js'),
    c18Path.join(rootDir, 'extend/lib/standard_chain_contract.js')
  ]);
  ['AIMirrorStandardChainAdapter.restore', 'adapter.restore(', 'AD.restore(', 'Adapter.restore(', '.restore('].forEach((n) => {
    libFiles.forEach((f) => {
      c18Assert.equal(c18Has(c18Fs.readFileSync(f, 'utf8'), n), false, n + ' in ' + f);
    });
  });
});

// 十、b10 / c7 / c6 就绪度与报告六节、复核输入边界。
c18Test('C-18 b10 / c7 / c6 就绪度与报告六节齐全', () => {
  c18Assert.ok(c18Has(readinessDoc, '| 05j_card_sig.js | 是 | 是 |'));
  c18Assert.ok(c18Has(readinessDoc, '步骤 5：execKeyFromToolCall 接入且 executedSigs 去消息指纹'));
  c18Assert.ok(c18Has(readinessDoc, '刷新恢复链：executedSigs 双查构型'));
  c18Assert.ok(c18Has(readinessDoc, '旧标记摘除当前不下发，前置未满足'));
  c18Assert.ok(c18Has(readinessDoc, 'c6 九文件顺序表未执行'));
  c18Assert.ok(c18Has(c7Doc, 'execKeyFromToolCall 接入且 executedSigs 去消息指纹'));
  c18Assert.ok(c18Has(c6Doc, 'executedSigs 落盘'));
  ['## 一、', '## 二、', '## 三、', '## 四、', '## 五、', '## 六、'].forEach((h) => {
    c18Assert.ok(c18Has(reportDoc, h));
  });
  c18Assert.ok(c18Has(reportDoc, '仅为分发方复核输入'));
  c18Assert.ok(c18Has(reportDoc, '不代拍板'));
  c18Assert.ok(c18Has(reportDoc, '不改 S1-S4 判态'));
  c18Assert.ok(c18Has(reportDoc, '阶段 3 不进入摘除步'));
});
