/* ============================================================
 * 轮询看门狗测试（node 自带测试运行器）
 *
 * 背景：
 *   实际发生过「发送失败后页面一直显示未连接、只能刷新恢复」。
 *   原因是轮询停掉后，能把它重新拉起的只有「失败后立即重连」与
 *   「页面切回前台」两条路径，任一路径失效就永久卡死。
 *   看门狗不依赖任何事件，定时自检并在异常时强制复活，
 *   本文件验证它确实能识别三种卡死形态、且不误伤正常状态。
 *
 * 运行方式：
 *   node --test flask_server/tests/js/
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 被测模块：与浏览器共用同一份 web_watchdog.js
const wd = require(path.join(__dirname, '..', '..', 'web_bridge', 'web_watchdog.js'));

/**
 * 构造一份可控的钩子与调用记录。
 *
 * @param {Object} state 初始状态：{ pollOn, busy, lastPollOkAt }
 * @returns {Object} { hooks, calls, setState }
 */
function makeHooks(state) {
  const calls = { revive: 0 };
  const cur = Object.assign({ pollOn: true, busy: false, lastPollOkAt: Date.now() }, state);
  const hooks = {
    state: function () { return cur; },
    revive: function () { calls.revive += 1; }
  };
  return {
    hooks: hooks,
    calls: calls,
    setState: function (patch) { Object.assign(cur, patch); }
  };
}

test('正常状态不复活：定时器在、在途空闲、刚成功过', () => {
  const h = makeHooks({ pollOn: true, busy: false, lastPollOkAt: Date.now() });
  wd.init(h.hooks);
  wd.check();
  assert.strictEqual(h.calls.revive, 0);
});

test('定时器丢失即复活：轮询停了没有任何自愈入口', () => {
  const h = makeHooks({ pollOn: false, busy: false, lastPollOkAt: Date.now() });
  wd.init(h.hooks);
  wd.check();
  assert.strictEqual(h.calls.revive, 1);
});

test('久未成功即复活：网络恢复后应自动重连', () => {
  // 距上次成功超过 30 秒阈值
  const h = makeHooks({ pollOn: true, busy: false, lastPollOkAt: Date.now() - 31000 });
  wd.init(h.hooks);
  wd.check();
  assert.strictEqual(h.calls.revive, 1);
});

test('在途标记泄漏即复活：收尾没执行到会挡住后续全部轮询', () => {
  const h = makeHooks({ pollOn: true, busy: true, lastPollOkAt: Date.now() });
  wd.init(h.hooks);
  // 第一次自检只记下「变为忙」的时刻，不立刻复活
  wd.check();
  assert.strictEqual(h.calls.revive, 0);
  // 超过 20 秒仍为忙，判定泄漏
  const realNow = Date.now;
  Date.now = () => realNow() + 21000;
  try {
    wd.check();
  } finally {
    Date.now = realNow;
  }
  assert.strictEqual(h.calls.revive, 1);
});

test('在途短暂为忙不复活：正常请求耗时不该被误判', () => {
  const h = makeHooks({ pollOn: true, busy: true, lastPollOkAt: Date.now() });
  wd.init(h.hooks);
  wd.check();
  wd.check();   // 仍在 20 秒阈值内
  assert.strictEqual(h.calls.revive, 0);
});

test('复活后有防抖：同一周期内不重复触发', () => {
  const h = makeHooks({ pollOn: false, busy: false, lastPollOkAt: Date.now() });
  wd.init(h.hooks);
  wd.check();
  wd.check();
  assert.strictEqual(h.calls.revive, 1);
});

test('从未成功过不按「久未成功」判定：首次加载阶段不该被判卡死', () => {
  // lastPollOkAt 为 0 表示本次会话还没成功过，交给「定时器丢失」判断
  const h = makeHooks({ pollOn: true, busy: false, lastPollOkAt: 0 });
  wd.init(h.hooks);
  wd.check();
  assert.strictEqual(h.calls.revive, 0);
});

test('复活抛异常不穿透：下一个周期会再试', () => {
  const state = { pollOn: false, busy: false, lastPollOkAt: Date.now() };
  wd.init({
    state: function () { return state; },
    revive: function () { throw new Error('复活失败'); }
  });
  assert.doesNotThrow(() => wd.check());
});

test('未注入钩子时安全返回', () => {
  wd.init(null);
  assert.doesNotThrow(() => wd.check());
});

test('start 与 stop 可重复调用不抛异常', () => {
  const h = makeHooks({});
  wd.init(h.hooks);
  assert.doesNotThrow(() => {
    wd.start();
    wd.start();   // 重复启动会先停旧的，不叠加
    wd.stop();
    wd.stop();
  });
});
