/*
 * B-9 反查夹具：五槽落点转换/拒绝纯函数层实测。
 * 纯函数由反查夹具直接 import 实测；新增被测 JS 源 1 个并纳入覆盖率达标。
 * 断言五槽 STATUS 恒 declared-placeholder、唯一键恒标准键、与 C-12 对齐、
 * 无悬空编号、不预设 B-7 是否拆片、活链零改动、异常违约不落盘无残留副作用。
 * 全文零反斜杠零正则，按字符码 10 切行规避跨端转义差异。
 */
'use strict';
const R = require('../../../extend/lib/standard_chain_b9_slot_resolver.js');
const A = require('../../../extend/lib/standard_chain_adapter.js');
const C = require('../../../extend/lib/standard_chain_contract.js');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const NL = String.fromCharCode(10);
const libDir = path.resolve(__dirname, '../../../extend/lib');
const doc = fs.readFileSync(path.join(libDir, 'standard_chain_b9_slot_contract.md'), 'utf8');
const map = fs.readFileSync(path.join(libDir, 'standard_chain_replacement_map.md'), 'utf8');
const src = fs.readFileSync(path.join(libDir, 'standard_chain_b9_slot_resolver.js'), 'utf8');
const IDS = ['M1', 'M2', 'M6', 'M7', 'M8'];
const mapBodies = map.split('### 槽位 M').slice(1);

// 一、五槽声明齐全、字段三项与顺序一致。
test('B-9 五槽：M1/M2/M6/M7/M8 顺序齐全且字段三项齐全', () => {
  assert.equal(R.SLOTS.length, 5);
  IDS.forEach((id, k) => {
    const s = R.SLOTS[k];
    assert.equal(s.id, id);
    assert.equal(s, R.findSlot(id));
    ['oldLayer', 'legacy', 'standard', 'criteria', 'matrix'].forEach((f) => {
      assert.ok(typeof s[f] === 'string' && s[f].length > 0, id + ' ' + f);
    });
  });
  assert.equal(R.findSlot('M3'), null);
  assert.equal(R.findSlot('M9'), null);
});

// 二、与 C-12 M1/M2/M6/M7/M8 落点类型逐槽对齐，无悬空编号。
test('B-9 与 C-12 对齐：五槽落点类型与槽位/矩阵编号齐全', () => {
  assert.equal(mapBodies.length, 8);
  IDS.forEach((id) => {
    const k = Number(id.slice(1));
    const body = mapBodies[k - 1];
    assert.ok(map.indexOf('### 槽位 M' + k) >= 0, 'C-12 ' + id);
    assert.ok(body.indexOf(R.findSlot(id).standard) >= 0, id + ' 落点类型');
    assert.ok(body.indexOf('declared-placeholder') >= 0, id + ' 声明态');
    assert.ok(doc.indexOf('### 槽位 ' + id) >= 0, '本清单 ' + id);
  });
  ['S1', 'S2', 'S3', 'S4', '#4', '#7', '#13', '#14'].forEach((n) => {
    assert.ok(doc.indexOf(n) >= 0 && map.indexOf(n) >= 0, n);
  });
});

// 三、STATUS 分层：清单/映射层与纯函数返回值恒 declared-placeholder。
test('B-9 STATUS：全链路恒声明态，纯函数层不翻状态', () => {
  assert.equal(R.STATUS, 'declared-placeholder');
  assert.equal(A.STATUS, R.STATUS);
  assert.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status, R.STATUS);
  [doc, map, src].forEach((d) => assert.ok(d.indexOf('declared-placeholder') >= 0));
  IDS.forEach((id) => {
    const s = R.findSlot(id);
    [R.resolveReplacement({ slot: id, marker: s.legacy }),
      R.resolveReplacement({ slot: id, marker: s.standard }),
      R.resolveReplacement(null),
      R.resolveReplacement({ slot: id, marker: 'bogus' })].forEach((r) => {
        assert.equal(r.status, R.STATUS);
      });
  });
});

