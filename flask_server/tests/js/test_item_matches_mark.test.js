/* ============================================================
 * 消息项角色标记匹配的测试
 *
 * 被测：extend/content/02_blocks.js 的 A.itemMatchesMark。
 *
 * 背景：split=false 的站点（DeepSeek、元宝）靠「标记选择器」区分消息角色，
 * 但标记落点不同——DeepSeek 在 item 的后代元素上，元宝直接写在 item 自身
 * 的 class 里。原实现只用 item.querySelector 查后代，元宝首次接入时 6 条
 * 消息全被判成用户消息。本测试锁定「自身与后代都要命中」这条不变量。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测文件：内容脚本的消息解析分片
const BLOCKS_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'content', '02_blocks.js');
// 依赖：内容脚本共享命名空间
const STATE_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'content', '00_state.js');
// 依赖：dom 工具
const DOM_UTILS_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js');

/**
 * 装载内容脚本消息解析分片，返回共享命名空间。
 * @returns {Object} window.AIMirrorContent
 */
function loadBlocks() {
  global.location = { hostname: 'example.com', href: 'https://example.com/chat/1' };
  global.window = {};
  global.document = { querySelector: () => null, querySelectorAll: () => [] };
  delete require.cache[require.resolve(DOM_UTILS_PATH)];
  require(DOM_UTILS_PATH);
  delete require.cache[require.resolve(STATE_PATH)];
  require(STATE_PATH);
  const A = global.window.AIMirrorContent;
  delete require.cache[require.resolve(BLOCKS_PATH)];
  require(BLOCKS_PATH);
  return A;
}

/**
 * 构造一个可控的假元素。
 * @param {Object} opts 选项
 * @param {boolean} opts.selfMatch 自身是否命中选择器
 * @param {boolean} opts.descMatch 后代是否命中选择器
 * @returns {Object} 假元素
 */
function fakeItem(opts) {
  return {
    // matches 模拟 CSS 选择器匹配自身
    matches: function () { return !!opts.selfMatch; },
    // querySelector 模拟查找后代
    querySelector: function () { return opts.descMatch ? { nodeType: 1 } : null; },
  };
}

test('标记在 item 自身时命中（元宝这类站点）', () => {
  const A = loadBlocks();
  const item = fakeItem({ selfMatch: true, descMatch: false });
  assert.strictEqual(A.itemMatchesMark(item, '.agent-chat__bubble--ai'), true);
});

test('标记在后代元素时命中（DeepSeek 这类站点）', () => {
  const A = loadBlocks();
  const item = fakeItem({ selfMatch: false, descMatch: true });
  assert.strictEqual(A.itemMatchesMark(item, '.ds-assistant-message-main-content'), true);
});

test('自身与后代都命中时仍返回真', () => {
  const A = loadBlocks();
  const item = fakeItem({ selfMatch: true, descMatch: true });
  assert.strictEqual(A.itemMatchesMark(item, '.x'), true);
});

test('两处都不命中时返回假（用户消息）', () => {
  const A = loadBlocks();
  const item = fakeItem({ selfMatch: false, descMatch: false });
  assert.strictEqual(A.itemMatchesMark(item, '.agent-chat__bubble--ai'), false);
});

test('选择器为空时返回假，不抛异常', () => {
  const A = loadBlocks();
  const item = fakeItem({ selfMatch: true, descMatch: true });
  assert.strictEqual(A.itemMatchesMark(item, ''), false);
  assert.strictEqual(A.itemMatchesMark(item, null), false);
});

test('元素为空时返回假，不抛异常', () => {
  const A = loadBlocks();
  assert.strictEqual(A.itemMatchesMark(null, '.x'), false);
  assert.strictEqual(A.itemMatchesMark(undefined, '.x'), false);
});

test('元素不支持 matches 时退化为只查后代，不抛异常', () => {
  const A = loadBlocks();
  const item = { querySelector: () => ({ nodeType: 1 }) };
  assert.strictEqual(A.itemMatchesMark(item, '.x'), true);
  const item2 = { querySelector: () => null };
  assert.strictEqual(A.itemMatchesMark(item2, '.x'), false);
});
