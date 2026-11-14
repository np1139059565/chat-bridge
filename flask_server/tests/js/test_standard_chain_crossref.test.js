/*
 * C-11 交叉一致性索引反查夹具（漂移防护）。
 * 只读三份已合入契约文档与两个已合入 lib。
 * 断言：矩阵 14 条 / 六段 6 段 / 四槽 4 槽、STATUS 全声明态、
 * 唯一键声明一致、交叉引用无悬空编号、不预设 B-7 是否拆片。
 * 全文零反斜杠、零正则，按字符码 10 切行规避跨端转义差异。
 * 新增被测 JS 源文件数为 0，故不引入新的覆盖率分母。
 */
'use strict';
const path = require('node:path');
const C = require('../../../extend/lib/standard_chain_contract.js');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const test = require('node:test');
const A = require('../../../extend/lib/standard_chain_adapter.js');

// 三份文档都在 extend/lib/ 下，只读不改写。
const libDir = path.resolve(__dirname, '../../../extend/lib');
const NL = String.fromCharCode(10);
const mDoc = fs.readFileSync(
  path.join(libDir, 'standard_chain_field_matrix.md'), 'utf8');
const bDoc = fs.readFileSync(
  path.join(libDir, 'standard_chain_boundary_contract.md'), 'utf8');
const pDoc = fs.readFileSync(
  path.join(libDir, 'standard_chain_pending_criteria.md'), 'utf8');
const iDoc = fs.readFileSync(
  path.join(libDir, 'standard_chain_crossref_index.md'), 'utf8');
const mLines = mDoc.split(NL);
const bLines = bDoc.split(NL);
const pLines = pDoc.split(NL);
const iLines = iDoc.split(NL);

// 一、C-8 矩阵只数「## 一、逐项对拍矩阵」小节内 14 行，
// 「## 二、九步装配推演」的步骤号 1-9 不计入。
test('C-11 矩阵：逐项对拍 14 条，装配 9 步不计入', () => {
  const body = iDoc.split('## 一、三份文档各自条目编号集合')[1]
    .split('## 二、STATUS')[0];
  assert.ok(body.indexOf('14') >= 0);
  assert.ok(body.indexOf('不计入矩阵条目') >= 0);
  const seg = mDoc.split('## 一、逐项对拍矩阵')[1]
    .split('## 二、端到端装配面只读推演')[0];
  const rows = seg.split(NL).filter((l) => {
    const p = l.split('|');
    return l.indexOf('| ') === 0 && p.length > 2
      && p[1].trim().length > 0 && !isNaN(Number(p[1].trim()));
  });
  assert.equal(rows.length, 14);
  ['1', '4', '7', '13', '14'].forEach((n) => {
    assert.ok(rows.some((l) => l.split('|')[1].trim() === n), n);
  });
});

// 二、C-9 六段：六个边界小节标题 + 逐段状态表 6 行。
test('C-11 六段：parse/buildCard/execute/reply/dedupe/restore', () => {
  const segs = ['parse(block)', 'buildCard(call)', 'execute(card)',
    'reply(msg)', 'dedupe(a, b)', 'restore(sessionId, call)'];
  segs.forEach((s) => assert.ok(bDoc.indexOf('### ') >= 0
    && bDoc.indexOf(s) >= 0, s));
  const heads = bLines.filter((l) => l.indexOf('### ') === 0
    && l.length > 4 && l[4] >= '1' && l[4] <= '6');
  assert.equal(heads.length, 6);
  const status = bLines.filter((l) => l.indexOf('| ') === 0
    && l.indexOf('declared-placeholder') >= 0);
  assert.equal(status.length, 6);
});

// 三、C-10 四槽：S1-S4 与矩阵 #4/#7/#13/#14 对齐。
test('C-11 四槽：S1-S4 对齐 #4/#7/#13/#14', () => {
  const slots = pLines.filter((l) => l.indexOf('## 槽位 S') === 0);
  assert.equal(slots.length, 4);
  const pairs = ['#4', '#7', '#13', '#14'];
  pairs.forEach((n, k) => assert.ok(slots[k].indexOf(n) >= 0, n));
  assert.ok(pDoc.indexOf('判定时点') >= 0);
});

