/* ============================================================
 * 文件提取与挂载行为测试
 *
 * 背景：
 *   read_file 返回的文件要挂到「触发它的那条用户消息」上。挂载靠文字匹配：
 *   卡片登记时记下文字，消息入树后按文字包含关系认领。
 *   这套逻辑此前没有任何行为测试，字段漏一个、匹配错一条都不会报错，
 *   表现只是「文件按钮不出现」或「文件挂到别人消息上」。
 *
 * 覆盖点：
 *   1. extractFile 认单文件、批量文件、整文件路径、分段 dataURL
 *   2. extractFile 拒绝非法项（无 path / content 不是 dataURL）
 *   3. 文字匹配挂载：命中、不命中、多图对多消息
 *   4. 命中后关联被移除，同一批文件不会挂到后续消息
 *
 * 运行：node --test flask_server/tests/js/*.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// ---- 全局桩：必须在加载被测模块之前就位（公共实现见 _part_stub）----
const dialog = require('./_part_stub').installStub();
// 05i 用到 Vue.h 造节点；测试只关心节点描述，给哑实现即可
global.Vue = { h: (tag, props, children) => ({ tag, props, children }) };

require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05i_files.js'));

const M = dialog.methods;
const D = dialog;

/**
 * 造一个会话对象。
 *
 * @param {Array} pendingFiles 待挂载的文件关联
 * @returns {Object} 会话
 */
function makeConv(pendingFiles) {
  return { msgTree: {}, pendingFiles: pendingFiles || [] };
}

/**
 * 造一条用户消息。
 *
 * @param {string} text 消息文字
 * @returns {Object} 消息对象
 */
function makeUserMsg(text) {
  return { id: 'm-' + text, role: 'user', blocks: [{ type: 'paragraph', text: text }] };
}

test('extractFile：单文件用 data.file 承载', () => {
  const result = { data: { file: { source: true, path: '/tmp/a.txt', name: 'a.txt', mime: 'text/plain' } } };
  const out = D.extractFile(result);
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].source, true);
  assert.strictEqual(out[0].path, '/tmp/a.txt');
});

test('extractFile：批量用 data.files 数组承载', () => {
  const result = { data: { files: [
    { source: true, path: '/a', name: 'a' },
    { source: true, path: '/b', name: 'b' }
  ] } };
  const out = D.extractFile(result);
  assert.strictEqual(out.length, 2);
  assert.deepStrictEqual(out.map((f) => f.path), ['/a', '/b']);
});

test('extractFile：单文件与批量同时存在时都要收', () => {
  // 这是真实场景：主结果一条、附带文件若干
  const result = { data: {
    file: { source: true, path: '/main', name: 'main' },
    files: [{ source: true, path: '/extra', name: 'extra' }]
  } };
  const out = D.extractFile(result);
  assert.strictEqual(out.length, 2);
});

test('extractFile：分段文件按 dataURL 承载', () => {
  const result = { data: { file: { content: 'data:text/plain;base64,QUJD', name: 'seg', mime: 'text/plain' } } };
  const out = D.extractFile(result);
  assert.strictEqual(out.length, 1);
  assert.strictEqual(out[0].source, false);
  assert.strictEqual(out[0].content, 'data:text/plain;base64,QUJD');
});

test('extractFile：content 不是 dataURL 的项被丢弃', () => {
  const result = { data: { file: { content: 'plain text', name: 'x' } } };
  assert.deepStrictEqual(D.extractFile(result), []);
});

test('extractFile：无 data 或 data 非对象时返回空数组', () => {
  assert.deepStrictEqual(D.extractFile(null), []);
  assert.deepStrictEqual(D.extractFile({}), []);
  assert.deepStrictEqual(D.extractFile({ data: 'oops' }), []);
});

test('挂载：文字命中时文件挂到该消息上', () => {
  const conv = makeConv([{ text: '读取报告', files: [{ name: 'r.txt' }] }]);
  const msg = makeUserMsg('请帮我读取报告');
  M._attachPendingFiles(conv, [msg]);
  assert.deepStrictEqual(msg.files, [{ name: 'r.txt' }]);
});

test('挂载：文字不命中时不挂', () => {
  const conv = makeConv([{ text: '读取报告', files: [{ name: 'r.txt' }] }]);
  const msg = makeUserMsg('完全无关的话');
  M._attachPendingFiles(conv, [msg]);
  assert.strictEqual(msg.files, undefined);
});

test('挂载：命中后关联被移除，不会重复挂到后续消息', () => {
  const conv = makeConv([{ text: '报告', files: [{ name: 'r.txt' }] }]);
  const m1 = makeUserMsg('看这个报告');
  const m2 = makeUserMsg('还有这个报告');
  M._attachPendingFiles(conv, [m1, m2]);
  // 只有第一条认领成功
  assert.ok(Array.isArray(m1.files));
  assert.strictEqual(m2.files, undefined);
  // 关联表已清空
  assert.strictEqual(conv.pendingFiles.length, 0);
});

test('挂载：多文件对多消息，各认领各的', () => {
  const conv = makeConv([
    { text: '甲文件', files: [{ name: 'a.txt' }] },
    { text: '乙文件', files: [{ name: 'b.txt' }] }
  ]);
  const m1 = makeUserMsg('看甲文件');
  const m2 = makeUserMsg('看乙文件');
  M._attachPendingFiles(conv, [m1, m2]);
  assert.strictEqual(m1.files[0].name, 'a.txt');
  assert.strictEqual(m2.files[0].name, 'b.txt');
});

test('挂载：只处理用户消息，助手消息不认领', () => {
  const conv = makeConv([{ text: '报告', files: [{ name: 'r.txt' }] }]);
  const msg = { id: 'a1', role: 'assistant', blocks: [{ type: 'paragraph', text: '关于报告' }] };
  M._attachPendingFiles(conv, [msg]);
  assert.strictEqual(msg.files, undefined);
  // 关联仍在，留给真正的用户消息
  assert.strictEqual(conv.pendingFiles.length, 1);
});
