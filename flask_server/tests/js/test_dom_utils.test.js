/* ============================================================
 * 前端公共工具测试（node 自带测试运行器）
 *
 * 覆盖 extend/lib/dom-utils.js 中的纯逻辑：
 *   - hashStr            稳定字符串哈希
 *   - toArray            任意值归一化为数组
 *   - messageFingerprint 消息内容指纹（卡片编号 / 去重的根基）
 *   - textOf             元素文本提取（传入替身对象验证）
 *
 * 运行方式：
 *   node --test flask_server/tests/js/
 *
 * 说明：dom-utils.js 是 IIFE，node 下把接口挂到 module.exports，
 * 故 require 后取 .AIMirrorDomUtils。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测模块：与浏览器共用同一份 dom-utils.js
const mod = require(path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js'));
const U = mod.AIMirrorDomUtils;

// ---------- hashStr ----------

test('hashStr：同输入同结果（稳定）', () => {
  assert.strictEqual(U.hashStr('hello'), U.hashStr('hello'));
});

test('hashStr：不同输入不同结果', () => {
  assert.notStrictEqual(U.hashStr('a'), U.hashStr('b'));
});

test('hashStr：空串也有确定结果（不抛异常）', () => {
  assert.strictEqual(typeof U.hashStr(''), 'string');
});

test('hashStr：返回 36 进制字符串', () => {
  assert.match(U.hashStr('abc'), /^[0-9a-z]+$/);
});

test('hashStr：相同前缀不应产生相同哈希（位置敏感）', () => {
  // djb2 逐字符累加，"ab" 与 "ba" 应不同，验证顺序被纳入
  assert.notStrictEqual(U.hashStr('ab'), U.hashStr('ba'));
});

// ---------- toArray ----------

test('toArray：数组原样返回', () => {
  const arr = [1, 2, 3];
  assert.strictEqual(U.toArray(arr), arr);
});

test('toArray：对象取 values 列表', () => {
  assert.deepStrictEqual(U.toArray({ a: 1, b: 2 }), [1, 2]);
});

test('toArray：字符串返回空数组（不拆字符）', () => {
  assert.deepStrictEqual(U.toArray('abc'), []);
});

test('toArray：null / undefined 返回空数组', () => {
  assert.deepStrictEqual(U.toArray(null), []);
  assert.deepStrictEqual(U.toArray(undefined), []);
});

test('toArray：数字返回空数组', () => {
  assert.deepStrictEqual(U.toArray(42), []);
});

test('toArray：空对象返回空数组', () => {
  assert.deepStrictEqual(U.toArray({}), []);
});

// ---------- messageFingerprint ----------

test('messageFingerprint：空消息返回固定指纹 m', () => {
  assert.strictEqual(U.messageFingerprint(null), 'm');
});

test('messageFingerprint：指纹以 m 开头', () => {
  assert.match(U.messageFingerprint({ role: 'user', blocks: [] }), /^m/);
});

test('messageFingerprint：同内容同指纹', () => {
  const a = { role: 'user', blocks: [{ type: 'text', text: 'hi' }] };
  const b = { role: 'user', blocks: [{ type: 'text', text: 'hi' }] };
  assert.strictEqual(U.messageFingerprint(a), U.messageFingerprint(b));
});

test('messageFingerprint：角色不同则指纹不同', () => {
  const blocks = [{ type: 'text', text: 'hi' }];
  assert.notStrictEqual(
    U.messageFingerprint({ role: 'user', blocks }),
    U.messageFingerprint({ role: 'assistant', blocks })
  );
});

test('messageFingerprint：思考块不参与（内容相同则指纹相同）', () => {
  const withThink = { role: 'assistant', blocks: [{ type: 'thinking', text: 'X' }, { type: 'text', text: 'hi' }] };
  const without = { role: 'assistant', blocks: [{ type: 'text', text: 'hi' }] };
  assert.strictEqual(U.messageFingerprint(withThink), U.messageFingerprint(without));
});

test('messageFingerprint：图片块不参与（内容相同则指纹相同）', () => {
  const withImg = { role: 'user', blocks: [{ type: 'image', src: 'blob:aaa' }, { type: 'text', text: 'hi' }] };
  const without = { role: 'user', blocks: [{ type: 'text', text: 'hi' }] };
  assert.strictEqual(U.messageFingerprint(withImg), U.messageFingerprint(without));
});

test('messageFingerprint：列表块 items 被序列化成非数组也不抛异常', () => {
  // 模拟旧存档把 items 序列化成对象
  const msg = { role: 'assistant', blocks: [{ type: 'list', ordered: false, items: { 0: 'a', 1: 'b' } }] };
  assert.doesNotThrow(() => U.messageFingerprint(msg));
});

test('messageFingerprint：blocks 缺失不抛异常', () => {
  assert.doesNotThrow(() => U.messageFingerprint({ role: 'user' }));
});

test('messageFingerprint：blocks 被序列化成对象不抛异常', () => {
  const msg = { role: 'user', blocks: { 0: { type: 'text', text: 'x' } } };
  assert.doesNotThrow(() => U.messageFingerprint(msg));
});

test('messageFingerprint：代码块内容变化则指纹变化', () => {
  const a = { role: 'assistant', blocks: [{ type: 'code', lang: 'js', code: 'a' }] };
  const b = { role: 'assistant', blocks: [{ type: 'code', lang: 'js', code: 'b' }] };
  assert.notStrictEqual(U.messageFingerprint(a), U.messageFingerprint(b));
});

// ---------- textOf ----------

test('textOf：读取 innerText 并去空白', () => {
  assert.strictEqual(U.textOf({ innerText: '  hi  ' }), 'hi');
});

test('textOf：innerText 缺失时回退 textContent', () => {
  assert.strictEqual(U.textOf({ textContent: 'fallback' }), 'fallback');
});

test('textOf：元素为空返回空串', () => {
  assert.strictEqual(U.textOf(null), '');
  assert.strictEqual(U.textOf(undefined), '');
});

// ---------- debounce ----------

test('debounce：连续调用只执行最后一次', async () => {
  let count = 0;
  const fn = U.debounce(() => { count++; }, 10);
  fn(); fn(); fn();
  await new Promise((r) => setTimeout(r, 40));
  assert.strictEqual(count, 1);
});