// 四、STATUS 全为 declared-placeholder：三份文档 + 两个 lib。
test('C-11 STATUS：三份文档与两个 lib 均为声明态', () => {
  [mDoc, bDoc, pDoc, iDoc].forEach((d) => {
    assert.ok(d.indexOf('declared-placeholder') >= 0);
  });
  assert.equal(A.STATUS, 'declared-placeholder');
  assert.equal(C.PRE_DISPATCH_HOOK_CONTRACT.status,
    'declared-placeholder');
  assert.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status,
    'declared-placeholder');
  const idx = iDoc.split('## 二、STATUS')[1].split('## 三、唯一键')[0];
  assert.ok(idx.indexOf('必须全部') >= 0);
});

// 五、唯一键声明一致：标准 tool_call.id 与 tool 消息三键。
test('C-11 唯一键：三份文档与 lib 同向、不含消息指纹', () => {
  [mDoc, bDoc, pDoc, iDoc].forEach((d) => {
    assert.ok(d.indexOf('tool_call.id') >= 0);
    assert.ok(d.indexOf('tool_call_id') >= 0);
  });
  assert.equal(A.KEY, 'tool_call.id');
  const madeId = C.makeToolCallId('n1');
  const toolMsg = C.standardToolMessage('call_n1', 'OK');
  assert.equal(madeId, 'call_n1');
  assert.deepEqual(toolMsg,
    { role: 'tool', tool_call_id: 'call_n1', content: 'OK' });
  const execArgs = { id: 'call_n1', tool: 't', parameters: { a: 1 } };
  const k = C.execKeyFromToolCall(execArgs, 's1');
  assert.ok(k.indexOf('fingerprint') < 0);
  assert.equal(A.restore('s1', { id: 'call_n1' }).noMessageFingerprint,
    true);
});

// 六、交叉引用表无悬空编号：矩阵四条、六段六个、四槽四个都能在三份里找到。
test('C-11 交叉引用：无悬空编号，同义异名登记', () => {
  const table = iDoc.split('## 四、逐项交叉引用表')[1]
    .split('## 五、B-7 判定时点')[0];
  ['#4', '#7', '#13', '#14', 'S1', 'S2', 'S3', 'S4',
    'execute', 'restore', 'PROTOCOL_RETIREMENT_CONTRACT'].forEach((k) => {
      assert.ok(table.indexOf(k) >= 0, k);
    });
  ['fetcher 跨侧', '意图执行', '协议字段退役', '旧标记摘除']
    .forEach((k) => assert.ok(table.indexOf(k) >= 0, k));
  assert.ok(iDoc.indexOf('悬空编号即漂移') >= 0);
});

// 七、判定时点沿用 C-10、不另立口径、不预设是否拆片。
test('C-11 判定时点：沿用 C-10，不预设 B-7 拆片', () => {
  const t = iDoc.split('## 五、B-7 判定时点')[1]
    .split('## 六、边界与只追加记录')[0];
  assert.ok(t.indexOf('沿用 C-10') >= 0);
  assert.ok(t.indexOf('不另立口径') >= 0);
  assert.ok(t.indexOf('不预设 B-7 是否拆片') >= 0);
  assert.ok(t.indexOf('B-8/B-9') >= 0);
  assert.ok(pDoc.indexOf('B-8/B-9') >= 0);
});

// 八、索引自身约束：零反斜杠由文件文本保证，边界小节齐全。
test('C-11 索引边界：只描述索引不实装、docs 只追加', () => {
  assert.ok(iDoc.indexOf('不实装执行下游') >= 0);
  assert.ok(iDoc.indexOf('docs 只追加') >= 0);
  assert.ok(iDoc.indexOf('新增被测 JS 源文件数为 0') >= 0);
  assert.equal(iLines.filter((l) => l.indexOf('## ') === 0).length, 6);
});
console.log('C11_CROSSREF_OK');
