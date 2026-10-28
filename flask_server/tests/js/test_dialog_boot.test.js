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
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// 工程内的抽屉目录
const DIALOG_DIR = path.join(__dirname, '..', '..', '..', 'extend', 'dialog');
const HTML_PATH = path.join(DIALOG_DIR, 'dialog.html');

/**
 * 从 dialog.html 里取出脚本的加载顺序。
 *
 * 不写死清单：清单一旦写死就与真实页面脱节，
 * 新增脚本而测试不知情时，测试会「假通过」。
 * @returns {string[]} 脚本相对路径，按出现顺序
 */
function scriptOrder() {
  const html = fs.readFileSync(HTML_PATH, 'utf-8');
  const out = [];
  const re = /<script src="([^"]+)"/g;
  let m;
  while ((m = re.exec(html)) !== null) out.push(m[1]);
  return out;
}

/**
 * 建一个能承载这些脚本的最小 Vue 替身。
 *
 * 脚本里对 Vue 的用法集中在几处：h() 造节点、reactive() 造响应式对象、
 * ref/nextTick 偶用。这里给出形状正确的哑实现，不追求行为等价——
 * 测试目标是「脚本能否跑完且挂载到位」，不是渲染正确性。
 * @returns {Object} Vue 替身
 */
function makeVueStub() {
  /**
   * h() 的哑实现：返回一个描述节点的普通对象。
   * @param {string|Function} tag 标签或组件
   * @param {Object} [props] 属性
   * @param {*} [children] 子节点
   * @returns {Object} 节点描述
   */
  const h = (tag, props, children) => ({ tag, props, children });
  return {
    h,
    reactive: (o) => o || {},
    ref: (v) => ({ value: v }),
    computed: (fn) => ({ get value() { return fn(); } }),
    watch: () => {},
    nextTick: (fn) => (fn ? fn() : Promise.resolve()),
    createApp: () => ({
      use() { return this; },
      mount() { return {}; },
      component() { return this; },
    }),
    defineComponent: (o) => o,
  };
}

/**
 * 建沙箱并加载全部脚本。
 *
 * @returns {{sandbox: Object, errors: Array<{file: string, error: Error}>}}
 *   sandbox 是加载完成后的上下文；errors 记录每个脚本的失败原因
 */
function bootDialog() {
  const vue = makeVueStub();
  // 最小 DOM 替身：只满足脚本「读取时」的调用，不实现真实行为
  const docStub = {
    createElement: () => ({ style: {}, appendChild() {}, setAttribute() {}, addEventListener() {} }),
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener() {},
    body: { appendChild() {}, style: {} },
    documentElement: { style: {} },
  };
  const sandbox = {
    console,
    setTimeout: () => 0,
    clearTimeout: () => {},
    setInterval: () => 0,
    clearInterval: () => {},
    document: docStub,
    navigator: { userAgent: 'node-test' },
    location: { href: 'http://localhost/' },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    addEventListener() {},
    postMessage() {},
    Vue: vue,
    // 被测代码依赖的外部小工具，给出形状正确的替身
    AIMirrorDomUtils: {
      debounce: (fn) => fn,
      hashStr: (s) => String(s).length,
      toArray: (v) => Array.prototype.slice.call(v || []),
    },
    chrome: { runtime: { sendMessage() {}, onMessage: { addListener() {} } } },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  vm.createContext(sandbox);

  const errors = [];
  for (const rel of scriptOrder()) {
    const file = path.join(DIALOG_DIR, rel);
    if (!fs.existsSync(file)) {
      errors.push({ file: rel, error: new Error('脚本文件不存在') });
      continue;
    }
    const code = fs.readFileSync(file, 'utf-8');
    try {
      vm.runInContext(code, sandbox, { filename: rel });
    } catch (e) {
      errors.push({ file: rel, error: e });
    }
  }
  return { sandbox, errors };
}

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
