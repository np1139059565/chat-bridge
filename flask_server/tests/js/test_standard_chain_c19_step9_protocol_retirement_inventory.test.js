/*
 * C-19 九步装配面第 9 步协议字段退役逐行取证反查夹具（dispatcher-20261116T235535-259fdb）。
 * 只读 require 三个已合入 lib，按字符码 10 切行反查 C-15 / C-8 / C-9 / C-14 / C-10~C-13 / b7 / b10 /
 * contract / adapter / B-8 / B-9 两片纯函数 / 活链协议字串落点 / 本报告。
 * 覆盖：C-15 第 9 行六列、C-8 九步表第 9 行与矩阵 #13、C-9 G1 与范围声明、
 * C-14 PROTOCOL 两行与第六节、b7 M1-M8 与三网关、C-12 八槽、C-13 索引、b10 S3 / S4、
 * contract PROTOCOL_RETIREMENT_CONTRACT 冻结声明态、B-9 五槽与 B-8 三槽互斥、
 * 活链协议字串落点只读反查、报告六节与复核输入边界。
 * 零反斜杠零正则，普通 indexOf 与 split；无 fs 写 / shell / 网络；新增被测 JS 源 0。
 * require 头部序按 A-10 与 c18 / a13 / c17 / b14 / c16 同族差异化归零；c19Test( 直接调用。
 */
'use strict';
const c19Path = require('node:path');
const c19Assert = require('node:assert/strict');
const ContractLib = require('../../../extend/lib/standard_chain_contract.js');
const AdapterLib = require('../../../extend/lib/standard_chain_adapter.js');
const SlotResolver = require('../../../extend/lib/standard_chain_b9_slot_resolver.js');
const c19Test = require('node:test');
const c19Fs = require('node:fs');

const LF = String.fromCharCode(10);
const rootDir = c19Path.resolve(__dirname, '../../..');
function c19Read(rel) { return c19Fs.readFileSync(c19Path.join(rootDir, rel), 'utf8'); }
function c19Has(text, needle) { return text.indexOf(needle) >= 0; }
function c19Lines(text) { return text.split(LF); }
function c19Count(text, needle) { return text.split(needle).length - 1; }
function c19LineCount(text, needle) { return c19Lines(text).filter((l) => c19Has(l, needle)).length; }
const c15Doc = c19Read('docs/c15-s2-remaining-surface-inventory.md');
const matrixDoc = c19Read('extend/lib/standard_chain_field_matrix.md');
const boundaryDoc = c19Read('extend/lib/standard_chain_boundary_contract.md');
const tableDoc = c19Read('extend/lib/standard_chain_c14_signature_table.md');
const b7Doc = c19Read('docs/b7-protocol-retirement-status.md');
const b10Doc = c19Read('docs/b10-removal-readiness-report.md');
const c12Doc = c19Read('extend/lib/standard_chain_replacement_map.md');
const c10Doc = c19Read('extend/lib/standard_chain_pending_criteria.md');
const c11Doc = c19Read('extend/lib/standard_chain_crossref_index.md');
const c13Doc = c19Read('extend/lib/standard_chain_c13_crossref_index.md');
const contractSrc = c19Read('extend/lib/standard_chain_contract.js');
const adapterSrc = c19Read('extend/lib/standard_chain_adapter.js');
const b8Src = c19Read('extend/lib/standard_slot_m345.js');
const b9Src = c19Read('extend/lib/standard_chain_b9_slot_resolver.js');
const bridgePart = c19Read('extend/dialog/parts/01b_bridge.js');
const corePy = c19Read('flask_server/core/chat_completions.py');
const textPy = c19Read('flask_server/remote_bridge/channel/text.py');
const parsePy = c19Read('flask_server/remote_bridge/message_parse.py');
const outboundPy = c19Read('flask_server/remote_bridge/outbound.py');
const flowPy = c19Read('flask_server/remote_bridge/message_flow.py');
const routerPy = c19Read('flask_server/remote_bridge/message_router.py');
const bridgePy = c19Read('flask_server/routes/bridge.py');
const reportDoc = c19Read('docs/c19-s2-step9-protocol-retirement-inventory.md');

// 一、C-15 第二节第 9 行六列在文（本片主锚，实时自动抽出原句）。
c19Test('C-19 C-15 第 9 行：协议字段退役六列', () => {
  const row9 = c19Lines(c15Doc).filter((l) => l.indexOf('| 9 | 协议字段退役') === 0);
  c19Assert.equal(row9.length, 1);
  c19Assert.ok(c19Has(row9[0], 'B-7 范围服务端 / 网关 / `remote_bridge` 信封'));
  c19Assert.ok(c19Has(row9[0], '替换位列全、三网关零遗留'));
  c19Assert.ok(c19Has(row9[0], '`PROTOCOL_RETIREMENT_CONTRACT.status` 仍 declared-placeholder'));
  c19Assert.ok(c19Has(row9[0], '运行时退役面全未动（19:45 S3 不变）'));
  c19Assert.ok(c19Has(row9[0], 'bridge-chat-call 28 文件、bridge-chat-res 30 文件、is_tool_result 10 文件'));
  c19Assert.ok(c19Has(row9[0], 'run-command（01b_bridge.js + routes/bridge.py）'));
  c19Assert.ok(c19Has(row9[0], 'PROTOCOL_RETIREMENT_CONTRACT.status 保持声明态'));
});

