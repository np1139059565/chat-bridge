
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('node:path');
const P = (f) => path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', f);
const src = (f) => fs.readFileSync(P(f), 'utf8');
global.window = { AIMirrorDialog: { methods: {} },
  parent: { postMessage: () => {} }, addEventListener: () => {} };
global.Vue = { h: (tag, props, children) => ({ tag, props, children }) };
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
require(P('08i_config_cache.js'));
require(P('08j_config_actions.js'));
require(P('08k_config_blocks.js'));
require(P('08e_toolconf.js'));
const D = global.window.AIMirrorDialog;
const STORE = {};
D.configCacheGet = (k) => Promise.resolve(STORE[k] || null);
D.configCacheSet = (k, v) => { STORE[k] = v; return Promise.resolve(true); };
function clearStore() { Object.keys(STORE).forEach((k) => delete STORE[k]); }

const BACKEND = {
  flask: { host: '127.0.0.1', port: 5000, url: 'http://127.0.0.1:5000' },
  limits: { max_json_chars: 1000 }, default_profile: 'glm',
  profiles: { glm: { label: '智谱清言 GLM', hosts: ['chatglm.cn'], container: '.x' } },
  tools: { read_file: { enabled: true } },
  tool_config: { read_file: [{ key: 'max_files', label: '上传文件最大数量', type: 'integer', value: 5 }] },
  system_config: [{ key: 'queue_max', label: '队列上限', type: 'integer', value: 5 }],
  available_tools: ['read_file'], site_profiles: { 'chatglm.cn': 'glm' }
};
function makeCtx(over) {
  const ctx = Object.assign({
    siteKey: 'chatglm.cn', configCache: null, configBackend: null,
    configDiff: {}, configPublicDiff: {}, configBlockDirty: {}, configDiffItems: [],
    configOffline: false, configDirty: false, configDiffCount: 0, siteProfShowAll: false,
    siteProfConfirmOpen: false, siteProfiles: {}, siteProfDraft: {}, _configRemovedSites: [],
    configTools: {}, toolConfig: {}, systemConfig: [], maxJsonChars: 1000,
    config: { profile: 'glm', flaskUrl: 'http://127.0.0.1:5000' },
    _siteProfLoaded: false, _toasts: [], toast: (m) => ctx._toasts.push(String(m))
  }, over || {});
  for (const n of Object.keys(D.methods)) {
    ctx[n] = function (...a) { return D.methods[n].apply(ctx, a); };
  }
  return ctx;
}
async function loaded(over) {
  clearStore();
  const c = makeCtx(over);
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  return c;
}

test('派生只读字段不进公共比对，伪差异 available_tools / site_profiles 消失', async () => {
  const c = await loaded();
  assert.ok(!('available_tools' in c.configPublicDiff));
  assert.ok(!('site_profiles' in c.configPublicDiff));
  const body = D.configPublicToBody(D.configPublic(c.configCache));
  assert.ok(!('available_tools' in body));
  assert.ok(!('site_profiles' in body));
});

test('单一明细源：顶部计数、徽标数字、弹框列表三者严格同源', async () => {
  const c = await loaded();
  c.configCache.pending = [
    { seq: 1, block: 'bridge', label: '远程桥接', path: '/api/bridge/config',
      method: 'POST', body: { a: 1 } }
  ];
  c.recomputeConfigDiff();
  assert.strictEqual(c.configDiffCount, c.configDiffItems.length);
  assert.ok(c.configDiffItems.length >= 1);
  c.configDiffItems.forEach((it) => assert.ok(it.label && it.block && it.section));
  const byBlock = {};
  c.configDiffItems.forEach((it) => { byBlock[it.block] = (byBlock[it.block] || 0) + 1; });
  assert.deepStrictEqual(c.configBlockDirty, byBlock);
});