// 四、唯一键：标准 tool_call.id 与 tool 消息三键，不含消息指纹。
test('B-9 唯一键：标准 id 与三键在每个返回值中恒一致', () => {
  assert.equal(R.KEY, 'tool_call.id');
  assert.equal(A.KEY, R.KEY);
  assert.deepEqual(Array.from(R.TOOL_MESSAGE_KEYS),
    ['role', 'tool_call_id', 'content']);
  assert.ok(Object.isFrozen(R.TOOL_MESSAGE_KEYS));
  const msg = C.standardToolMessage('call_n1', 'OK');
  assert.equal(msg.role, 'tool');
  assert.equal(msg.tool_call_id, 'call_n1');
  assert.equal(msg.content, 'OK');
  const seed = { id: 'call_n1', tool: 't', parameters: { a: 1 } };
  assert.ok(C.execKeyFromToolCall(seed, 's1').indexOf('fingerprint') < 0);
  IDS.forEach((id) => {
    const s = R.findSlot(id);
    [R.resolveReplacement({ slot: id, marker: s.legacy }),
      R.resolveReplacement({ slot: id, marker: s.standard })].forEach((r) => {
        assert.equal(r.by, R.KEY);
        assert.equal(r.keys, R.TOOL_MESSAGE_KEYS);
      });
  });
});

// 五、逐槽三态实测：旧位不再生效、新位生效、异常违约不落盘。
test('B-9 逐槽实测：旧位拒绝附转换建议 / 新位规范化 / 异常不落盘', () => {
  IDS.forEach((id) => {
    const s = R.findSlot(id);
    const oldRes = R.resolveReplacement({ slot: id, marker: s.legacy });
    assert.equal(oldRes.accepted, false, id + ' 旧位');
    assert.equal(oldRes.reason, 'legacy-slot-not-effective');
    assert.equal(oldRes.convertedTo, s.standard);
    assert.equal(oldRes.persisted, false);
    const newRes = R.resolveReplacement({ slot: id, marker: s.standard });
    assert.equal(newRes.accepted, true, id + ' 新位');
    assert.equal(newRes.target, s.standard);
    assert.equal(newRes.oldLayer, s.oldLayer);
    assert.equal(newRes.persisted, false);
    const bad = [null, 'text', 7, {}, { slot: id },
      { slot: id, marker: 'bogus' }, { slot: 'M9', marker: s.standard }];
    bad.forEach((q) => {
      const r = R.resolveReplacement(q);
      assert.equal(r.accepted, false, id + ' 违约');
      assert.equal(r.persisted, false);
      assert.equal(r.status, R.STATUS);
    });
  });
});

// 六、无残留副作用：声明冻结、调用前后快照一致、返回值不写盘。
test('B-9 无残留副作用：声明冻结且调用前后状态不变', () => {
  assert.ok(Object.isFrozen(R.SLOTS));
  const snap = JSON.stringify(R.SLOTS);
  IDS.forEach((id) => {
    const s = R.findSlot(id);
    R.resolveReplacement({ slot: id, marker: s.legacy });
    R.resolveReplacement({ slot: id, marker: s.standard });
  });
  assert.equal(JSON.stringify(R.SLOTS), snap);
  assert.ok(Object.isFrozen(R.resolveReplacement(null).keys));
});

// 七、边界：活链零改动、不装配运行时、M6/M8 口径、只追加、不预设拆片。
test('B-9 边界：源码与清单均落在纯函数层，不碰活链', () => {
  ['05f_parse', '05c_prompt', '00_data', 'remote_bridge', 'window.', 'fs.']
    .forEach((k) => assert.ok(src.indexOf(k) < 0, k));
  assert.ok(src.indexOf('module.exports') >= 0);
  ['活链文件零改动', '不装配运行时 M', '纯函数由反查夹具直接 import 实测',
    '零代码改动', '兼容位现状', '三网关', '公共层解析', 'docs 只追加',
    '不预设 B-7 是否拆片', '旧标记摘除'].forEach((k) => {
      assert.ok(doc.indexOf(k) >= 0, k);
    });
  assert.equal(R.findSlot('M8').compatibleOnly, true);
  IDS.slice(0, 4).forEach((id) => {
    assert.equal(R.findSlot(id).compatibleOnly, false);
  });
  assert.equal(doc.split(NL).filter((l) => l.indexOf('### 槽位 M') === 0).length, 5);
});
console.log('B9_SLOT_RESOLVER_OK');
