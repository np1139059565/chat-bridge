/* ============================================================
 * 断连恢复：一次失败即彻底重建轮询
 *
 * 背景（2026-11-07 实机）：切回前台后页面停在「未连接」，发送全部失败，
 * 只能手动刷新。旧实现里失败后走「延迟重连」，受最小重连间隔与
 * reconnectTimer 双重延迟，可能迟迟不重建；回前台还有一条「后台超 30 秒
 * 整页刷新」的分支。两者都已移除，改为一次失败即重建、且禁止整页刷新。
 *
 * 本文件用源码级断言锁住这几条约束：
 *   1. 失败分支调用 hardResetPolling，且不再调用 reconnectNow；
 *   2. hardResetPolling 五步齐全（停表 / 掐在途 / 清忙 / 重建 / 补拉）；
 *   3. 回前台走 hardResetPolling，且源码里没有 location.reload；
 *   4. 延迟重连的遗留变量与函数确已删除。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

/** 读取 web_page.js 源码。 */
function src() {
  return fs.readFileSync(path.join(__dirname, '../../web_bridge/web_page.js'), 'utf8');
}

/** 取出某个函数体（从 function 名 起，按大括号配平截取）。 */
function fnBody(code, name) {
  const start = code.indexOf('function ' + name + '(');
  assert.ok(start >= 0, '未找到函数 ' + name);
  let i = code.indexOf('{', start);
  let depth = 0;
  for (let j = i; j < code.length; j++) {
    if (code[j] === '{') depth++;
    else if (code[j] === '}') {
      depth--;
      if (depth === 0) return code.slice(i, j + 1);
    }
  }
  throw new Error('函数体未闭合：' + name);
}

test('失败分支调用 hardResetPolling，不再走延迟重连', () => {
  const body = fnBody(src(), 'onPollFail');
  assert.ok(body.includes('hardResetPolling()'), '失败后应立即重建');
  assert.ok(!body.includes('reconnectNow'), '不应再调用已删除的 reconnectNow');
});

test('hardResetPolling 五步齐全：停表 / 掐在途 / 清忙 / 重建 / 补拉', () => {
  const body = fnBody(src(), 'hardResetPolling');
  assert.ok(body.includes('stopPolling()'), '须先停表');
  assert.ok(body.includes('abortInflightPoll('), '须掐断在途请求');
  assert.ok(body.includes('pollBusy = false'), '须清在途忙标记');
  assert.ok(body.includes('startPolling()'), '须重建定时器');
  assert.ok(body.includes('fetchMessages(false)'), '须立即补拉一次');
});

test('hardResetPolling 不做整页刷新', () => {
  const body = fnBody(src(), 'hardResetPolling');
  assert.ok(!body.includes('location.reload'), '重建路径不得刷新整页');
});

test('回前台一律重建轮询，源码中不存在整页刷新', () => {
  const code = src();
  assert.ok(!code.includes('location.reload'), '整页刷新已移除，禁止回退');
  const vis = code.slice(code.indexOf("document.addEventListener('visibilitychange'"));
  assert.ok(vis.includes('hardResetPolling()'), '回前台应走彻底重建');
});

test('延迟重连的遗留定义已清理', () => {
  const code = src();
  assert.ok(!code.includes('function reconnectNow'), 'reconnectNow 应已删除');
  assert.ok(!code.includes('MIN_RECONNECT_GAP'), '最小重连间隔应已删除');
  assert.ok(!code.includes('RELOAD_AFTER_HIDDEN_MS'), '整页刷新阈值应已删除');
});
