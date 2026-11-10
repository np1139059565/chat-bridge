// 模块：工具扫描结果的前端回归测试
// 用途：验证安装后扫描列表即时收敛，渲染层只呈现可安装条目。
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const P = (f) => path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', f);
global.window = { AIMirrorDialog: { methods: {} },
  parent: { postMessage: () => {} }, addEventListener: () => {} };
global.Vue = { h: (tag, props, children) => ({ tag, props, children }) };
require(P('03_custom_tools.js'));
require(P('08_settings.js'));
const D = global.window.AIMirrorDialog;

/** 构造最小 Vue 实例替身；额外覆写在方法挂载之后再贴回，避免被覆盖。 */
function makeCtx(over) {
  const extra = over || {};
  const ctx = Object.assign({
    skillScanDir: 'skills', scanResults: [], scanOpen: true,
    customTools: [], customExpanded: {}, _toasts: [],
    toast: (m) => ctx._toasts.push(String(m)),
    loadCustomTools: async () => {},
    fetchTools: async () => {}
  }, extra);
  for (const n of Object.keys(D.methods)) {
    ctx[n] = function (...a) { return D.methods[n].apply(ctx, a); };
  }
  Object.keys(extra).forEach((k) => { ctx[k] = extra[k]; });
  return ctx;
}

/** 递归收集渲染树里所有按钮的文案，避免把说明文案误判成按钮状态。 */
function buttonTexts(node, out) {
  if (!node || typeof node !== 'object') return out;
  if (Array.isArray(node)) { node.forEach((n) => buttonTexts(n, out)); return out; }
  if (node.tag === 'button') {
    const c = node.children;
    out.push(Array.isArray(c) ? c.join('') : String(c == null ? '' : c));
  }
  if (node.children) buttonTexts(node.children, out);
  return out;
}

test('installSkill：安装后移除该工具，空掉的 skill 整条移除，其它条目保留', async () => {
  D.apiFetch = async () => ({ ok: true, installed: ['t_only'] });
  const ctx = makeCtx({ scanResults: [
    { skill_name: 'only', skill_dir: 'skills/only', tools: [{ name: 't_only', description: '仅此一个' }] },
    { skill_name: 'part', skill_dir: 'skills/part', tools: [
      { name: 't_a', description: 'A' }, { name: 't_only', description: '同名' }, { name: 't_b', description: 'B' }] },
    { skill_name: 'doconly', skill_dir: 'skills/doconly', tools: [] },
    { skill_name: 'broken', skill_dir: 'skills/broken', tools: [], error: 'bad json' }
  ] });
  await ctx.installSkill('skills/only', 't_only');
  assert.deepStrictEqual(ctx.scanResults.map((s) => s.skill_name), ['part', 'doconly', 'broken']);
  assert.deepStrictEqual(ctx.scanResults[0].tools.map((t) => t.name), ['t_a', 't_b']);
});

test('renderCustomInstallBlock：只呈现可安装工具，按钮统一为「安装」', () => {
  const ctx = makeCtx({ scanResults: [
    { skill_name: 'fresh', skill_dir: 'skills/fresh',
      tools: [{ name: 't_new', description: '新工具' }] }
  ], scanOpen: true });
  const vnode = D.renderCustomInstallBlock(ctx);
  const text = JSON.stringify(vnode);
  const btns = buttonTexts(vnode, []);
  assert.ok(text.indexOf('t_new') >= 0);
  assert.ok(btns.some((t) => t === '安装'));
  assert.ok(!btns.some((t) => t.indexOf('已安装') >= 0));
  assert.ok(text.indexOf('disabled') < 0);
});

test('renderCustomInstallBlock：旧版后端带 installed 标记时只呈现新工具', () => {
  const ctx = makeCtx({ scanResults: [
    { skill_name: 'stale', skill_dir: 'skills/stale', tools: [
      { name: 't_old', description: '旧', installed: true },
      { name: 't_new', description: '新' }
    ] }
  ], scanOpen: true });
  const vnode = D.renderCustomInstallBlock(ctx);
  const text = JSON.stringify(vnode);
  const btns = buttonTexts(vnode, []);
  assert.ok(text.indexOf('t_new') >= 0);
  assert.ok(text.indexOf('t_old') < 0);
  assert.ok(!btns.some((t) => t.indexOf('已安装') >= 0));
  assert.ok(text.indexOf('disabled') < 0);
});
