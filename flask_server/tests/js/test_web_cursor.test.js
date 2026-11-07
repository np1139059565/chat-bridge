/* ============================================================
 * 游标持久化与缺口补齐测试
 *
 * 背景：手机端切后台超过 30 秒，回前台整页重载，内存游标归零；
 * 首屏只取最新 10 条，后台期间积压的中间段被永久跳过。
 * 本文件验证 web_cursor.js 的三件事：
 *   1. 游标能存能取，存储异常时安全降级；
 *   2. 缺口判定（存过进度且服务端更靠后）；
 *   3. 补齐按批推进、逐批持久化，中途失败不把游标提前推到最新。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('path');

/**
 * 在隔离的全局环境里加载 web_cursor.js，返回 window.WebCursor。
 *
 * 模块是 IIFE，直接读 window；故用 vm 沙箱造一个可控的 window，
 * 并注入可替换的 localStorage，用来模拟禁用与写失败。
 * @param {Object} [storage] 自定义 localStorage 实现
 * @returns {Object} window.WebCursor
 */
function loadCursor(storage) {
  const vm = require('vm');
  const fs = require('fs');
  const src = fs.readFileSync(path.join(__dirname, '../../web_bridge/web_cursor.js'), 'utf8');
  const win = {};
  const sandbox = {
    window: win,
    localStorage: storage || {
      _d: {},
      getItem(k) { return this._d[k] === undefined ? null : this._d[k]; },
      setItem(k, v) { this._d[k] = String(v); },
    },
    parseInt,
    String,
    isNaN,
    Promise,
    console,
  };
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox);
  return win.WebCursor;
}

/** 造一个会记录调用的假依赖。 */
function fakeDeps(batches) {
  const calls = [];
  return {
    calls,
    fetchSince(cur, limit) {
      calls.push(cur);
      return Promise.resolve(batches.shift() || { success: true, seq: cur, messages: [] });
    },
    renderBatch(msgs) { calls.push('render:' + msgs.length); },
    log() {},
  };
}

test('游标读写：存进去能原样读出来', () => {
  const C = loadCursor();
  C.saveCursor(1234);
  assert.strictEqual(C.loadCursor(), 1234);
});

test('游标读写：无记录时返回 0', () => {
  const C = loadCursor();
  assert.strictEqual(C.loadCursor(), 0);
});

test('游标读写：存储里是脏数据时返回 0，不抛异常', () => {
  const C = loadCursor({ getItem: () => 'abc', setItem: () => {} });
  assert.strictEqual(C.loadCursor(), 0);
});

test('游标读写：存储被禁用（抛异常）时安全降级为 0', () => {
  const C = loadCursor({ getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } });
  assert.strictEqual(C.loadCursor(), 0);
  assert.doesNotThrow(() => C.saveCursor(9));
});

test('缺口判定：存过进度且服务端更靠后 → 需要补齐', () => {
  const C = loadCursor();
  assert.strictEqual(C.needsCatchUp(100, 120), true);
});

test('缺口判定：从未拉取过（0）不算缺口', () => {
  const C = loadCursor();
  assert.strictEqual(C.needsCatchUp(0, 120), false);
});

test('缺口判定：已追平（相等）不需要补齐', () => {
  const C = loadCursor();
  assert.strictEqual(C.needsCatchUp(120, 120), false);
});

test('缺口判定：入参非法时返回 false，不抛异常', () => {
  const C = loadCursor();
  assert.strictEqual(C.needsCatchUp('x', 10), false);
});

test('首屏无缺口时不启动补齐', async () => {
  const C = loadCursor();
  const deps = fakeDeps([]);
  C.init(deps);
  C.saveCursor(50);
  C.init(deps);
  C.onPollOk(50, true);
  assert.deepStrictEqual(deps.calls, [], '游标已追平，不应发起补齐请求');
});

test('首屏有缺口时从旧游标逐批补齐，直到追平', async () => {
  const C = loadCursor();
  // 旧游标 10，服务端最新 35；两批数据：11-30、31-35
  C.saveCursor(10);
  const deps = fakeDeps([
    { success: true, seq: 30, messages: new Array(20).fill({}) },
    { success: true, seq: 35, messages: new Array(5).fill({}) },
    // 第三批：确认已追平（返回空），补齐据此收手
    { success: true, seq: 35, messages: [] },
  ]);
  C.init(deps);
  C.onPollOk(35, true);
  // 等三轮微任务跑完
  await new Promise((r) => setTimeout(r, 10));
  // 多出的末尾一次 fetchSince(35) 是「确认追平」的探测，属预期行为
  assert.deepStrictEqual(deps.calls, [10, 'render:20', 30, 'render:5', 35]);
  assert.strictEqual(C.loadCursor(), 35, '补齐完成后游标应推进到最新');
});

test('补齐中途失败时游标停在已推进的位置，不跳到最新', async () => {
  const C = loadCursor();
  C.saveCursor(10);
  const deps = {
    calls: [],
    n: 0,
    fetchSince(cur) {
      this.calls.push(cur);
      this.n += 1;
      if (this.n === 1) return Promise.resolve({ success: true, seq: 30, messages: [{}] });
      return Promise.reject(new Error('network'));
    },
    renderBatch() {},
    log() {},
  };
  C.init(deps);
  C.onPollOk(99, true);
  await new Promise((r) => setTimeout(r, 10));
  // 第一批成功推进到 30；第二批失败，游标应停在 30 而非 99
  assert.strictEqual(C.loadCursor(), 30);
});