// 二、C-8 九步表第 9 行与对拍矩阵 #13。
c19Test('C-19 C-8：九步表第 9 行与矩阵 #13', () => {
  c19Assert.ok(c19Has(matrixDoc, '| 9 | 协议字段退役 | B-7 范围：服务端 / 网关 / remote_bridge 信封 | 未交付 | 是 |'));
  c19Assert.ok(c19Has(matrixDoc, '| 13 | 协议字段退役 | A-7 未动该面 | PROTOCOL_RETIREMENT_CONTRACT 为 declared-placeholder | 待对拍 |'));
});

// 三、C-9 对应锚：G1 与范围声明，无独立第 9 步边界段（体例差如实登记）。
c19Test('C-19 C-9：G1 与不碰 B-7 退役面范围声明', () => {
  c19Assert.ok(c19Has(boundaryDoc, 'G1 **STATUS 恒为 `declared-placeholder`**'));
  c19Assert.ok(c19Has(boundaryDoc, '不碰 B-7 协议字段退役面'));
  c19Assert.ok(c19Has(boundaryDoc, '## 一、六段逐段边界语义'));
  c19Assert.ok(c19Has(boundaryDoc, '### 6. restore(sessionId, call)'));
  c19Assert.equal(c19Has(boundaryDoc, '### 9.'), false);
});

// 四、C-14 PROTOCOL 两签名行、C-10~C-13 索引行、第六节边界。
c19Test('C-19 C-14：PROTOCOL 两签名行与第六节边界', () => {
  c19Assert.ok(c19Has(tableDoc, '| PROTOCOL_RETIREMENT_CONTRACT.status | standard_chain_contract.js | declared-placeholder | 一致 | declared-placeholder |'));
  c19Assert.ok(c19Has(tableDoc, '| PROTOCOL_RETIREMENT_CONTRACT.direction | standard_chain_contract.js | standard tool_calls / tool message as the only key | 一致 | declared-placeholder |'));
  c19Assert.ok(c19Has(tableDoc, '| C-12 八槽映射 | standard_chain_replacement_map.md | M1-M8 八槽'));
  c19Assert.ok(c19Has(tableDoc, '| C-13 八槽索引 | standard_chain_c13_crossref_index.md |'));
  c19Assert.ok(c19Has(tableDoc, '## 六、execute 段实装登记'));
  const sec6 = tableDoc.split('## 六、execute 段实装登记')[1] || '';
  c19Assert.equal(c19Has(sec6, 'PROTOCOL_RETIREMENT_CONTRACT'), false);
});

// 五、contract PROTOCOL 冻结声明态 + adapter STATUS / KEY / EXECUTE_STATUS 独立。
c19Test('C-19 contract：PROTOCOL 冻结声明态与 STATUS 独立', () => {
  c19Assert.equal(ContractLib.PROTOCOL_RETIREMENT_CONTRACT.status, 'declared-placeholder');
  c19Assert.equal(ContractLib.PROTOCOL_RETIREMENT_CONTRACT.owner, 'B-7');
  c19Assert.equal(ContractLib.PROTOCOL_RETIREMENT_CONTRACT.legacy.length, 2);
  c19Assert.equal(ContractLib.PROTOCOL_RETIREMENT_CONTRACT.legacy[0], 'bridge-chat-call');
  c19Assert.equal(ContractLib.PROTOCOL_RETIREMENT_CONTRACT.legacy[1], 'bridge-chat-res');
  c19Assert.ok(c19Has(ContractLib.PROTOCOL_RETIREMENT_CONTRACT.direction, 'standard tool_calls / tool message as the only key'));
  c19Assert.equal(Object.isFrozen(ContractLib.PROTOCOL_RETIREMENT_CONTRACT), true);
  c19Assert.equal(AdapterLib.STATUS, 'declared-placeholder');
  c19Assert.equal(AdapterLib.KEY, 'tool_call.id');
  c19Assert.equal(AdapterLib.EXECUTE_STATUS, 'implemented-S2-step5');
  c19Assert.ok(c19Has(contractSrc, 'var PROTOCOL_RETIREMENT_CONTRACT = Object.freeze({'));
  c19Assert.ok(c19Has(contractSrc, 'PROTOCOL_RETIREMENT_CONTRACT: PROTOCOL_RETIREMENT_CONTRACT'));
  c19Assert.ok(c19Has(adapterSrc, 'declared-placeholder'));
});

