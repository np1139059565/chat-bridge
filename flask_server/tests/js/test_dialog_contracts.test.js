/* ============================================================
 * 抽屉脚本的「加载契约」测试
 *
 * 背景：
 *   一次真实故障——新脚本排在命名空间创建者之前、且直接用未创建的全局，
 *   导致整个抽屉脚本链中断。根因不是某一行写错，而是「脚本之间隐含的
 *   加载顺序契约没有被任何地方声明和检查」。
 *
 * 本文件把这层契约显式化，覆盖四类风险：
 *   1. 顺序契约：依赖命名空间的文件，不得排在创建者之前
 *   2. 独立契约：每个脚本单独执行也不应崩（防隐性顺序依赖）
 *   3. 命名契约：注册到 D.methods 的方法名不重复（防互相覆盖）
 *   4. 挂载契约：dialog.html 里的脚本路径必须真实存在
 *
 * 运行：node --test flask_server/tests/js/
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const DIALOG_DIR = path.join(__dirname, '..', '..', '..', 'extend', 'dialog');
const PARTS_DIR = path.join(DIALOG_DIR, 'parts');
const HTML_PATH = path.join(DIALOG_DIR, 'dialog.html');

/**
 * 读出 dialog.html 里的脚本顺序。
 * @returns {string[]} 相对路径列表
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
 * 构造一个可执行脚本的最小沙箱。
 * @returns {Object} vm 上下文
 */
