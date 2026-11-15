/*
 * A-11 reply 单点边界反查夹具（零代码改动的只读取证片）。
 * 只读 require 已合入 adapter / contract 两个 lib；契约 .md 与活链文件
 * 按字符码 10 切行、普通 indexOf / split 反查（零反斜杠零正则）。
 * 覆盖：返回形状恰四键、role 硬编码、content 不回显、缺键归一、
 * 强制归一不抛错、幂等新对象、C-9 / C-14 两处标注对拍、运行期零调用方。
 * 新增被测 JS 源 0；无 fs 写 / shell / 网络。
 */
'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const AD = require('../../../extend/lib/standard_chain_adapter.js');
const SC = require('../../../extend/lib/standard_chain_contract.js');

const LF = String.fromCharCode(10);
const repoRoot = path.resolve(__dirname, '../../..');
function read(rel) { return fs.readFileSync(path.join(repoRoot, rel), 'utf8'); }
function has(text, needle) { return text.indexOf(needle) >= 0; }
function line(text, head) {
  const hit = text.split(LF).filter((l) => l.indexOf(head) === 0);
  return hit;
}
const adapterSrc = read('extend/lib/standard_chain_adapter.js');
const boundary = read('extend/lib/standard_chain_boundary_contract.md');
const table = read('extend/lib/standard_chain_c14_signature_table.md');
const executePart = read('extend/dialog/parts/06_execute.js');
const parsePart = read('extend/dialog/parts/05f_parse.js');
const dataPart = read('extend/dialog/parts/00_data.js');
const cardsPart = read('extend/dialog/parts/05g_cards.js');
const dialogHtml = read('extend/dialog/dialog.html');
const FLAT = { by: 'tool_call.id', role: 'tool', tool_call_id: null, status: 'declared-placeholder' };

// 一、导出面：reply 在六段内，STATUS / KEY / EXECUTE_STATUS 三个常量不漂移。
test('A-11 导出面：reply 在六段导出内且三个常量不漂移', () => {
  assert.equal(typeof AD.reply, 'function');
  ['parse', 'buildCard', 'execute', 'reply', 'dedupe', 'restore'].forEach((n) => {
    assert.equal(typeof AD[n], 'function');
  });
  assert.equal(AD.STATUS, 'declared-placeholder');
  assert.equal(AD.KEY, 'tool_call.id');
  assert.equal(AD.EXECUTE_STATUS, 'implemented-S2-step5');
});

// 二、返回形状：完整入参恰四键，content 键不存在。
test('A-11 形状：完整入参返回恰四键且 content 不回显', () => {
  const out = AD.reply({ role: 'tool', tool_call_id: 'call_a11', content: 'OK' });
  assert.deepEqual(Object.keys(out).sort(), ['by', 'role', 'status', 'tool_call_id']);
  assert.equal(out.by, 'tool_call.id');
  assert.equal(out.role, 'tool');
  assert.equal(out.tool_call_id, 'call_a11');
  assert.equal(out.status, 'declared-placeholder');
  assert.equal(Object.prototype.hasOwnProperty.call(out, 'content'), false);
});

// 三、缺键归一：四类残缺入参一律深等于扁平形状，不抛错。
test('A-11 缺键归一：残缺入参深等于扁平形状', () => {
  const holes = [null, undefined, {}, { role: 'tool' }];
  holes.forEach((m) => {
    assert.deepEqual(AD.reply(m), FLAT);
  });
});

// 四、role 硬编码：非 tool 角色与类型扰动不改输出、不回显入参。
test('A-11 role 硬编码常量：角色扰动不改变输出', () => {
  const odd = ['assistant', 'user', 'function', '', 42, null];
  odd.forEach((r) => {
    const out = AD.reply({ role: r, tool_call_id: 'call_x' });
    assert.equal(out.role, 'tool');
    assert.equal(out.tool_call_id, 'call_x');
    assert.equal(out.by, 'tool_call.id');
  });
});

// 五、不抛错与幂等：非对象入参不抛，同参两次新对象深相等。
test('A-11 幂等与新对象：重复调用等价且不共享引用', () => {
  const m = { role: 'tool', tool_call_id: 'call_same', content: 'x' };
  const first = AD.reply(m);
  const second = AD.reply(m);
  assert.notEqual(first, second);
  assert.deepEqual(first, second);
  ['str', 42, true, []].forEach((v) => {
    assert.doesNotThrow(() => AD.reply(v));
  });
});

// 六、C-9 对拍：第一节第 4 段边界表与第二节状态行逐格在文。
test('A-11 C-9 对拍：reply 两处标注与代码实况一致', () => {
  assert.ok(has(boundary, '### 4. reply(msg)'));
  assert.ok(has(boundary, '硬编码常量'));
  assert.ok(has(boundary, '不回显入参 role、不抛错'));
  const statusRows = line(boundary, '| reply | declared-placeholder |');
  assert.equal(statusRows.length, 1);
  assert.ok(has(statusRows[0], 'tool 三键'));
  assert.ok(has(statusRows[0], 'n/a'));
  assert.ok(has(statusRows[0], '否'));
});

// 七、C-14 对拍：第二节 reply 行逐格一致，第六节 B-12 只追加登记不涉 reply。
test('A-11 C-14 对拍：签名行一致且第六节无 reply 字样', () => {
  assert.ok(has(table, '## 六、execute 段实装登记'));
  const replyRows = line(table, '| reply(msg) |');
  assert.equal(replyRows.length, 1);
  assert.ok(has(replyRows[0], 'standard_chain_adapter.js'));
  assert.ok(has(replyRows[0], '返回 by=KEY、role=tool、tool_call_id、status=STATUS'));
  assert.ok(has(replyRows[0], '一致'));
  assert.ok(has(replyRows[0], 'declared-placeholder'));
  const sec6 = table.slice(table.indexOf('## 六、'));
  assert.equal(sec6.indexOf('reply') >= 0, false);
});

// 八、运行期取证：源内唯一定义、活链零调用方、三键由 standardToolMessage 产出。
test('A-11 运行期取证：零调用方且 tool 三键不含消息指纹', () => {
  assert.equal(adapterSrc.split('function reply(').length - 1, 1);
  const liveParts = [executePart, parsePart, dataPart, cardsPart, dialogHtml];
  liveParts.forEach((src) => {
    assert.equal(src.indexOf('.reply(') >= 0, false);
  });
  assert.ok(has(dialogHtml, 'standard_chain_adapter.js'));
  const tm = SC.standardToolMessage('call_a11', 'OK');
  assert.deepEqual(tm, { role: 'tool', tool_call_id: 'call_a11', content: 'OK' });
  assert.equal(Object.prototype.hasOwnProperty.call(tm, 'msgId'), false);
});
