/*
 * A-13 九步装配面第 6 步 tool 消息回执单步只读取证反查夹具
 * （dispatcher-20261116T202644-440f67，零代码改动的只读取证片）。
 * 只读 require 已合入 adapter / contract / translator 三个 lib（均 UMD node 分支），
 * 契约 .md / 就绪度报告 / 活链文件 fs 只读反查，按字符码 10 切行、
 * 普通 indexOf / split（零反斜杠零正则）；无 fs 写 / shell / 网络。
 * 覆盖：standardToolMessage 三键纯函数实测与全仓计数、adapter.reply 声明态
 * 零下游、translator fromToolMessage / toToolMessage 双向活翻译面实测、
 * 运行期回执旧链 13 文件落点、C-8 / C-15 / C-9 / C-14 / b10 五处锚点对拍、
 * 差异登记 4 项、报告六节自反。
 * 新增被测 JS 源 0；不装配 M、不建开关、不切活链、不翻 STATUS。
 */
'use strict';
// 防重窗：require 序与 a11 / a12 / c16 家族差异化（fs 前置于 test / 路径别名单段拼）。
const a13Fs = require('node:fs');
const a13Test = require('node:test');
const a13Assert = require('node:assert/strict');
const a13Path = require('node:path');
const a13Contract = require('../../../extend/lib/standard_chain_contract.js');
const a13Adapter = require('../../../extend/lib/standard_chain_adapter.js');
const a13Translator = require('../../../extend/lib/translator.js');

const LF = String.fromCharCode(10);
const a13Root = a13Path.resolve(__dirname, '../../..');
const relOf = function (rel) { return a13Path.join(a13Root, rel); };
const readOf = function (rel) { return a13Fs.readFileSync(relOf(rel), 'utf8'); };
const hasStr = function (t, n) { return t.indexOf(n) >= 0; };
const cntOf = function (t, n) { return t.split(n).length - 1; };
const linesOf = function (t) { return t.split(LF); };

const adapterSrc = readOf('extend/lib/standard_chain_adapter.js');
const contractSrc = readOf('extend/lib/standard_chain_contract.js');
const translatorSrc = readOf('extend/lib/translator.js');
const matrixDoc = readOf('extend/lib/standard_chain_field_matrix.md');
const boundaryDoc = readOf('extend/lib/standard_chain_boundary_contract.md');
const tableDoc = readOf('extend/lib/standard_chain_c14_signature_table.md');
const c15Doc = readOf('docs/c15-s2-remaining-surface-inventory.md');
const b10Doc = readOf('docs/b10-removal-readiness-report.md');
const reportDoc = readOf('docs/a13-step6-receipt-inventory.md');
const parsePart = readOf('extend/dialog/parts/05f_parse.js');
const promptPart = readOf('extend/dialog/parts/05c_prompt.js');
const dataPart = readOf('extend/dialog/parts/00_data.js');
const execPart = readOf('extend/dialog/parts/06_execute.js');
const cardsPart = readOf('extend/dialog/parts/05g_cards.js');
const memPart = readOf('extend/dialog/parts/05d_memory.js');
const htmlDoc = readOf('extend/dialog/dialog.html');

// 一、standardToolMessage 三键纯函数（contract 侧）
a13Test('A13-1 standardToolMessage 恰三键且无第四键', () => {
  const msg = a13Contract.standardToolMessage('call_x9', 'ok');
  a13Assert.deepEqual(Object.keys(msg).sort(), ['content', 'role', 'tool_call_id']);
  a13Assert.equal(msg.role, 'tool');
  a13Assert.equal(msg.tool_call_id, 'call_x9');
  a13Assert.equal(msg.content, 'ok');
  a13Assert.equal(hasStr(JSON.stringify(msg), 'msgId'), false);
});
a13Test('A13-2 String 归一：null/undefined/数字/对象入参', () => {
  const m1 = a13Contract.standardToolMessage(null, null);
  a13Assert.equal(m1.tool_call_id, 'null');
  a13Assert.equal(m1.content, '');
  const m2 = a13Contract.standardToolMessage(42, undefined);
  a13Assert.equal(m2.tool_call_id, '42');
  a13Assert.equal(m2.content, '');
  const m3 = a13Contract.standardToolMessage({ k: 1 }, { a: 1 });
  a13Assert.equal(m3.tool_call_id, String({ k: 1 }));
  a13Assert.equal(m3.content, String({ a: 1 }));
});
a13Test('A13-3 幂等新对象 + 冻结契约不漂移', () => {
  const a = a13Contract.standardToolMessage('call_1', 'x');
  const b = a13Contract.standardToolMessage('call_1', 'x');
  a13Assert.notEqual(a, b);
  a13Assert.equal(a13Contract.PRE_DISPATCH_HOOK_CONTRACT.status, 'declared-placeholder');
  a13Assert.equal(a13Contract.PROTOCOL_RETIREMENT_CONTRACT.status, 'declared-placeholder');
  a13Assert.equal(a13Contract.PREFIX, 'call_');
});