// 六、b7 M1-M8 八槽、三网关 run-command 零命中、第四节显式声明。
c19Test('C-19 b7：M1-M8 八槽列全与三网关结论', () => {
  ['M1 bridge-chat-call', 'M2 bridge-chat-res', 'M3 run-command', 'M4 external-call', 'M5 is_tool_result', 'M6 三网关包装', 'M7 公共层解析', 'M8 旧标记兼容位'].forEach((m) => {
    c19Assert.ok(c19Has(b7Doc, '| ' + m + ' |'), 'missing ' + m);
  });
  c19Assert.ok(c19Has(b7Doc, '三网关（qq_gateway.py / wecom_gateway.py / weixin_gateway.py）grep `run-command` 零命中'));
  c19Assert.ok(c19Has(b7Doc, '旧标记摘除面（矩阵 #14 / S4）无协议字段替换位'));
  c19Assert.ok(c19Has(b7Doc, '不预设 B-7 总结论'));
});

// 七、C-12 八槽、C-10 / C-11 / C-13 索引、B-8 三槽与 B-9 五槽互斥。
c19Test('C-19 C-10~C-13 与 B-8 / B-9 八槽互斥', () => {
  ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8'].forEach((m) => {
    c19Assert.ok(c19Has(c12Doc, '### 槽位 ' + m), 'missing slot ' + m);
  });
  c19Assert.ok(c19Has(c12Doc, '| #13 协议字段退役 | S3 |'));
  c19Assert.ok(c19Has(c12Doc, '| #14 旧标记摘除 | S4 |'));
  c19Assert.ok(c19Has(c10Doc, 'S3'));
  c19Assert.ok(c19Has(c10Doc, '#13'));
  c19Assert.ok(c19Has(c11Doc, '14'));
  c19Assert.ok(c19Has(c13Doc, 'M1'));
  c19Assert.ok(c19Has(c13Doc, 'M8'));
  c19Assert.ok(c19Has(tableDoc, '两片源码互不 require、文件名不同、无文件交集'));
  c19Assert.ok(c19Has(b8Src, 'M3'));
  c19Assert.ok(c19Has(b8Src, 'M5'));
  c19Assert.equal(SlotResolver.SLOTS.length, 5);
  c19Assert.deepEqual(SlotResolver.SLOTS.map((s) => s.id).sort(), ['M1', 'M2', 'M6', 'M7', 'M8'].sort());
  c19Assert.ok(c19Has(b9Src, 'var STATUS = '));
});

// 八、b10 S3 / S4 收口条件与就绪度。
c19Test('C-19 b10：S3 三项收口条件与 S4 三项硬前置', () => {
  c19Assert.ok(c19Has(b10Doc, '| S3 #13 协议字段退役 | 替换位列全'));
  c19Assert.ok(c19Has(b10Doc, '契约面判一致≠运行时退役'));
  c19Assert.ok(c19Has(b10Doc, '①S2 装配实装并验收'));
  c19Assert.ok(c19Has(b10Doc, '| S4 #14 旧标记摘除 |'));
  c19Assert.ok(c19Has(b10Doc, '旧标记摘除当前不下发，前置未满足'));
  c19Assert.ok(c19Has(b10Doc, 'S1/S3 判一致不构成摘除触发'));
  c19Assert.ok(c19Has(b10Doc, 'c6 九文件顺序表未执行'));
});

// 九、活链协议字串落点只读反查（零写入）：run-command / 服务端 / remote_bridge。
c19Test('C-19 活链：协议字串落点只读反查', () => {
  c19Assert.equal(c19Count(bridgePart, 'run-command'), 2);
  c19Assert.ok(c19Has(bridgePart, '/api/bridge/run-command'));
  c19Assert.ok(c19Has(bridgePy, '@bp.route("/api/bridge/run-command", methods=["POST", "OPTIONS"])'));
  c19Assert.ok(c19Has(corePy, 'bridge-chat-call'));
  c19Assert.ok(c19Has(textPy, '("bridge-chat-call", "tool")'));
  c19Assert.ok(c19Has(textPy, '("bridge-chat-res", "tool")'));
  c19Assert.ok(c19Has(parsePy, 'bridge-chat-res'));
  c19Assert.equal(c19LineCount(outboundPy, 'is_tool_result'), 4);
  c19Assert.ok(c19Has(flowPy, 'is_tool_result'));
  c19Assert.ok(c19Has(routerPy, 'is_tool_result'));
  c19Assert.equal(c19Has(contractSrc, 'PROTOCOL_RETIREMENT_CONTRACT.status ='), false);
});

// 十、本报告六节齐全，差异登记不越复核输入边界。
c19Test('C-19 报告：六节齐全且结论仅为复核输入', () => {
  ['## 一、', '## 二、', '## 三、', '## 四、', '## 五、', '## 六、'].forEach((h) => {
    c19Assert.ok(c19Has(reportDoc, h));
  });
  c19Assert.ok(c19Has(reportDoc, '仅为分发方复核输入'));
  c19Assert.ok(c19Has(reportDoc, '不代拍板'));
  c19Assert.ok(c19Has(reportDoc, '不改 S1-S4 判态'));
  c19Assert.ok(c19Has(reportDoc, '不自行圈定下一实装面'));
  c19Assert.ok(c19Has(reportDoc, '不预设下发时点'));
  c19Assert.ok(c19Has(reportDoc, '阶段 3 不进入摘除步'));
});
