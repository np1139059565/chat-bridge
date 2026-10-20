/* ============================================================
 * 选择器表达式解析的测试
 *
 * 被测文件：extend/lib/dom-utils.js 中的 resolveSelectorExpr。
 * 该函数需要真实的 document，本测试用最小假对象提供 querySelectorAll，
 * 并用 global.document 注入，使其在 node 环境下可运行。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测文件的绝对路径
const MOD_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js');

/**
 * 构造一个假元素：只需 nodeType 为 1（元素节点）。
 * @returns {Object} 假元素
 */
function elem() {
  return { nodeType: 1 };
}

/**
 * 重新加载被测模块，并注入一个可控的 global.document。
 * 模块把工具函数挂到 global.AIMirrorDomUtils，故每次都要清缓存重载。
 * @param {Object} doc 假 document
 * @returns {Object} global.AIMirrorDomUtils
 */
function loadWithDoc(doc) {
  global.document = doc;
  // 模块末尾把接口挂到 window（浏览器环境）而非 global：
  // 这里提供一个干净的 window 对象承接导出，并把 document 一并挂上，
  // 因为模块内部使用的是全局 document。
  global.window = { document: doc };
  // 模块可能缓存全局引用，清掉缓存确保读到新的 document
  delete require.cache[require.resolve(MOD_PATH)];
  require(MOD_PATH);
  return global.window.AIMirrorDomUtils;
}

test('空表达式：返回空列表与 empty 错误码', () => {
  const utils = loadWithDoc({ querySelectorAll: () => [] });
  // 空串、空白、null、undefined 都应识别为空
  assert.deepEqual(utils.resolveSelectorExpr('').error, 'empty');
  assert.deepEqual(utils.resolveSelectorExpr('   ').error, 'empty');
  assert.deepEqual(utils.resolveSelectorExpr(null).error, 'empty');
  assert.deepEqual(utils.resolveSelectorExpr(undefined).error, 'empty');
});

test('JS 表达式返回单个元素：规整为单元素列表', () => {
  const el = elem();
  // 表达式求值能拿到 global 上的对象
  global.__testEl = el;
  const utils = loadWithDoc({ querySelectorAll: () => [] });
  const r = utils.resolveSelectorExpr('__testEl');
  assert.strictEqual(r.error, '');
  assert.strictEqual(r.list.length, 1);
  assert.strictEqual(r.list[0], el);
});

test('JS 表达式返回数组：逐项规整并过滤非元素', () => {
  const a = elem();
  const b = elem();
  // 数组里混入文本节点与 null，应被过滤掉
  global.__testArr = [a, { nodeType: 3 }, null, b];
  const utils = loadWithDoc({ querySelectorAll: () => [] });
  const r = utils.resolveSelectorExpr('__testArr');
  assert.strictEqual(r.error, '');
  assert.strictEqual(r.list.length, 2);
});

test('JS 表达式返回空数组：报 not_found', () => {
  global.__testEmpty = [];
  const utils = loadWithDoc({ querySelectorAll: () => [] });
  const r = utils.resolveSelectorExpr('__testEmpty');
  assert.strictEqual(r.error, 'not_found');
  assert.strictEqual(r.list.length, 0);
});

test('JS 表达式返回非元素值：报 not_found', () => {
  global.__testNum = 42;
  const utils = loadWithDoc({ querySelectorAll: () => [] });
  const r = utils.resolveSelectorExpr('__testNum');
  // 数字没有 nodeType 也没有 length，规整后为空
  assert.strictEqual(r.error, 'not_found');
});

test('类数组对象：按 length 展开', () => {
  const a = elem();
  const b = elem();
  // 模拟 NodeList：有 length 与下标
  global.__testList = { length: 2, 0: a, 1: b };
  const utils = loadWithDoc({ querySelectorAll: () => [] });
  const r = utils.resolveSelectorExpr('__testList');
  assert.strictEqual(r.list.length, 2);
  assert.strictEqual(r.error, '');
});

test('非法 JS 且是合法选择器：回退到 querySelectorAll', () => {
  const found = [elem(), elem()];
  let asked = '';
  const utils = loadWithDoc({
    querySelectorAll: (s) => { asked = s; return found; },
  });
  // .a.b 不是合法 JS 表达式，但作为选择器合法
  const r = utils.resolveSelectorExpr('.a.b');
  assert.strictEqual(asked, '.a.b');
  assert.strictEqual(r.error, '');
  assert.strictEqual(r.list.length, 2);
});

test('非法 JS 且选择器也非法：报 invalid', () => {
  const utils = loadWithDoc({
    querySelectorAll: () => { throw new Error('bad selector'); },
  });
  const r = utils.resolveSelectorExpr('###');
  assert.strictEqual(r.error, 'invalid');
  assert.strictEqual(r.list.length, 0);
});

test('选择器回退返回空：列表为空，错误码为空串', () => {
  const utils = loadWithDoc({ querySelectorAll: () => [] });
  // 合法选择器但页面上没有匹配元素。
  // 注意：回退路径对空结果返回 error=''（而非 'not_found'），
  // 与表达式路径的语义不同；调用方一律以 list.length 判断是否找到，
  // 故本用例按实际行为断言，避免测试与实现脱节。
  const r = utils.resolveSelectorExpr('.not-exist');
  assert.strictEqual(r.list.length, 0);
  assert.strictEqual(r.error, '');
});

test('首尾空白会被裁剪后再处理', () => {
  let asked = '';
  const utils = loadWithDoc({
    querySelectorAll: (s) => { asked = s; return [elem()]; },
  });
  utils.resolveSelectorExpr('  .a  ');
  // 传给 querySelectorAll 的应是裁剪后的表达式
  assert.strictEqual(asked, '.a');
});
