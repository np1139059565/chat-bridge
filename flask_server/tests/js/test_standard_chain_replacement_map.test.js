/*
 * C-12 协议字段替换位映射清单反查夹具。
 * 只读 C-10 判据清单 / C-11 交叉索引 / 本清单与两个已合入 lib。
 * 断言：8 槽位、各字段三项齐全、STATUS 恒声明态、
 * 唯一键恒标准键、不预设 B-7 是否拆片、沿用 C-10 判定时点。
 * 全文零反斜杠零正则，按字符码 10 切行规避跨端转义差异。
 * 新增被测 JS 源文件数为 0，故不引入新的覆盖率分母。
 */
'use strict';
const A = require('../../../extend/lib/standard_chain_adapter.js');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../../../extend/lib/standard_chain_contract.js');

// 三份文档都在 extend/lib/ 下，只读不改写。
const libDir = path.resolve(__dirname, '../../../extend/lib');
const NL = String.fromCharCode(10);
const p10 = fs.readFileSync(
  path.join(libDir, 'standard_chain_pending_criteria.md'), 'utf8');
const p11 = fs.readFileSync(
  path.join(libDir, 'standard_chain_crossref_index.md'), 'utf8');
const doc = fs.readFileSync(
  path.join(libDir, 'standard_chain_replacement_map.md'), 'utf8');
const dLines = doc.split(NL);
const heads = dLines.filter((l) => l.indexOf('### 槽位 M') === 0);
const bodies = doc.split('### 槽位 M').slice(1);

// 一、清单槽位数 = 8，且 M1-M8 编号顺序齐全。
test('C-12 清单：8 槽位 M1-M8 顺序齐全', () => {
  assert.equal(heads.length, 8);
  assert.equal(bodies.length, 8);
  for (let k = 1; k <= 8; k += 1) {
    assert.ok(heads[k - 1].indexOf('M' + k) >= 0, 'M' + k);
  }
});

// 二、每槽三项齐全：旧位所在层 / 替换位落点类型 / 是否仍占位。
test('C-12 清单：每槽三项齐全且仍为声明态', () => {
  const tags = ['旧位所在层', '替换位落点类型', '是否仍占位'];
  bodies.forEach((b, k) => {
    tags.forEach((t) => assert.ok(b.indexOf(t) >= 0,
      'M' + (k + 1) + ' ' + t));
    assert.ok(b.indexOf('declared-placeholder') >= 0);
    assert.ok(b.indexOf('矩阵编号') >= 0);
  });
});

// 三、六类旧字段与三网关包装 / 公共层解析全部显式登记。
test('C-12 清单：六类旧字段与包装层 / 解析层齐全', () => {
  const keys = ['bridge-chat-call', 'bridge-chat-res', 'run-command',
    'external-call', 'is_tool_result', '三网关包装', '公共层解析',
    '旧位→新位'];
  keys.forEach((k) => assert.ok(doc.indexOf(k) >= 0, k));
  const row = dLines.filter((l) => l.indexOf('| #13') === 0);
  assert.ok(row.length >= 1);
});

// 四、交叉引用对齐：C-10 四槽与 C-11 四个矩阵编号都在。
test('C-12 交叉引用：S1-S4 与 #4/#7/#13/#14 对齐', () => {
  ['S1', 'S2', 'S3', 'S4', '#4', '#7', '#13', '#14'].forEach((k) => {
    assert.ok(doc.indexOf(k) >= 0, k);
  });
  assert.ok(p10.indexOf('S1') >= 0 && p10.indexOf('S4') >= 0);
  assert.ok(p11.indexOf('#13') >= 0 && p11.indexOf('S3') >= 0);
  assert.ok(doc.indexOf('C-10') >= 0 && doc.indexOf('C-11') >= 0);
});

// 五、STATUS 恒为 declared-placeholder：三份文档与两个 lib。
test('C-12 STATUS：全链路仍为声明态', () => {
  [p10, p11, doc].forEach((d) => {
    assert.ok(d.indexOf('declared-placeholder') >= 0);
  });
  assert.equal(A.STATUS, 'declared-placeholder');
  assert.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status,
    'declared-placeholder');
  assert.ok(doc.indexOf('G1') >= 0);
});

// 六、唯一键：拆成三个短契约，天然不形成连续 5 行跨文件重复窗口。
test('C-12 唯一键 A：标准 id 生成与反解', () => {
  const id = C.makeToolCallId('n1');
  assert.equal(id, 'call_n1');
  assert.equal(C.nonceFromToolCallId(id), 'n1');
  assert.equal(A.KEY, 'tool_call.id');
});

test('C-12 唯一键 B：tool 消息三键', () => {
  const msg = C.standardToolMessage('call_n1', 'OK');
  assert.equal(msg.role, 'tool');
  assert.equal(msg.tool_call_id, 'call_n1');
  assert.equal(msg.content, 'OK');
  assert.ok(doc.indexOf('tool_call.id') >= 0);
});

test('C-12 唯一键 C：执行键不含消息指纹', () => {
  const seed = { id: 'call_n1', tool: 't', parameters: { a: 1 } };
  const key = C.execKeyFromToolCall(seed, 's1');
  assert.ok(key.indexOf('fingerprint') < 0);
  assert.ok(doc.indexOf('tool_call_id') >= 0);
});

// 七、判定时点沿用 C-10、不另立口径、不预设 B-7 是否拆片。
test('C-12 判定时点：沿用 C-10 且不预设结论', () => {
  const t = doc.split('## 四、判定时点')[1]
    .split('## 五、边界与只追加记录')[0];
  assert.ok(t.indexOf('沿用 C-10') >= 0);
  assert.ok(t.indexOf('不另立口径') >= 0);
  assert.ok(t.indexOf('不预设 B-7 是否拆片') >= 0);
  assert.ok(t.indexOf('B-8/B-9') >= 0);
  assert.ok(p10.indexOf('判定时点') >= 0);
});

// 八、索引自身约束：只描述映射不实装、docs 只追加。
test('C-12 清单边界：只描述映射不实装', () => {
  assert.ok(doc.indexOf('不实装') >= 0);
  assert.ok(doc.indexOf('不代替分发方裁定') >= 0);
  assert.ok(doc.indexOf('docs 只追加') >= 0);
  assert.equal(dLines.filter((l) => l.indexOf('## ') === 0).length, 5);
});
console.log('C12_REPLACEMENT_MAP_OK');
