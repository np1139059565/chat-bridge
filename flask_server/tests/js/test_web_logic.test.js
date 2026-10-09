/* ============================================================
 * 前端纯逻辑测试（node 自带测试运行器）
 *
 * 背景：
 *   web_page.js 与 DOM / fetch 强耦合，无法脱离浏览器测试，前端逻辑
 *   此前没有任何回归安全网。把纯逻辑抽到 web_logic.js 后，可用 node
 *   直接断言，无需浏览器。
 *
 * 运行方式：
 *   node --test flask_server/tests/js/
 *   （或指定本文件：node --test test_web_logic.test.js）
 *
 * 覆盖：失败分类（超时 / 网络错 / 其它）、离线标记、断开容差、慢响应判定。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测模块：与浏览器共用同一份 web_logic.js
const logic = require(path.join(__dirname, '..', '..', 'web_bridge', 'web_logic.js'));

test('失败分类：AbortError 归为超时（已发出无响应）', () => {
  assert.strictEqual(logic.classifyFailKind('AbortError', ''), 'timeout(已发出,无响应)');
});

test('失败分类：TypeError 归为网络错（未发出）', () => {
  assert.strictEqual(logic.classifyFailKind('TypeError', ''), 'neterr(未发出/断连)');
});

test('失败分类：其它错误取消息前 40 字', () => {
  const msg = 'x'.repeat(100);
  const got = logic.classifyFailKind('Error', msg);
  assert.strictEqual(got.length, 40);
  assert.strictEqual(got, msg.slice(0, 40));
});

test('失败分类：无名无消息回退 unknown', () => {
  assert.strictEqual(logic.classifyFailKind('', ''), 'unknown');
});

test('离线标记：断网时带 OFFLINE', () => {
  assert.strictEqual(logic.offlineSuffix(false), ' OFFLINE');
});

test('离线标记：在线时为空', () => {
  assert.strictEqual(logic.offlineSuffix(true), '');
});

test('断开判定：未达容差不显示断开', () => {
  assert.strictEqual(logic.shouldShowDisconnected(3, 4), false);
});

test('断开判定：达到容差显示断开', () => {
  assert.strictEqual(logic.shouldShowDisconnected(4, 4), true);
  assert.strictEqual(logic.shouldShowDisconnected(5, 4), true);
});

test('慢响应：低于阈值不算慢', () => {
  assert.strictEqual(logic.isSlowPoll(999, 1000), false);
});

test('慢响应：达到阈值算慢', () => {
  assert.strictEqual(logic.isSlowPoll(1000, 1000), true);
});
