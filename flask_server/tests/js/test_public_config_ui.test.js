const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const R = (f) => path.join(__dirname, '..', '..', '..', f);
const P = (f) => R('extend/dialog/parts/' + f);

global.window = { AIMirrorDialog: { methods: {} },
  parent: { postMessage: () => {} }, addEventListener: () => {} };
global.Vue = { h: (tag, props, children) => ({ tag, props, children }) };
require(P('08h_profile_fields.js'));
require(P('08g_site_profiles.js'));
require(P('08i_config_cache.js'));
require(P('08j_config_actions.js'));
require(P('08e_toolconf.js'));
const D = global.window.AIMirrorDialog;
const STORE = {};
D.configCacheGet = (k) => Promise.resolve(STORE[k] || null);
D.configCacheSet = (k, v) => { STORE[k] = v; return Promise.resolve(true); };
function clearStore() { Object.keys(STORE).forEach((k) => delete STORE[k]); }

const BACKEND = {
  flask: { host: '127.0.0.1', port: 5000, url: 'http://127.0.0.1:5000' },
  limits: { max_json_chars: 1000 },
  default_profile: 'glm',
  profiles: { glm: { label: 'GLM', hosts: ['chatglm.cn'], container: '.a' } },
  tools: { read_file: { enabled: true },
    run_command: { enabled: true, languages: ['python', 'git'] } },
  tool_config: { read_file: [{ key: 'max_bytes', value: 10 }] },
  system_config: [{ key: 'queue_max', value: 5 }],
  available_tools: ['read_file'], site_profiles: { 'chatglm.cn': 'glm' }
};
function makeCtx(over) {
  const ctx = Object.assign({
    siteKey: 'chatglm.cn', configCache: null, configBackend: null,
    configDiff: {}, configPublicDiff: {}, configOffline: false, configDirty: false,
    configDiffCount: 0, siteProfShowAll: false, siteProfConfirmOpen: false,
    siteProfiles: {}, siteProfDraft: {}, _configRemovedSites: [],
    configTools: JSON.parse(JSON.stringify(BACKEND.tools)),
    toolConfig: JSON.parse(JSON.stringify(BACKEND.tool_config)),
    systemConfig: JSON.parse(JSON.stringify(BACKEND.system_config)),
    maxJsonChars: 1000,
    config: { profile: 'glm', flaskUrl: 'http://127.0.0.1:5000', flaskPort: 5000 },
    _siteProfLoaded: false, _toasts: [],
    toast: (m) => ctx._toasts.push(String(m))
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
  c.configTools = c.configCache.tools;
  c.toolConfig = c.configCache.tool_config;
  c.systemConfig = c.configCache.system_config;
  c.maxJsonChars = c.configCache.limits.max_json_chars;
  return c;
}

test('publicIsDiff：工具开关 / 语言 / tool_config / system_config / 体积上限逐控件判差异', async () => {
  const c = await loaded();
  assert.strictEqual(c.publicIsDiff('tools', 'read_file', 'enabled', true), false);
  assert.strictEqual(c.publicIsDiff('tools', 'read_file', 'enabled', false), true);
  assert.strictEqual(c.publicIsDiff('tools', 'run_command', 'languages', ['python', 'git']), false);
  assert.strictEqual(c.publicIsDiff('tools', 'run_command', 'languages', ['python']), true);
  assert.strictEqual(c.publicIsDiff('tool_config', 'read_file', 'max_bytes', 10), false);
  assert.strictEqual(c.publicIsDiff('tool_config', 'read_file', 'max_bytes', 42), true);
  assert.strictEqual(c.publicIsDiff('system_config', '', 'queue_max', 5), false);
  assert.strictEqual(c.publicIsDiff('system_config', '', 'queue_max', 9), true);
  assert.strictEqual(c.publicIsDiff('limits', '', 'max_json_chars', 1000), false);
  assert.strictEqual(c.publicIsDiff('limits', '', 'max_json_chars', 2000), true);
  assert.strictEqual(c.publicIsDiff('nope', '', 'x', 1), false);
});

test('publicFieldClass / publicRestoreBtn：差异时挂色与还原按钮，一致时不挂', async () => {
  const c = await loaded();
  assert.strictEqual(D.publicFieldClass(c, 'tools', 'read_file', 'enabled', true), '');
  assert.strictEqual(D.publicFieldClass(c, 'tools', 'read_file', 'enabled', false), ' sp-field-diff');
  assert.strictEqual(D.publicRestoreBtn(c, 'tools', 'read_file', 'enabled', true), null);
  const btn = D.publicRestoreBtn(c, 'tools', 'read_file', 'enabled', false);
  assert.ok(btn && btn.props && btn.props.class === 'sp-restore-btn');
  assert.strictEqual(D.publicFieldClass({}, 'tools', 'read_file', 'enabled', false), '');
});

test('restorePublicItem：逐项还原只改这一个控件，不 POST，同组其它项不受影响', async () => {
  const c = await loaded();
  let posted = 0;
  D.apiFetch = () => { posted += 1; return Promise.resolve(); };
  c.configTools.read_file.enabled = false;
  c.configTools.run_command.languages = ['python'];
  await c.syncPublicToCache();
  await c.restorePublicItem('tools', 'read_file', 'enabled');
  assert.strictEqual(c.configTools.read_file.enabled, true);
  assert.strictEqual(c.publicIsDiff('tools', 'read_file', 'enabled', true), false);
  assert.deepStrictEqual(c.configTools.run_command.languages, ['python']);
  assert.strictEqual(c.publicIsDiff('tools', 'run_command', 'languages', ['python']), true);
  assert.strictEqual(posted, 0);
});

test('restorePublicItem：tool_config / system_config / limits 各走各的 state', async () => {
  const c = await loaded();
  c.toolConfig.read_file[0].value = 42;
  c.systemConfig[0].value = 9;
  c.maxJsonChars = 2000;
  await c.syncPublicToCache();
  await c.restorePublicItem('tool_config', 'read_file', 'max_bytes');
  await c.restorePublicItem('system_config', '', 'queue_max');
  await c.restorePublicItem('limits', '', 'max_json_chars');
  assert.strictEqual(c.toolConfig.read_file[0].value, 10);
  assert.strictEqual(c.systemConfig[0].value, 5);
  assert.strictEqual(c.maxJsonChars, 1000);
});

test('renderToolConfig：差异项渲染出标色 class 与还原按钮（公共配置区真的有 UI）', async () => {
  const c = await loaded();
  c.toolConfig.read_file[0].value = 42;
  const txt = JSON.stringify(D.renderToolConfig(c, 'read_file'));
  assert.ok(txt.indexOf('sp-field-diff') >= 0);
  assert.ok(txt.indexOf('sp-restore-btn') >= 0);
});

test('renderConfigBadge：一致/离线静默；仅本段差异亮警示', async () => {
  const c = await loaded();
  assert.strictEqual(D.renderConfigBadge(c, 'tools'), null);
  assert.strictEqual(D.renderConfigBadge(Object.assign({}, c, { configOffline: true }), 'tools'), null);
  c.configDiffItems = [
    { block: 'tools', section: 'tools', label: '公共配置 · 工具上下线', detail: '' }
  ];
  const badge = JSON.stringify(D.renderConfigBadge(c, 'tools'));
  assert.ok(badge.indexOf('sp-diff-badge') >= 0);
  assert.ok(badge.indexOf('未覆盖') >= 0);
});

test('折叠卡片头不再出现「与服务端一致」废话', () => {
  const files = ['extend/dialog/parts/08j_config_actions.js',
    'extend/dialog/parts/08b_settings.js', 'extend/dialog/parts/08_settings.js'];
  for (const f of files) {
    const s = fs.readFileSync(R(f), 'utf8');
    assert.strictEqual(s.indexOf('与服务端一致'), -1, f + ' 仍含该文案');
  }
});

test('顶部状态栏：一致时不渲染状态文字，仍保留功能按钮', async () => {
  const c = await loaded();
  c.configDirty = false;
  c.configOffline = false;
  const txt = JSON.stringify(D.renderConfigStatusBar(c));
  assert.ok(txt.indexOf('与服务端一致') < 0);
  assert.ok(txt.indexOf('覆盖') >= 0);
  assert.ok(txt.indexOf('显示全部站点') >= 0);
  c.configDirty = true;
  c.configDiffItems = [
    { block: 'general', section: 'general', label: '公共配置 · 体积上限', detail: '' },
    { block: 'tools', section: 'tools', label: '公共配置 · 工具上下线', detail: '' }
  ];
  const busy = JSON.stringify(D.renderConfigStatusBar(c));
  assert.ok(busy.indexOf('2 项未覆盖') >= 0);
  assert.ok(busy.indexOf('体积上限') >= 0);
});

test('连接层不进草稿：后端改端口后本地缓存跟随，覆盖不会把旧端口写回', async () => {
  clearStore();
  const c = makeCtx();
  const backend = JSON.parse(JSON.stringify(BACKEND));
  backend.flask.port = 5001;
  backend.flask.url = 'http://127.0.0.1:5001';
  await c.configLoadAndDiff(backend);
  assert.strictEqual(c.configCache.flask.port, 5001);
  assert.ok(!('flask' in c.configPublicDiff));
  const body = D.configPublicToBody(D.configPublic(c.configCache));
  assert.strictEqual(body.flask.port, 5001);
  assert.ok(!('url' in body.flask));
  assert.ok(!('default_profile' in body));
  assert.ok('url' in c.configCache.flask);   // 提交体删 url 不能污染本地缓存
});

test('设置页顶部挂全局状态栏与确认框；站点配置块不再重复挂', () => {
  const b = fs.readFileSync(R('extend/dialog/parts/08b_settings.js'), 'utf8');
  const g = fs.readFileSync(R('extend/dialog/parts/08g_site_profiles.js'), 'utf8');
  assert.ok(b.indexOf('D.renderConfigStatusBar') >= 0);
  assert.ok(b.indexOf('D.renderConfigConfirmBar') >= 0);
  assert.ok(b.indexOf('D.renderConfigBadge') >= 0);
  assert.strictEqual(g.indexOf('renderConfigStatusBar'), -1);
  assert.strictEqual(g.indexOf('renderConfigConfirmBar'), -1);
});

test('公共配置各渲染点都接上了标色与还原', () => {
  const files = ['extend/dialog/parts/08_settings.js', 'extend/dialog/parts/08e_toolconf.js',
    'extend/dialog/parts/01_backend.js'];
  for (const f of files) {
    const s = fs.readFileSync(R(f), 'utf8');
    assert.ok(s.indexOf('publicFieldClass') >= 0, f + ' 未标色');
    assert.ok(s.indexOf('publicRestoreBtn') >= 0, f + ' 未挂还原');
  }
});
