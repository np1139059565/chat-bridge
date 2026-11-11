/* ============================================================
 * 工具参数声明适配层测试（node 自带测试运行器）
 *
 * 覆盖 extend/lib/tool-schema-adapter.js 的纯逻辑：标准 schema 还原、
 * anyOf 首支、required 归属、旧数组兼容与异常输入兜底。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const mod = require(path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'tool-schema-adapter.js'));
const toFlatParams = mod.toFlatParams;

test('标准 schema：properties 键即参数名，顶层 required 标必填', () => {
  const s = {
    type: 'object',
    properties: {
      path: { type: 'string', description: '路径' },
      limit: { type: 'integer' }
    },
    required: ['path']
  };
  assert.deepStrictEqual(toFlatParams(s), [
    { name: 'path', type: 'string', required: true, description: '路径' },
    { name: 'limit', type: 'integer', required: false, description: '' }
  ]);
});

test('anyOf 取首支作展示类型', () => {
  const s = { type: 'object', properties: { path: { anyOf: [{ type: 'string' }, { type: 'array' }], description: '路径' } }, required: ['path'] };
  assert.strictEqual(toFlatParams(s)[0].type, 'string');
});

test('anyOf 首支无 type 回退 string', () => {
  const s = { type: 'object', properties: { p: { anyOf: [{ description: 'x' }] } } };
  assert.strictEqual(toFlatParams(s)[0].type, 'string');
});

test('anyOf 为空数组时走 prop.type', () => {
  const s = { type: 'object', properties: { p: { type: 'boolean', anyOf: [] } } };
  assert.strictEqual(toFlatParams(s)[0].type, 'boolean');
});

test('属性无 type 回退 string', () => {
  const s = { type: 'object', properties: { p: { description: '说明' } } };
  assert.strictEqual(toFlatParams(s)[0].type, 'string');
  assert.strictEqual(toFlatParams(s)[0].description, '说明');
});

test('无 required 时全部非必填', () => {
  const s = { type: 'object', properties: { a: { type: 'string' } } };
  assert.strictEqual(toFlatParams(s)[0].required, false);
});

test('required 非数组按空处理', () => {
  const s = { type: 'object', properties: { a: { type: 'string' } }, required: 'a' };
  assert.strictEqual(toFlatParams(s)[0].required, false);
});

test('无 properties 返回空数组', () => {
  assert.deepStrictEqual(toFlatParams({ type: 'object' }), []);
});

test('空 schema 对象返回空数组', () => {
  assert.deepStrictEqual(toFlatParams({}), []);
});

test('属性为 null 时字段仍齐全', () => {
  const s = { type: 'object', properties: { p: null }, required: ['p'] };
  assert.deepStrictEqual(toFlatParams(s), [{ name: 'p', type: 'string', required: true, description: '' }]);
});

test('旧扁平数组原样返回副本（兼容历史 tool.json）', () => {
  const arr = [{ name: 'a', type: 'string', required: true, description: 'x' }];
  const got = toFlatParams(arr);
  assert.deepStrictEqual(got, arr);
  assert.notStrictEqual(got, arr);
});

test('null / 字符串 / 数字返回空数组，不抛异常', () => {
  assert.deepStrictEqual(toFlatParams(null), []);
  assert.deepStrictEqual(toFlatParams('x'), []);
  assert.deepStrictEqual(toFlatParams(3), []);
  assert.deepStrictEqual(toFlatParams(undefined), []);
});

test('接口同时挂到全局与 module.exports', () => {
  assert.strictEqual(typeof mod.toFlatParams, 'function');
  const w = typeof window !== 'undefined' ? window : globalThis;
  assert.strictEqual(w.AIMirrorToolSchema.toFlatParams, mod.toFlatParams);
});
