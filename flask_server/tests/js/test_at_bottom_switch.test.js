/* ============================================================
 * 底部判定开关（atBottomCheck）的测试
 *
 * 被测：extend/content/04_observer.js 的 A.isAtBottom。
 *
 * 背景：部分站点的「滚动到底部」按钮不可靠或根本不存在，isAtBottom 恒返回
 * false，导致滚动轮次的自动执行与风控恢复被永久拦住。为此新增档案字段
 * atBottomCheck（默认开启）：关闭后 isAtBottom 直接返回 true，视为「始终
 * 在底部」，不再用底部状态限制自动执行。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测文件：内容脚本的观察器分片
const OBS_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'content', '04_observer.js');
// 依赖：内容脚本共享命名空间
const STATE_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'content', '00_state.js');
// 依赖：dom 工具
const DOM_UTILS_PATH = path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js');

/**
 * 装载观察器分片，并让 activeProfile 返回指定档案。
 * @param {Object} profile 要生效的站点档案
 * @param {Function} querySelector 假的 querySelector，用于模拟按钮是否存在
 * @returns {Object} window.AIMirrorContent
 */
function loadObserver(profile, querySelector) {
  global.location = { hostname: 'example.com', href: 'https://example.com/chat/1' };
  global.window = {};
  global.document = {
    querySelector: querySelector || (() => null),
    querySelectorAll: () => [],
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  delete require.cache[require.resolve(DOM_UTILS_PATH)];
  require(DOM_UTILS_PATH);
  delete require.cache[require.resolve(STATE_PATH)];
  require(STATE_PATH);
  const A = global.window.AIMirrorContent;
  // 覆盖档案读取，直接返回被测档案
  A.activeProfile = () => profile;
  delete require.cache[require.resolve(OBS_PATH)];
  require(OBS_PATH);
  return A;
}

test('开关缺省：按开启处理，走正常判定（按钮不存在=在底部）', () => {
  const A = loadObserver({ scrollToBottomButton: ['.btn'] }, () => null);
  assert.strictEqual(A.isAtBottom(), true);
});

test('开关缺省：按钮存在=不在底部', () => {
  const A = loadObserver({ scrollToBottomButton: ['.btn'] }, (sel) => sel === '.btn' ? {} : null);
  assert.strictEqual(A.isAtBottom(), false);
});

test('开关显式开启(true)：行为与缺省一致', () => {
  const A = loadObserver({ atBottomCheck: true, scrollToBottomButton: ['.btn'] },
    (sel) => sel === '.btn' ? {} : null);
  assert.strictEqual(A.isAtBottom(), false);
});

test('开关关闭(false)：无视按钮存在，一律视为在底部', () => {
  const A = loadObserver({ atBottomCheck: false, scrollToBottomButton: ['.btn'] },
    (sel) => sel === '.btn' ? {} : null);
  assert.strictEqual(A.isAtBottom(), true);
});

test('开关关闭(false)：未配按钮选择器时同样返回在底部', () => {
  const A = loadObserver({ atBottomCheck: false }, () => null);
  assert.strictEqual(A.isAtBottom(), true);
});

test('未配按钮且开关缺省：保守判定为不在底部（原行为不变）', () => {
  const A = loadObserver({}, () => null);
  assert.strictEqual(A.isAtBottom(), false);
});