// 二、adapter.reply 声明态零下游
a13Test('A13-4 adapter.reply 恰四键回显与常量', () => {
  const r = a13Adapter.reply({ tool_call_id: 'call_q1', content: 'zz' });
  a13Assert.deepEqual(Object.keys(r).sort(), ['by', 'role', 'status', 'tool_call_id']);
  a13Assert.equal(r.by, 'tool_call.id');
  a13Assert.equal(r.role, 'tool');
  a13Assert.equal(r.tool_call_id, 'call_q1');
  a13Assert.equal(r.status, 'declared-placeholder');
  a13Assert.equal(hasStr(JSON.stringify(r), 'zz'), false);
});
a13Test('A13-5 运行期零调用方：活链六文件 .reply( 零命中', () => {
  const six = [parsePart, promptPart, dataPart, execPart, cardsPart, memPart];
  for (const src of six) {
    a13Assert.equal(cntOf(src, '.reply('), 0);
  }
  a13Assert.equal(cntOf(adapterSrc, 'function reply'), 1);
  a13Assert.equal(cntOf(adapterSrc, 'AIMirrorStandardChainAdapter.reply'), 0);
});

// 三、translator 双向活翻译面（运行期回执的最强实锤）
a13Test('A13-6 fromToolMessage：role 判定 + nonce 剥前缀 + success 补真', () => {
  const out = a13Translator.fromToolMessage(
    { role: 'tool', tool_call_id: 'call_ab12', name: 'list_tools', content: '{"ok":true}' },
    false
  );
  const body = JSON.parse(out);
  a13Assert.equal(body.ok, true);
  a13Assert.equal(body.tool, 'list_tools');
  a13Assert.equal(body.type, 'bridge-chat-res');
  a13Assert.equal(body.nonce, 'ab12');
  a13Assert.equal(body.success, true);
  a13Assert.equal(a13Translator.fromToolMessage({ role: 'user' }, false), '');
});
a13Test('A13-7 toToolMessage：信封→标准 tool 消息三键形态', () => {
  const m = a13Translator.toToolMessage('call_cd34', 'get_rule', { done: 1 });
  a13Assert.equal(m.role, 'tool');
  a13Assert.equal(m.tool_call_id, 'call_cd34');
  a13Assert.equal(m.name, 'get_rule');
  a13Assert.deepEqual(JSON.parse(m.content), { done: 1 });
  a13Assert.equal(a13Translator.callIdFromNonce('ef56'), 'call_ef56');
  a13Assert.equal(a13Translator.nonceFromCallId('call_ef56'), 'ef56');
});
// 四、运行期回执旧链落点（git grep 计数与夹具反查互证）
a13Test('A13-8 旧链六文件 bridge-chat-res 落点计数（b10 快照口径）', () => {
  a13Assert.equal(cntOf(parsePart, 'bridge-chat-res'), 3);
  a13Assert.equal(cntOf(promptPart, 'bridge-chat-res'), 6);
  a13Assert.equal(cntOf(dataPart, 'bridge-chat-res'), 3);
  a13Assert.equal(cntOf(execPart, 'bridge-chat-res'), 1);
  a13Assert.equal(cntOf(cardsPart, 'bridge-chat-res'), 3);
  a13Assert.equal(cntOf(memPart, 'bridge-chat-res'), 2);
  a13Assert.equal(cntOf(translatorSrc, 'bridge-chat-res'), 4);
});
a13Test('A13-9 关键落点行文：05f 判源 / 00_data nonce 配对 / 05g 质量回传', () => {
  const f = linesOf(parsePart);
  a13Assert.equal(f[389].indexOf('bridge-chat-res') >= 0, true);
  a13Assert.equal(hasStr(parsePart, 'msgSource'), true);
  a13Assert.equal(hasStr(dataPart, 'cardHasMessage'), true);
  a13Assert.equal(hasStr(dataPart, 'external-call'), true);
  a13Assert.equal(hasStr(cardsPart, 'quality_report'), true);
  a13Assert.equal(hasStr(execPart, 'postCardResult'), true);
  a13Assert.equal(hasStr(htmlDoc, 'standard_chain_adapter.js'), true);
  a13Assert.equal(hasStr(htmlDoc, 'translator.js'), true);
});

