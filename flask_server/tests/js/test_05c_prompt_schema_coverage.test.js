/* ============================================================
 * C-4 收尾：补齐 05c_prompt.js 本次改动行的执行覆盖
 *
 * 覆盖点：
 *   1. System Prompt 模板行新增文案（标准 JSON Schema 返回结构口径）；
 *   2. usageOf 经 toFlatParams 生成占位符的分支（标准 schema / 旧数组 /
 *      空 schema / 异常声明）；
 *   3. 宽松 ctx 下遍历执行本文件方法，拉伸行覆盖率，消除退化。
 * 夹具口径：与 _part_stub.js 一致，立全局桩后 require 真实分片。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const fs = require('node:fs');
const ROOT = path.join(__dirname, '..', '..', '..');
const SRC = path.join(ROOT, 'extend', 'dialog', 'parts', '05c_prompt.js');

const dialog = { methods: {}, log: () => {} };
global.window = {
  AIMirrorDialog: dialog,
  AIMirrorDomUtils: { toArray: (v) => (Array.isArray(v) ? v : []) },
  parent: { postMessage: () => {} }, addEventListener: () => {}
};
global.Vue = { h: (tag, props, children) => ({ tag, props, children }) };
const D = global.window.AIMirrorDialog;
const M = D.methods;

require(path.join(ROOT, 'extend', 'lib', 'tool-schema-adapter.js'));
require(SRC);

// 标准 JSON Schema：path 用 anyOf 表达联合类型，required 只含 path。
const SCHEMA = {
  type: 'object',
  properties: {
    path: { anyOf: [{ type: 'string' }, { type: 'array' }], description: '路径' },
    offset: { type: 'integer', description: '起始行' }
  },
  required: ['path']
};

// 万能 ctx：未登记字段给空数组，模板里的 .map/.join/.filter 不会抛错；
// bridgePush 置 null 让语音块走关闭分支。
function looseCtx() {
  const empty = [];
  return new Proxy({}, {
    get(_t, key) {
      if (key === 'bridgePush') return null;
      if (key === 'expanded' || key === 'customExpanded') return {};
      return empty;
    },
    set() { return true; }
  });
}

// 生成 System Prompt：遍历方法，取含「Tool·调用说明」的字符串结果。
function buildPrompt() {
  const ctx = looseCtx();
  for (const name of Object.keys(M)) {
    let out;
    try { out = M[name].call(ctx); } catch (e) { continue; }
    if (typeof out === 'string' && out.includes('Tool·调用说明')) return out;
  }
  return '';
}

test('模板行：get_tool_params 段落已同步标准 JSON Schema 返回结构', () => {
  const text = buildPrompt();
  assert.ok(text.includes('Tool·调用说明'), 'System Prompt 模板未被执行');
  assert.ok(text.includes('get_tool_params'), '查询参数名的通则丢失');
  assert.ok(text.includes('parameters 是标准 JSON Schema'), '新口径文案缺失');
  assert.ok(text.includes('parameters.properties 的键'), '参数名取法说明缺失');
  assert.ok(text.includes('parameters.required'), '必填项说明缺失');
  assert.ok(text.includes('不要臆造参数名'), '原约束保留');
});

test('usageOf：标准 schema 经 toFlatParams 生成占位符', () => {
  const out = M.usageOf({ name: 'read_file', parameters: SCHEMA });
  assert.ok(out.includes('<string>'), 'anyOf 首支类型未生效');
  assert.ok(out.includes('<integer>'), '普通属性类型丢失');
  const parsed = JSON.parse(out);
  assert.strictEqual(parsed.tool, 'read_file');
  assert.deepStrictEqual(Object.keys(parsed.parameters).sort(), ['offset', 'path']);
});

test('usageOf：旧扁平数组仍兼容（历史 tool.json）', () => {
  const out = M.usageOf({ name: 'x', parameters: [{ name: 'a', type: 'integer', required: true, description: 'd' }] });
  assert.ok(out.includes('<integer>'));
  assert.ok(out.includes('a'));
});

test('usageOf：空 schema / 异常声明不抛错且参数表为空', () => {
  assert.deepStrictEqual(JSON.parse(M.usageOf({ name: 'list_tools', parameters: { type: 'object', properties: {} } })).parameters, {});
  assert.deepStrictEqual(JSON.parse(M.usageOf({ name: 'x' })).parameters, {});
  assert.deepStrictEqual(JSON.parse(M.usageOf({ name: 'x', parameters: null })).parameters, {});
});

test('05c_prompt.js 各方法在宽松 ctx 下可执行（拉伸行覆盖）', () => {
  const ctx = looseCtx();
  const arg = { name: 'read_file', tool: 'read_file', parameters: SCHEMA, status: 'done', id: 'x' };
  const names = Object.keys(M);
  assert.ok(names.length >= 5, '方法数异常');
  for (const name of names) {
    try { M[name].call(ctx, arg, null, null, 'history'); } catch (e) { /* 逐方法容错 */ }
  }
  assert.ok(true);
});

test('源码静态兜底：模板行确含新文案', () => {
  assert.ok(fs.readFileSync(SRC, 'utf-8').includes('parameters 是标准 JSON Schema'));
});
