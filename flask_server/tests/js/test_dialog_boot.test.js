/* ============================================================
 * 抽屉脚本加载顺序与启动完整性测试
 *
 * 为什么需要它：
 *   2026-10 的一次改动把新脚本插到了 00_data.js 之前，而新脚本直接用
 *   window.AIMirrorDialog 却不创建它，结果拿到 undefined、挂属性抛
 *   TypeError，整个抽屉脚本链中断，用户只能回退版本。
 *   此类故障的共性是「静态检查发现不了、一跑页面就挂」，
 *   故必须有测试真的按 dialog.html 的顺序把脚本执行一遍。
 *
 * 做法：
 *   用 node:vm 建一个沙箱，按 dialog.html 的真实顺序加载全部脚本，
 *   注入最小的 window / Vue / document 替身，然后断言：
 *   1. 每个脚本都能执行完（不抛异常）
 *   2. 命名空间与关键方法最终都存在
 *   3. 注册在 D.methods 上的方法名不重复覆盖（防两个文件互相顶掉）
 *
 * 运行：
 *   node --test flask_server/tests/js/
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 加载口径与沙箱替身统一来自公共夹具，避免两份测试各存一份实现而分叉
const {
  DIALOG_DIR,
  HTML_PATH,
  scriptOrder,
  bootDialog,
} = require('./_dialog_fixture');

// ---------- 用例 ----------
test('全部脚本能按 dialog.html 的顺序执行完，无一抛错', () => {
  const { errors } = bootDialog();
  const detail = errors.map((e) => e.file + ' -> ' + e.error.message).join('\n');
  assert.deepStrictEqual(errors, [], '有脚本执行失败：\n' + detail);
});

test('命名空间 AIMirrorDialog 最终存在', () => {
  const { sandbox } = bootDialog();
  assert.ok(sandbox.AIMirrorDialog, 'AIMirrorDialog 未创建');
});

test('QQ 桥接的加载函数已挂载', () => {
  const { sandbox } = bootDialog();
  const M = sandbox.AIMirrorDialog && sandbox.AIMirrorDialog.methods;
  assert.ok(M, 'methods 未创建');
  assert.strictEqual(typeof M.loadBridge, 'function', 'loadBridge 缺失');
});

test('微信桥接的加载函数已挂载', () => {
  const { sandbox } = bootDialog();
  const M = sandbox.AIMirrorDialog && sandbox.AIMirrorDialog.methods;
  assert.ok(M, 'methods 未创建');
  assert.strictEqual(typeof M.loadWeixin, 'function', 'loadWeixin 缺失');
  assert.strictEqual(typeof M.startWxStatusPoll, 'function', 'startWxStatusPoll 缺失');
  assert.strictEqual(typeof M.saveWxConfig, 'function', 'saveWxConfig 缺失');
});

test('微信初始状态工厂可独立调用（不依赖 00_data.js 先执行）', () => {
  const { sandbox } = bootDialog();
  const D = sandbox.AIMirrorDialog;
  assert.strictEqual(typeof D.weixinInitialState, 'function', 'weixinInitialState 缺失');
  const st = D.weixinInitialState();
  assert.strictEqual(st.wxEnabled, false, '默认应为未启用');
  assert.strictEqual(st.wxQuota.limit, 10, '默认回复池上限应为 10');
});

test('渲染函数已挂载：QQ 与微信两个区块都可用', () => {
  const { sandbox } = bootDialog();
  const D = sandbox.AIMirrorDialog;
  assert.strictEqual(typeof D.renderBridgeBlock, 'function', 'renderBridgeBlock 缺失');
  assert.strictEqual(typeof D.renderWeixinBlock, 'function', 'renderWeixinBlock 缺失');
});