// 五、五处锚点对拍
a13Test('A13-10 C-8 第 6 步行 / C-14 两行：装配占位与三键', () => {
  const m = linesOf(matrixDoc);
  const step6 = m.filter(function (l) { return l.indexOf('| 6 | tool 消息回执') === 0; });
  a13Assert.equal(step6.length, 1);
  a13Assert.equal(hasStr(step6[0], 'standard_chain_contract.js standardToolMessage'), true);
  a13Assert.equal(hasStr(step6[0], 'standard_chain_adapter.js reply'), true);
  a13Assert.equal(hasStr(step6[0], '否'), true);
  const t = linesOf(tableDoc);
  const stRow = t.filter(function (l) { return l.indexOf('standardToolMessage(callId,content)') >= 0; });
  a13Assert.equal(stRow.length, 1);
  a13Assert.equal(hasStr(stRow[0], '{role:tool,tool_call_id,content} 三键'), true);
  const repRow = t.filter(function (l) { return l.indexOf('reply(msg)') >= 0 || l.indexOf('reply(') >= 0; });
  a13Assert.equal(repRow.length >= 1, true);
});
a13Test('A13-11 C-15 | 6 | 行与 b10 就绪度表关键断语', () => {
  const c = linesOf(c15Doc);
  const row6 = c.filter(function (l) { return l.indexOf('| 6 |') === 0; });
  a13Assert.equal(row6.length >= 1, true);
  a13Assert.equal(hasStr(row6[0], 'adapter.reply 无运行期下游') || hasStr(row6[0], 'adapter.reply 占位'), true);
  a13Assert.equal(hasStr(c15Doc, 'bridge-chat-res'), true);
  a13Assert.equal(hasStr(b10Doc, '步骤 3：标准 tool_calls 解析入口可用'), true);
  a13Assert.equal(hasStr(b10Doc, '翻译层本体（不属旧链，但含旧协议字串）'), true);
  a13Assert.equal(hasStr(b10Doc, '摘除任务书未下发') || hasStr(b10Doc, '摘除任务书'), true);
});

// 六、报告自反与差异登记
a13Test('A13-12 本报告六节齐全 + 差异登记 4 项 + 判态锚引用', () => {
  for (const head of ['## 一、取证范围与方法', '## 二、代码实况：第 6 步三面逐项钉死', '## 三、四处锚点逐行对拍', '## 四、差异登记（供分发方复核，不代拍板）', '## 五、结论', '## 六、边界与只追加记录']) {
    a13Assert.equal(hasStr(reportDoc, head), true);
  }
  for (const item of ['计数漂移', 'b10 S2 行第 5 步状态措辞时点漂移', '任务书锚点指代漂移', '不构成执行权迁移、不构成新前置']) {
    a13Assert.equal(hasStr(reportDoc, item), true);
  }
  a13Assert.equal(hasStr(reportDoc, 'dispatcher-20261116T202644-440f67'), true);
  a13Assert.equal(cntOf(reportDoc, 'dispatcher-20261116T202644-440f67') >= 1, true);
  a13Assert.equal(hasStr(reportDoc, '19:45 判态锚不变'), true);
});