test('确认框改浮层：sp-modal-mask 且逐项列出具体配置，不再笼统', async () => {
  const c = await loaded();
  c.configDiffItems = [
    { block: 'general', section: 'general', label: '公共配置 · 工具结果体积上限', detail: '整份提交' },
    { block: 'site_profiles', section: 'site_profiles', label: '网页 AI 站点配置 · glm.hosts', detail: '' }
  ];
  c.siteProfConfirmOpen = true;
  const s = JSON.stringify(D.renderConfigConfirmBar(c));
  assert.ok(s.indexOf('sp-modal-mask') >= 0, '未改浮层');
  assert.ok(s.indexOf('工具结果体积上限') >= 0, '未列具体公共项');
  assert.ok(s.indexOf('glm.hosts') >= 0, '未列具体站点字段');
  assert.ok(s.indexOf('2 项将被写入') >= 0, '数目未写出');
  assert.ok(s.indexOf('【网页 AI 站点配置】') >= 0);
  assert.ok(s.indexOf('确认覆盖') >= 0);
});

test('顶部状态栏压成一行：不铺开徽标，具体项放悬浮 title', async () => {
  const c = await loaded();
  c.configDiffItems = [
    { block: 'general', section: 'general', label: '公共配置 · 工具内部配置', detail: '' }
  ];
  const s = JSON.stringify(D.renderConfigStatusBar(c));
  assert.ok(s.indexOf('sp-modal-mask') < 0);
  assert.ok(s.indexOf('公共差异：') < 0, '仍铺开公共差异徽标');
  assert.ok(s.indexOf('悬浮看具体项') >= 0);
  assert.ok(s.indexOf('工具内部配置') >= 0, 'title 未含具体项');
  assert.ok(s.indexOf('查看差异 / 覆盖') >= 0);
});

test('三个徽标都带 title，悬浮能看具体字段名', async () => {
  const c = await loaded();
  c.configDiffItems = [
    { block: 'site_profiles', section: 'site_profiles', label: '网页 AI 站点配置 · glm.hosts', detail: '' },
    { block: 'tools', section: 'tools', label: '公共配置 · 工具上下线 / run_command 支持语言', detail: '' },
    { block: 'bridge', section: 'bridge', label: '远程桥接 / 投递策略 · 待覆盖写入', detail: '' }
  ];
  c.configBlockDirty = { site_profiles: 1, tools: 1, bridge: 1 };
  assert.ok(JSON.stringify(D.renderSiteProfileBadge(c)).indexOf('glm.hosts') >= 0);
  assert.ok(JSON.stringify(D.renderConfigBadge(c, 'tools')).indexOf('工具上下线') >= 0);
  assert.ok(JSON.stringify(D.renderBlockBadge(c, 'bridge')).indexOf('待覆盖写入') >= 0);
});

test('configValueToText：数组 / 对象 hosts 都不会渲染成 [object Object]', () => {
  assert.strictEqual(D.configValueToText(['chatglm.cn', 'chatglm.com']),
    'chatglm.cn' + String.fromCharCode(10) + 'chatglm.com');
  assert.strictEqual(D.configValueToText({ hosts: ['a.com'] }), 'a.com');
  assert.strictEqual(D.configValueToText({ value: 7 }), '7');
  assert.strictEqual(D.configValueToText(null), '');
  assert.strictEqual(D.configValueToText('x'), 'x');
  assert.ok(D.configValueToText({ a: 1 }).indexOf('[object Object]') < 0);
});

test('站点字段渲染走归一化：源码不再 String(val)，数组 hosts 文本化无乱码', () => {
  const g = src('08g_site_profiles.js');
  assert.strictEqual(g.indexOf('String(val)'), -1, '08g 仍直接 String(val)');
  assert.ok(g.indexOf('configValueToText') >= 0, '08g 未接归一化');
  const txt = D.configValueToText(['chatglm.cn', 'chatglm.com']);
  assert.ok(txt.indexOf('[object Object]') < 0);
});

test('08g 自包含：单独加载不依赖 08j 的 configValueToText', () => {
  const fs2 = require('fs');
  const p2 = path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '08g_site_profiles.js');
  const g = fs2.readFileSync(p2, 'utf8');
  assert.ok(g.indexOf('const toText') >= 0, '08g 未自带归一化');
  assert.ok(g.indexOf('D.configValueToText = D.configValueToText || toText') >= 0);
  assert.strictEqual(g.indexOf('D.configValueToText(val)'), -1, '渲染仍依赖外部定义');
  assert.strictEqual(g.indexOf('String(val)'), -1, '仍直接 String(val)');
});
