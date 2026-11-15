/*
 * C-15 只读取证反查夹具。
 * 只读 require 两个已合入 lib，按字符码 10 切行反查契约文档与活链装载实况。
 * 覆盖：五段声明态、EXECUTE_STATUS 独立导出、B-12 只追加登记、
 * C-8 历史推演标注保留、旧信封活链留存、本报告四节齐全。
 * 零反斜杠零正则，普通 indexOf 与 split；新增被测 JS 源 0。
 */
'use strict';
const nodeAssert = require('node:assert/strict');
const nodeTest = require('node:test');
const nodeFs = require('node:fs');
const nodePath = require('node:path');
const A = require('../../../extend/lib/standard_chain_adapter.js');
const C = require('../../../extend/lib/standard_chain_contract.js');

const LF = String.fromCharCode(10);
const repoRoot = nodePath.resolve(__dirname, '../../..');
function read(rel) { return nodeFs.readFileSync(nodePath.join(repoRoot, rel), 'utf8'); }
function has(text, needle) { return text.indexOf(needle) >= 0; }
function rows(text) { return text.split(LF); }
const adapterSrc = read('extend/lib/standard_chain_adapter.js');
const boundary = read('extend/lib/standard_chain_boundary_contract.md');
const table = read('extend/lib/standard_chain_c14_signature_table.md');
const matrix = read('extend/lib/standard_chain_field_matrix.md');
const criteria = read('extend/lib/standard_chain_pending_criteria.md');
const readiness = read('docs/b10-removal-readiness-report.md');
const report = read('docs/c15-s2-remaining-surface-inventory.md');
const executePart = read('extend/dialog/parts/06_execute.js');
const dialogHtml = read('extend/dialog/dialog.html');
const parsePart = read('extend/dialog/parts/05f_parse.js');
const dataPart = read('extend/dialog/parts/00_data.js');

// 一、六段中除 execute 外五段恒声明态，KEY 恒标准 tool_call.id。
nodeTest('C-15 五段声明回显：STATUS 与 KEY 不漂移', () => {
  nodeAssert.equal(A.STATUS, 'declared-placeholder');
  nodeAssert.equal(A.KEY, 'tool_call.id');
  const samples = [
    A.parse(null),
    A.buildCard({ id: 'call_n1' }),
    A.reply({ role: 'tool', tool_call_id: 'call_n1' }),
    A.dedupe('call_n1', 'call_n1'),
    A.restore('s1', { id: 'call_n1' })
  ];
  samples.forEach((r) => {
    nodeAssert.equal(r.by, A.KEY);
    nodeAssert.equal(r.status, A.STATUS);
  });
  nodeAssert.equal(samples[2].role, 'tool');
  nodeAssert.equal(samples[4].noMessageFingerprint, true);
});

// 二、execute 段实装态只由独立导出表达，单参回显不变。
nodeTest('C-15 execute 单点：独立导出与单参回显不变', () => {
  nodeAssert.equal(A.EXECUTE_STATUS, 'implemented-S2-step5');
  nodeAssert.equal(A.execute(null).status, A.STATUS);
  nodeAssert.equal(A.execute(null).by, A.KEY);
  nodeAssert.ok(has(adapterSrc, 'execute-caught'));
  nodeAssert.ok(has(adapterSrc, 'card.status = '));
});

// 三、B-12 落点：06_execute 委托 adapter.execute，dialog.html 装载 adapter。
nodeTest('C-15 第 5 步落点：委托注入与装载行在码', () => {
  nodeAssert.ok(has(executePart, 'AIMirrorStandardChainAdapter.execute(card'));
  nodeAssert.ok(has(executePart, 'callTool'));
  nodeAssert.ok(has(dialogHtml, 'standard_chain_adapter.js'));
});

// 四、只追加登记：边界契约第四节与 C-14 第六节存在，历史状态表保留。
nodeTest('C-15 只追加登记：两处实装登记与历史六段表并存', () => {
  nodeAssert.ok(has(boundary, '## 四、execute 段实装登记'));
  nodeAssert.ok(has(boundary, 'EXECUTE_STATUS'));
  nodeAssert.ok(has(table, '## 六、execute 段实装登记'));
  nodeAssert.ok(has(table, 'implemented-S2-step5'));
  const parseRows = rows(boundary).filter((l) => l.indexOf('| parse | declared-placeholder |') === 0);
  nodeAssert.equal(parseRows.length, 1);
  nodeAssert.ok(has(boundary, '| execute | declared-placeholder |'));
});

// 五、C-8 第二节第 5 步历史标注保留，第 6 步推演行存在（只读推演）。
nodeTest('C-15 九步推演：第 5 步历史标注与第 6 步落点行保留', () => {
  nodeAssert.ok(has(matrix, '## 二、端到端装配面只读推演'));
  nodeAssert.ok(has(matrix, 'standard_chain_adapter.js execute'));
  nodeAssert.ok(has(matrix, 'standardToolMessage'));
  nodeAssert.ok(has(matrix, '仍占位；运行时执行权在 05g_cards.js'));
});

// 六、S4 判据与就绪度：旧标记摘除硬前置与报告口径在码。
nodeTest('C-15 S4：判据三项与就绪度结论原文保留', () => {
  nodeAssert.ok(has(criteria, '## 槽位 S4｜矩阵 #14 旧标记摘除'));
  nodeAssert.ok(has(criteria, '分发方另行下发摘除任务书'));
  nodeAssert.ok(has(readiness, '旧标记摘除当前不下发，前置未满足'));
  nodeAssert.ok(has(readiness, 'c6 九文件顺序表未执行'));
});

// 七、旧信封仍为活链（零摘除），三键纯函数在码。
nodeTest('C-15 活链留存：旧协议字串与三键契约并存', () => {
  nodeAssert.ok(has(parsePart, 'bridge-chat-call'));
  nodeAssert.ok(has(dataPart, 'bridge-chat-res'));
  nodeAssert.equal(C.makeToolCallId('n1'), 'call_n1');
  nodeAssert.deepEqual(C.standardToolMessage('call_n1', 'OK'), {
    role: 'tool', tool_call_id: 'call_n1', content: 'OK'
  });
});

// 八、本报告四节判定与边界节齐全，建议仅作复核输入。
nodeTest('C-15 报告：四节判定齐全且建议不越复核输入', () => {
  ['## 一、', '## 二、', '## 三、', '## 四、', '## 五、', '## 六、'].forEach((h) => {
    nodeAssert.ok(has(report, h));
  });
  nodeAssert.ok(has(report, '仅为分发方复核输入'));
  nodeAssert.ok(has(report, '不预设下发时点'));
});
