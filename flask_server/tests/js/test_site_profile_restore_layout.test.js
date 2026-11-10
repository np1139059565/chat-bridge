// 模块：逐项还原按钮同行布局的回归测试
// 用途：锁定还原按钮与输入框处于同一行容器，且差异标色/按钮语义不回退。
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const P = (f) => path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', f);
const R = (f) => path.join(__dirname, '..', '..', '..', f);
global.window = { AIMirrorDialog: { methods: {} },
  parent: { postMessage: () => {} }, addEventListener: () => {} };
global.Vue = { h: (tag, props, children) => ({ tag, props, children }) };
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
const D = global.window.AIMirrorDialog;

function makeCtx(over) {
  const ctx = Object.assign({
    siteKey: 'yuanbao.tencent.com', siteProfiles: {}, siteProfDraft: {},
    siteProfShowAll: false, siteProfOpen: true, siteProfExpanded: { yuanbao: true },
    siteProfDeleting: {}, siteProfTesting: {}, siteProfTestResult: {},
    newSiteId: '', newSiteLabel: '', newSiteHosts: '', newField: {},
    configDiff: { yuanbao: { label: '腾讯元宝' } },
    _toasts: [], toast: (m) => ctx._toasts.push(String(m)),
    currentProfileId: () => 'yuanbao', restoreProfileField: () => {}
  }, over || {});
  for (const n of Object.keys(D.methods)) {
    ctx[n] = function (...a) { return D.methods[n].apply(ctx, a); };
  }
  return ctx;
}

/** 递归找出 class 含 name 的节点。 */
function findClass(node, name, out) {
  if (!node || typeof node !== 'object') return out;
  if (Array.isArray(node)) { node.forEach((n) => findClass(n, name, out)); return out; }
  const c = node.props && node.props.class;
  if (typeof c === 'string' && c.split(/\s+/).indexOf(name) >= 0) out.push(node);
  if (node.children) findClass(node.children, name, out);
  return out;
}

test('差异字段：还原按钮与输入框同处 sp-field-main 一行', () => {
  const c = makeCtx({ siteProfDraft: { yuanbao: {
    label: '腾讯元宝11', hosts: 'yuanbao.tencent.com' } } });
  const vnode = D.renderSiteProfilesBlock(c);
  const mains = findClass(vnode, 'sp-field-main', []);
  assert.ok(mains.length >= 1, '未生成同行容器');
  const hasPair = mains.some((m) => {
    const kids = m.children || [];
    const restore = findClass(kids, 'sp-restore-btn', []).length > 0;
    const input = findClass(kids, 'sp-input', []).length > 0;
    return restore && input;
  });
  assert.ok(hasPair, '还原按钮与 label 输入框不在同一容器');
});

test('无差异字段：同行容器只含控件，不伪造还原按钮', () => {
  const c = makeCtx({ configDiff: {}, siteProfDraft: { yuanbao: {
    label: '腾讯元宝11', hosts: 'yuanbao.tencent.com' } } });
  const txt = JSON.stringify(D.renderSiteProfilesBlock(c));
  assert.ok(txt.indexOf('sp-field-main') >= 0);
  assert.ok(txt.indexOf('sp-restore-btn') < 0, '无差异却出现还原按钮');
});

test('样式表：sp-field-main 为横向 flex，按钮不换行', () => {
  const s = fs.readFileSync(R('extend/dialog/styles/02f_site_profiles.css'), 'utf8');
  assert.ok(s.indexOf('.sp-field-main') >= 0);
  const seg = s.slice(s.indexOf('.sp-field-main'), s.indexOf('.sp-field-main') + 420);
  assert.ok(seg.indexOf('flex-direction: row') >= 0);
  assert.ok(s.indexOf('.sp-field-main > .sp-restore-btn') >= 0);
});

test('既有语义不回退：标黄 class 与差异明细仍挂在 tc-control 上', () => {
  const c = makeCtx({ siteProfDraft: { yuanbao: {
    label: '腾讯元宝11', hosts: 'yuanbao.tencent.com' } } });
  const rows = findClass(D.renderSiteProfilesBlock(c), 'sp-field-diff', []);
  assert.ok(rows.length >= 1, '差异字段未标黄');
  rows.forEach((r) => assert.ok(String(r.props.class).indexOf('tc-control') >= 0));
});

test('行数门禁：08g 不超过 450 行', () => {
  const n = fs.readFileSync(P('08g_site_profiles.js'), 'utf8').split(String.fromCharCode(10)).length;
  assert.ok(n <= 450, '08g 行数 ' + n);
});
