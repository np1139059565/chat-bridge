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
const D = global.window.AIMirrorDialog;

const STORE = {};
D.configCacheGet = (k) => Promise.resolve(STORE[k] || null);
D.configCacheSet = (k, v) => { STORE[k] = v; return Promise.resolve(true); };
function clearStore() { Object.keys(STORE).forEach((k) => delete STORE[k]); }

function makeCtx(over) {
  const ctx = Object.assign({
    siteKey: 'chatglm.cn', configCache: null, configBackend: null,
    configDiff: {}, configPublicDiff: {}, configOffline: false, configDirty: false,
    configDiffCount: 0, siteProfShowAll: false, siteProfConfirmOpen: false,
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

const BACKEND = {
  flask: { host: '127.0.0.1', port: 5000, url: 'http://127.0.0.1:5000' },
  limits: { max_json_chars: 1000 },
  default_profile: 'glm',
  profiles: { glm: { label: 'GLM', hosts: ['chatglm.cn'], container: '.a' },
    deepseek: { label: 'DS', hosts: ['deepseek.com'] } },
  tools: { read_file: { enabled: true } },
  tool_config: { read_file: [{ key: 'max_bytes', value: 10 }] },
  system_config: [{ key: 'queue_max', value: 5 }],
  available_tools: ['read_file'], site_profiles: { 'chatglm.cn': 'glm' }
};

test('currentProfileId：按 hosts 命中当前页，未登记兜底 glm', () => {
  clearStore();
  assert.strictEqual(makeCtx({ configCache: BACKEND }).currentProfileId(), 'glm');
  assert.strictEqual(makeCtx({ siteKey: 'www.deepseek.com', configCache: BACKEND }).currentProfileId(), 'deepseek');
  assert.strictEqual(makeCtx({ siteKey: 'unknown.com', configCache: BACKEND }).currentProfileId(), 'glm');
});

test('configLoadAndDiff：首载用后端初始化缓存；刷新不覆盖本地草稿', async () => {
  clearStore();
  const c = makeCtx();
  await c.configLoadAndDiff(BACKEND);
  assert.deepStrictEqual(c.configCache.profiles, BACKEND.profiles);
  assert.strictEqual(c.configDirty, false);
  c.siteProfDraft.glm.container = '.mine';
  await c.persistConfigCache();
  assert.strictEqual(c.configDirty, true);
  assert.strictEqual(c.configDiff.glm.container, '.a');
  const backend2 = JSON.parse(JSON.stringify(BACKEND));
  backend2.profiles.glm.container = '.server2';
  const c2 = makeCtx();
  await c2.configLoadAndDiff(backend2);
  assert.strictEqual(c2.siteProfDraft.glm.container, '.mine');
  assert.strictEqual(c2.configDiff.glm.container, '.server2');
});

test('首载深拷贝：persist 不污染后端快照对象', async () => {
  clearStore();
  const c = makeCtx();
  await c.configLoadAndDiff(BACKEND);
  c.siteProfDraft.glm.container = '.mine';
  await c.persistConfigCache();
  assert.strictEqual(BACKEND.profiles.glm.container, '.a');
  assert.strictEqual(c.configBackend.profiles.glm.container, '.a');
});

test('restoreProfileField：逐项用后端值擦本地，不影响同页其它项', async () => {
  clearStore();
  const c = makeCtx();
  await c.configLoadAndDiff(BACKEND);
  c.siteProfDraft.glm.container = '.mine';
  c.siteProfDraft.glm.label = 'MyGLM';
  await c.persistConfigCache();
  await c.restoreProfileField('glm', 'container');
  assert.strictEqual(c.siteProfDraft.glm.container, '.a');
  assert.strictEqual(c.siteProfDraft.glm.label, 'MyGLM');
});

test('syncPublicToCache：公共 setter 只写缓存，不 POST', async () => {
  clearStore();
  let posted = 0;
  D.apiFetch = () => { posted += 1; return Promise.resolve(); };
  const c = makeCtx();
  await c.configLoadAndDiff(BACKEND);
  c.configTools = c.configCache.tools;
  c.configTools.read_file.enabled = false;
  c.maxJsonChars = 2000;
  await c.syncPublicToCache();
  assert.strictEqual(posted, 0);
  assert.strictEqual(c.configCache.tools.read_file.enabled, false);
  assert.strictEqual(c.configCache.limits.max_json_chars, 2000);
});

test('applyConfigOverwrite：公共整份 + 只提交当前站点档案', async () => {
  clearStore();
  let posted = null;
  D.apiFetch = (c, url, opts) => { posted = opts.body; return Promise.resolve(); };
  const c = makeCtx();
  await c.configLoadAndDiff(BACKEND);
  c.siteProfDraft.glm.container = '.mine';
  c.siteProfDraft.deepseek = { label: 'DS', hosts: 'deepseek.com' };
  c.siteProfConfirmOpen = true;
  await c.applyConfigOverwrite();
  assert.deepStrictEqual(Object.keys(posted.profiles), ['glm']);
  assert.strictEqual(posted.profiles.glm.container, '.mine');
  assert.strictEqual(posted.tool_config.read_file.max_bytes, 10);
  assert.ok(!('system_config' in posted));
  assert.ok(!('available_tools' in posted));
  assert.ok(!('site_profiles' in posted));
  assert.strictEqual(c.siteProfConfirmOpen, false);
});

test('删除站点：本地缓存不复活，profiles_remove 带上 id', async () => {
  clearStore();
  let posted = null;
  D.apiFetch = (c, url, opts) => { posted = opts.body; return Promise.resolve(); };
  const c = makeCtx();
  await c.configLoadAndDiff(BACKEND);
  delete c.siteProfDraft.deepseek;
  c.siteProfConfirmOpen = true;
  await c.applyConfigOverwrite();
  assert.ok(!('deepseek' in c.configCache.profiles));
  assert.ok(posted.profiles_remove.indexOf('deepseek') >= 0);
});

test('覆盖弹窗：两栏分开列，确认/取消按钮齐全', () => {
  clearStore();
  const c = makeCtx({ siteProfConfirmOpen: true, configCache: BACKEND });
  const node = D.renderConfigConfirmBar(c);
  assert.ok(node);
  const txt = JSON.stringify(node);
  assert.ok(txt.indexOf('公共配置') >= 0);
  assert.ok(txt.indexOf('网页 AI 站点配置') >= 0);
  assert.ok(txt.indexOf('其它电脑') >= 0);
});
