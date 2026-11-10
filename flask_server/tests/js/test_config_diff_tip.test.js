// 模块：配置差异悬浮明细的回归测试
// 用途：锁定「键=母本值」格式与既有徽标文案兼容，避免改徽标时丢字段。
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const P = (f) => path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', f);
global.window = { AIMirrorDialog: { methods: {} },
  parent: { postMessage: () => {} }, addEventListener: () => {} };
global.Vue = { h: (tag, props, children) => ({ tag, props, children }) };
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
require(P('08i_config_cache.js'));
require(P('08j_config_actions.js'));
require(P('08k_config_blocks.js'));
const D = global.window.AIMirrorDialog;
const STORE = {};
D.configCacheGet = (k) => Promise.resolve(STORE[k] || null);
D.configCacheSet = (k, v) => { STORE[k] = v; return Promise.resolve(true); };

const BACKEND = {
  flask: { host: '127.0.0.1', port: 5000, url: 'http://127.0.0.1:5000' },
  limits: { max_json_chars: 1000 }, default_profile: 'glm',
  profiles: { yuanbao: { label: '腾讯元宝', hosts: ['yuanbao.tencent.com'], container: '.a' } },
  tools: { read_file: { enabled: true } }, tool_config: {}, system_config: [],
  available_tools: ['read_file'], site_profiles: { 'yuanbao.tencent.com': 'yuanbao' }
};

function makeCtx(over) {
  const ctx = Object.assign({
    siteKey: 'yuanbao.tencent.com', configCache: null, configBackend: null,
    configDiff: {}, configPublicDiff: {}, configBlockDirty: {}, configOffline: false,
    configDirty: false, configDiffCount: 0, configDiffItems: [],
    siteProfShowAll: false, siteProfConfirmOpen: false,
    siteProfiles: {}, siteProfDraft: {}, _configRemovedSites: [],
    configTools: {}, toolConfig: {}, systemConfig: [], maxJsonChars: 1000,
    config: { profile: 'glm', flaskUrl: 'http://127.0.0.1:5000', flaskPort: 5000 },
    _siteProfLoaded: false, _toasts: [],
    toast: (m) => ctx._toasts.push(String(m))
  }, over || {});
  for (const n of Object.keys(D.methods)) {
    ctx[n] = function (...a) { return D.methods[n].apply(ctx, a); };
  }
  return ctx;
}

function clearStore() { Object.keys(STORE).forEach((k) => delete STORE[k]); }

test('diffTipLine：有母本值输出「键=母本值」，无母本值保留标签', () => {
  assert.strictEqual(D.diffTipLine({ key: 'yuanbao.label', backend: '腾讯元宝', label: 'x' }),
    'yuanbao.label=腾讯元宝');
  assert.strictEqual(D.diffTipLine({ key: 'x', backend: '', label: '待覆盖写入' }), '待覆盖写入');
});

test('站点字段差异：明细携带母本值，站点徽标悬浮显示键=母本值', async () => {
  clearStore();
  const c = makeCtx();
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  c.siteProfDraft.yuanbao.label = '疼疼疼';
  await c.persistConfigCache();
  const it = (c.configDiffItems || []).find((x) => x.key === 'yuanbao.label');
  assert.ok(it, '未生成 yuanbao.label 明细');
  assert.strictEqual(it.backend, '腾讯元宝');
  assert.strictEqual(D.diffTipLine(it), 'yuanbao.label=腾讯元宝');
  const badge = JSON.stringify(D.renderSiteProfileBadge(c));
  assert.ok(badge.indexOf('yuanbao.label=腾讯元宝') >= 0, badge);
});

test('公共配置差异：明细携带母本值，公共徽标悬浮显示键=母本值', async () => {
  clearStore();
  const c = makeCtx();
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  c.configTools = { read_file: { enabled: false } };
  await c.syncPublicToCache();
  const it = (c.configDiffItems || []).find((x) => x.key === 'tools');
  assert.ok(it, '未生成 tools 明细');
  assert.ok(it.backend.length > 0);
  const badge = JSON.stringify(D.renderConfigBadge(c, 'tools'));
  assert.ok(badge.indexOf('tools=') >= 0, badge);
  assert.ok(badge.indexOf('未覆盖') >= 0);
});

test('待覆盖写入无母本值：悬浮保留原标签，既有徽标文案不丢', async () => {
  clearStore();
  const c = makeCtx();
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  c.configCache.pending = [
    { seq: 1, block: 'bridge', path: '/api/bridge/config', method: 'POST', body: { qq: 2 } }
  ];
  c.recomputeConfigDiff();
  const badge = JSON.stringify(D.renderBlockBadge(c, 'bridge'));
  assert.ok(badge.indexOf('待覆盖写入') >= 0, badge);
  const bar = JSON.stringify(D.renderConfigStatusBar(c));
  assert.ok(bar.indexOf('悬浮看具体项') >= 0, bar);
});
