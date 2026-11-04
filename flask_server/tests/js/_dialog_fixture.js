/* ============================================================
 * 抽屉脚本测试公共夹具
 *
 * 为什么独立成文件：
 *   test_dialog_boot 与 test_dialog_contracts 都需要「按 dialog.html 的
 *   真实顺序把脚本跑一遍」，原先两份文件各存一份 scriptOrder 与沙箱替身，
 *   任何一处调整都要改两遍，漏改就会让两份测试的加载环境悄悄分叉。
 *   抽到此处后，加载口径只有一份真源。
 *
 * 命名约定：
 *   文件名以 _ 开头、且不以 .test.js 结尾，因此
 *   1. 不会被 node --test 当作测试文件执行；
 *   2. 不匹配提交钩子的 *.test.js 收集规则；
 *   3. 位于 tests/js 下，覆盖率门禁按路径将其排除，不参与阈值校验。
 * ============================================================ */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// 工程内的抽屉目录：本文件位于 flask_server/tests/js，向上三级到工程根
const DIALOG_DIR = path.join(__dirname, '..', '..', '..', 'extend', 'dialog');
// 分片脚本所在子目录
const PARTS_DIR = path.join(DIALOG_DIR, 'parts');
// 页面入口：脚本加载顺序以它为准
const HTML_PATH = path.join(DIALOG_DIR, 'dialog.html');

/**
 * 从 dialog.html 里取出脚本的加载顺序。
 *
 * 不写死清单：清单一旦写死就与真实页面脱节，
 * 新增脚本而测试不知情时，测试会「假通过」。
 * @returns {string[]} 脚本相对路径，按出现顺序
 */
function scriptOrder() {
  // 读出页面源码，按 src 属性逐个提取
  const html = fs.readFileSync(HTML_PATH, 'utf-8');
  const out = [];
  // 只关心 <script src="..."> 这一种形态
  const re = /<script src="([^"]+)"/g;
  let m;
  // 逐个匹配并把捕获到的路径收集起来，顺序即加载顺序
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
    // 响应式对象：原样返回，脚本只做读写
    reactive: (o) => o || {},
    // ref：包一层 value，与真实 API 形状一致
    ref: (v) => ({ value: v }),
    // computed：用 getter 惰性求值
    computed: (fn) => ({ get value() { return fn(); } }),
    // watch：无需真实监听，空实现即可
    watch: () => {},
    // nextTick：同步执行回调，便于断言紧跟其后
    nextTick: (fn) => (fn ? fn() : Promise.resolve()),
    // createApp：链式哑对象，满足脚本挂载前的调用
    createApp: () => ({
      use() { return this; },
      mount() { return {}; },
      component() { return this; },
    }),
    // defineComponent：原样返回配置对象
    defineComponent: (o) => o,
  };
}

/**
 * 构造一个可执行抽屉脚本的最小沙箱上下文。
 *
 * 注入的全局对象只满足脚本「读取时」的调用，不实现真实行为：
 * 测试关心的是脚本能否跑完、命名空间与方法是否正确挂载。
 * @returns {Object} vm 上下文（同时充当 window）
 */
function makeSandbox() {
  // DOM 替身：覆盖脚本会调用到的创建、查询与事件注册
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
    // 定时器全部返回 0，避免测试挂住等待
    setTimeout: () => 0,
    clearTimeout: () => {},
    setInterval: () => 0,
    clearInterval: () => {},
    document: docStub,
    navigator: { userAgent: 'node-test' },
    location: { href: 'http://localhost/' },
    // 网络请求一律返回成功的空响应，脚本不会因外部依赖失败而中断
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    // 本地存储替身：读为 null，写与删为空操作
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    addEventListener() {},
    postMessage() {},
    Vue: makeVueStub(),
    // 被测代码依赖的外部小工具，给出形状正确的替身
    AIMirrorDomUtils: {
      debounce: (fn) => fn,
      hashStr: (s) => String(s).length,
      toArray: (v) => Array.prototype.slice.call(v || []),
    },
    // 扩展运行时替身：消息发送与监听均为空实现
    chrome: { runtime: { sendMessage() {}, onMessage: { addListener() {} } } },
  };
  // 脚本以 window / globalThis / self 访问全局，三者都指向沙箱本身
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  // 把普通对象升格为可执行上下文
  vm.createContext(sandbox);
  return sandbox;
}

/**
 * 在沙箱里执行一个脚本文件。
 * @param {Object} sandbox 上下文
 * @param {string} rel     相对 dialog 目录的脚本路径
 * @throws 脚本自身抛出的异常原样抛出，由调用方决定如何记录
 */
function runScript(sandbox, rel) {
  const file = path.join(DIALOG_DIR, rel);
  // 以相对路径作为文件名，报错时能直接看出是哪个脚本
  vm.runInContext(fs.readFileSync(file, 'utf-8'), sandbox, { filename: rel });
}

/**
 * 按 dialog.html 的顺序加载全部脚本，收集每个脚本的失败原因。
 *
 * 与 runScript 的区别：这里不中断，一个脚本失败后继续加载下一个，
 * 便于一次性看到全部失败项；需要精确定位「第几个文件开始崩」时用 runScript。
 * @returns {{sandbox: Object, errors: Array<{file: string, error: Error}>}}
 */
function bootDialog() {
  const sandbox = makeSandbox();
  const errors = [];
  for (const rel of scriptOrder()) {
    const file = path.join(DIALOG_DIR, rel);
    // 文件缺失单独记一类错误，与执行失败区分开
    if (!fs.existsSync(file)) {
      errors.push({ file: rel, error: new Error('脚本文件不存在') });
      continue;
    }
    try {
      runScript(sandbox, rel);
    } catch (e) {
      errors.push({ file: rel, error: e });
    }
  }
  return { sandbox, errors };
}

// 对外暴露夹具：两份测试都从这里取，加载口径只有一份真源
module.exports = {
  DIALOG_DIR,
  PARTS_DIR,
  HTML_PATH,
  scriptOrder,
  makeVueStub,
  makeSandbox,
  runScript,
  bootDialog,
};