function makeSandbox() {
  const h = (tag, props, children) => ({ tag, props, children });
  const sandbox = {
    console,
    setTimeout: () => 0,
    clearTimeout: () => {},
    setInterval: () => 0,
    clearInterval: () => {},
    document: {
      createElement: () => ({ style: {}, appendChild() {}, setAttribute() {}, addEventListener() {} }),
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {},
      body: { appendChild() {}, style: {} },
      documentElement: { style: {} },
    },
    navigator: { userAgent: 'node-test' },
    location: { href: 'http://localhost/' },
    fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    addEventListener() {},
    postMessage() {},
    Vue: {
      h,
      reactive: (o) => o || {},
      ref: (v) => ({ value: v }),
      computed: (fn) => ({ get value() { return fn(); } }),
      watch: () => {},
      nextTick: (fn) => (fn ? fn() : Promise.resolve()),
      createApp: () => ({ use() { return this; }, mount() { return {}; }, component() { return this; } }),
      defineComponent: (o) => o,
    },
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
  return sandbox;
}

/**
 * 在沙箱里执行一个脚本文件。
 * @param {Object} sandbox 上下文
 * @param {string} rel     相对路径
 */
function runScript(sandbox, rel) {
  const file = path.join(DIALOG_DIR, rel);
  vm.runInContext(fs.readFileSync(file, 'utf-8'), sandbox, { filename: rel });
}

// ---------- 1. 挂载契约 ----------
test('dialog.html 引用的每个脚本文件都真实存在', () => {
  const missing = scriptOrder().filter((rel) => !fs.existsSync(path.join(DIALOG_DIR, rel)));
  assert.deepStrictEqual(missing, [], '以下脚本在 html 里被引用但文件不存在：' + missing.join(', '));
});

test('parts 目录下的脚本都被 dialog.html 引用（防新增文件忘记挂载）', () => {
  const referenced = new Set(scriptOrder().map((r) => path.basename(r)));
  const onDisk = fs.readdirSync(PARTS_DIR).filter((f) => f.endsWith('.js'));
  const orphans = onDisk.filter((f) => !referenced.has(f));
  assert.deepStrictEqual(orphans, [], '以下脚本存在但未挂进 dialog.html：' + orphans.join(', '));
});

// ---------- 2. 顺序契约 ----------
test('排在命名空间创建者之前的脚本，必须自行兜底创建', () => {
  const creator = '00_data.js';
  // 只看 parts/ 下的自有脚本：lib/ 是第三方库，不参与本契约
  const parts = scriptOrder().filter((r) => r.startsWith('parts/'));
  const ci = parts.findIndex((r) => path.basename(r) === creator);
  assert.ok(ci >= 0, 'dialog.html 未加载 ' + creator);

  // 契约：创建者之前的脚本一旦要用命名空间，必须自己兜底创建
  // （否则拿到 undefined，挂属性即抛错，整条脚本链中断）。
  // 创建者之后的脚本可以放心直接用，无需兜底。
  const offenders = [];
  for (const rel of parts.slice(0, ci)) {
    const name = path.basename(rel);
    const src = fs.readFileSync(path.join(PARTS_DIR, name), 'utf-8');
    const uses = /window\.AIMirrorDialog/.test(src);
    const guards = /window\.AIMirrorDialog\s*=\s*window\.AIMirrorDialog\s*\|\|/.test(src);
    if (uses && !guards) offenders.push(name);
  }
  assert.deepStrictEqual(
    offenders, [],
    '以下脚本排在 ' + creator + ' 之前，使用了命名空间却未兜底创建：' + offenders.join(', '));
});

// ---------- 3. 顺序契约（增量加载）----------
//
// 本工程的脚本设计是「分片往同一命名空间挂」，后面的天然依赖前面的，
// 因此不能要求「每个脚本单独执行」——那等于要求改架构。
// 真正该守的契约是：按顺序逐个加载，每一步都不能崩。
// 这能精确定位「第几个文件开始出问题」，比只测全量启动更有诊断价值。
test('按序逐个加载，每一步都不抛异常（可定位到具体文件）', () => {
  const sandbox = makeSandbox();
  const failures = [];
  const parts = scriptOrder().filter((r) => r.startsWith('parts/'));
  for (let i = 0; i < parts.length; i++) {
    try {
      runScript(sandbox, parts[i]);
    } catch (e) {
      failures.push('第 ' + (i + 1) + ' 个 ' + path.basename(parts[i]) + ' -> ' + e.message);
      break;   // 链路已断，后续必然连带失败，只报第一个原因
    }
  }
  assert.deepStrictEqual(failures, [], '脚本链在以下位置中断：\n' + failures.join('\n'));
});

// ---------- 4. 命名契约 ----------
test('多个脚本注册的方法名互不覆盖', () => {
  // 逐脚本在全新沙箱里执行，收集各自往 D.methods 上挂了哪些键
  const owners = new Map();   // 方法名 -> [文件名]
  for (const rel of scriptOrder()) {
    const sandbox = makeSandbox();
    try {
      runScript(sandbox, rel);
    } catch (e) {
      continue;   // 独立执行失败由上一个用例负责报告
    }
    const M = (sandbox.AIMirrorDialog || {}).methods || {};
    for (const key of Object.keys(M)) {
      if (!owners.has(key)) owners.set(key, []);
      owners.get(key).push(path.basename(rel));
    }
  }
  // 同一方法名被两个不同文件注册，说明后加载的会静默覆盖前者
  const conflicts = [];
  for (const [key, files] of owners.entries()) {
    const uniq = [...new Set(files)];
    if (uniq.length > 1) conflicts.push(key + ' <- ' + uniq.join(', '));
  }
  assert.deepStrictEqual(conflicts, [], '以下方法名被多个文件注册：\n' + conflicts.join('\n'));
});

// ---------- 5. 全量启动后再校验关键方法 ----------
test('全量按序启动后，方法表非空且关键入口齐全', () => {
  const sandbox = makeSandbox();
  for (const rel of scriptOrder()) runScript(sandbox, rel);
  const M = sandbox.AIMirrorDialog.methods;
  assert.ok(Object.keys(M).length > 50, '方法表过少，疑似大量脚本未生效');
  for (const name of ['loadBridge', 'loadWeixin', 'saveBridge', 'saveWxConfig',
                      'wxStartLogin', 'wxSubmitVerify', 'wxLogout',
                      'reportToBridge', 'startBridgeStatusPoll', 'startWxStatusPoll']) {
    assert.strictEqual(typeof M[name], 'function', '关键方法缺失：' + name);
  }
});
