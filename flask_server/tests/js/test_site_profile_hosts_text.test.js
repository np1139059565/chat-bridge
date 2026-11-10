// 模块：站点档案 hosts 文本归一化的回归测试
// 用途：锁定卡片头域名 chip 与序列化/草稿重置不再产生 [object Object]。
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const P = (f) => path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', f);
global.window = { AIMirrorDialog: { methods: {} },
  parent: { postMessage: () => {} }, addEventListener: () => {} };
global.Vue = { h: (tag, props, children) => ({ tag, props, children }) };
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
const D = global.window.AIMirrorDialog;
const NL = String.fromCharCode(10);

function makeCtx(over) {
  const ctx = Object.assign({
    siteKey: 'chatglm.cn', siteProfiles: {}, siteProfDraft: {},
    siteProfShowAll: false, siteProfOpen: true, siteProfExpanded: {},
    siteProfDeleting: {}, siteProfTesting: {}, siteProfTestResult: {},
    newSiteId: '', newSiteLabel: '', newSiteHosts: '', newField: {},
    configDiff: {}, _toasts: [], toast: (m) => ctx._toasts.push(String(m)),
    currentProfileId: () => 'glm'
  }, over || {});
  for (const n of Object.keys(D.methods)) {
    ctx[n] = function (...a) { return D.methods[n].apply(ctx, a); };
  }
  return ctx;
}

test('serializeProfilesDraft：数组 / 对象 hosts 都不产生 [object Object]', () => {
  const arr = D.serializeProfilesDraft({ glm: { hosts: ['chatglm.cn', 'chatglm.com'], label: 'L' } });
  assert.deepStrictEqual(arr.glm.hosts, ['chatglm.cn', 'chatglm.com']);
  const obj = D.serializeProfilesDraft({ glm: { hosts: { hosts: ['a.com'] }, label: 'L' } });
  assert.deepStrictEqual(obj.glm.hosts, ['a.com']);
  assert.ok(JSON.stringify(obj).indexOf('[object Object]') < 0);
});

test('serializeProfilesDraft：文本按行拆、空行剔除、布尔与数字口径不变', () => {
  const out = D.serializeProfilesDraft({ k: { hosts: 'a.com' + NL + NL + 'b.com' + NL, split: false, custom: 123 } });
  assert.deepStrictEqual(out.k.hosts, ['a.com', 'b.com']);
  assert.strictEqual(out.k.split, false);
  assert.strictEqual(out.k.custom, '123');
});

test('resetSiteProfDraft：对象形状 hosts 归一为文本，不固化乱码', () => {
  const c = makeCtx({ siteProfiles: { glm: { hosts: { hosts: ['a.com'] }, label: 'L' } } });
  c.resetSiteProfDraft();
  assert.strictEqual(c.siteProfDraft.glm.hosts, 'a.com');
  assert.ok(JSON.stringify(c.siteProfDraft).indexOf('[object Object]') < 0);
});

test('renderSiteProfilesBlock：数组 hosts 显示真实域名 chip，无 [object Object]', () => {
  const c = makeCtx({ siteProfDraft: { glm: {
    hosts: ['chatglm.cn', 'chatglm.com'], label: '智谱清言 GLM' } } });
  const txt = JSON.stringify(D.renderSiteProfilesBlock(c));
  assert.ok(txt.indexOf('[object Object]') < 0, txt.slice(0, 400));
  assert.ok(txt.indexOf('chatglm.cn') >= 0);
  assert.ok(txt.indexOf('chatglm.com') >= 0);
});

test('源码审计：08g 不再用 String() 直取 hosts / val', () => {
  const s = fs.readFileSync(P('08g_site_profiles.js'), 'utf8');
  assert.strictEqual(s.indexOf('String(draft.hosts'), -1);
  assert.strictEqual(s.indexOf('String(val == null'), -1);
  assert.strictEqual(s.indexOf('String(val)'), -1);
  assert.ok(s.indexOf('toText(draft.hosts') >= 0);
});

test('行数门禁：08g 不超过 450 行', () => {
  const n = fs.readFileSync(P('08g_site_profiles.js'), 'utf8').split(NL).length;
  assert.ok(n <= 450, '08g 行数 ' + n);
});
