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
require(P('00a_api.js'));
const D = global.window.AIMirrorDialog;
const STORE = {};
D.configCacheGet = (k) => Promise.resolve(STORE[k] || null);
D.configCacheSet = (k, v) => { STORE[k] = v; return Promise.resolve(true); };
function clearStore() { Object.keys(STORE).forEach((k) => delete STORE[k]); }
const BACKEND = {
  flask: { host: '127.0.0.1', port: 5000, url: 'http://127.0.0.1:5000' },
  limits: { max_json_chars: 1000 }, default_profile: 'glm',
  profiles: { glm: { label: 'GLM', hosts: ['chatglm.cn'], container: '.a' } },
  tools: { read_file: { enabled: true } }, tool_config: {}, system_config: [],
  available_tools: ['read_file'], site_profiles: { 'chatglm.cn': 'glm' }
};
function makeCtx(over) {
  const ctx = Object.assign({
    siteKey: 'chatglm.cn', configCache: null, configBackend: null,
    configDiff: {}, configPublicDiff: {}, configBlockDirty: {},
    configOffline: false, configDirty: false, configDiffCount: 0,
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
function okResp(obj) { return { ok: true, status: 200, json: async () => obj }; }

test('白名单：受管配置端点命中；动作 / 扫描 / 日志端点放行', () => {
  assert.ok(D.matchConfigBlock('/api/bridge/config', 'POST', true));
  assert.ok(D.matchConfigBlock('/api/bridge/weixin/config', 'POST', true));
  assert.ok(D.matchConfigBlock('/api/bridge/wecom/config', 'POST', true));
  assert.ok(D.matchConfigBlock('/skills/foo/enabled', 'POST', true));
  assert.ok(D.matchConfigBlock('/rules', 'POST', true));
  assert.ok(D.matchConfigBlock('/rules/abc', 'DELETE', true));
  assert.ok(D.matchConfigBlock('/custom_tools/foo', 'POST', true));
  assert.strictEqual(D.matchConfigBlock('/custom_tools/scan', 'POST', true), null);
  assert.strictEqual(D.matchConfigBlock('/custom_tools/install', 'POST', true), null);
  assert.strictEqual(D.matchConfigBlock('/api/web/client_log', 'POST', true), null);
  assert.strictEqual(D.matchConfigBlock('/api/bridge/weixin/login', 'POST', true), null);
  assert.strictEqual(D.matchConfigBlock('/rules', 'GET', true), null);
  assert.ok(D.matchConfigBlock('/prompt_sections', 'GET', false));
  assert.strictEqual(D.matchConfigBlock('/api/bridge/config', 'POST', false), null);
});

test('指令端点：配置保存拦，下发命令带 action 时放行', () => {
  const b = D.matchConfigBlock('/api/bridge/commands', 'POST', true);
  assert.ok(b);
  assert.strictEqual(b.guard({ name: 'x', cmd: 'y' }), true);
  assert.strictEqual(b.guard({ action: 'run', target: 'all' }), false);
});

test('mergeIntoShape：顶层命中 / 子对象命中 / 数组安全', () => {
  assert.deepStrictEqual(D.mergeIntoShape({ qq: 1, voice: 0 }, { qq: 2 }), { qq: 2, voice: 0 });
  assert.deepStrictEqual(D.mergeIntoShape({ config: { qq: 1, voice: 0 } }, { qq: 2 }),
    { config: { qq: 2, voice: 0 } });
  const arr = [1, 2];
  assert.strictEqual(D.mergeIntoShape(arr, { a: 1 }), arr);
  assert.deepStrictEqual(D.mergeIntoShape({ ok: true }, null), { ok: true });
});

test('apiFetch：配置写不发请求并登记 pending；动作端点照常发；__commit 放行', async () => {
  clearStore();
  const calls = [];
  global.fetch = async (url, opts) => { calls.push({ url, opts }); return okResp({ ok: true }); };
  const ctx = makeCtx();
  const r = await D.apiFetch(ctx, '/api/bridge/config', { method: 'POST', body: { qq: 2 } });
  assert.strictEqual(r.draft, true);
  assert.strictEqual(calls.length, 0);
  assert.strictEqual(ctx.configCache.pending.length, 1);
  await D.apiFetch(ctx, '/api/web/client_log', { method: 'POST', body: { x: 1 } });
  assert.strictEqual(calls.length, 1);
  await D.apiFetch(ctx, '/api/bridge/config', { method: 'POST', body: { qq: 3 }, __commit: true });
  assert.strictEqual(calls.length, 2);
});

test('apiFetch 读端点：把待覆盖改动合并进响应，UI 重读不回冲', async () => {
  clearStore();
  global.fetch = async () => okResp({ config: { qq: 1, voice: 0 } });
  const ctx = makeCtx();
  await D.apiFetch(ctx, '/api/bridge/config', { method: 'POST', body: { qq: 2 } });
  const data = await D.apiFetch(ctx, '/api/bridge/config');
  assert.strictEqual(data.config.qq, 2);
  assert.strictEqual(data.config.voice, 0);
});

test('pending 按路径去重；recomputeConfigDiff 把待覆盖区块计入 dirty', async () => {
  clearStore();
  global.fetch = async () => okResp({ ok: true });
  const ctx = makeCtx();
  await ctx.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  await D.apiFetch(ctx, '/api/bridge/config', { method: 'POST', body: { qq: 2 } });
  await D.apiFetch(ctx, '/api/bridge/config', { method: 'POST', body: { qq: 3 } });
  assert.strictEqual(ctx.configCache.pending.length, 1);
  assert.strictEqual(ctx.configCache.pending[0].body.qq, 3);
  assert.strictEqual(ctx.configBlockDirty.bridge, 1);
  assert.strictEqual(ctx.configDirty, true);
  assert.ok(ctx.configDiffCount >= 1);
  // pending 是内部字段，不能被当成公共配置差异提交
  assert.ok(!('pending' in ctx.configPublicDiff));
  const body = D.configPublicToBody(D.configPublic(ctx.configCache));
  assert.ok(!('pending' in body));
});

test('applyConfigOverwrite：先回放各区块写入，再提交 /config，最后清空 pending', async () => {
  clearStore();
  const posted = [];
  global.fetch = async (url, opts) => { posted.push({ url, opts }); return okResp({ success: true }); };
  const ctx = makeCtx();
  await ctx.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  ctx.configCache.pending = [
    { seq: 2, block: 'wecom', path: '/api/bridge/wecom/config', method: 'POST', body: { bot: 'b' } },
    { seq: 1, block: 'bridge', path: '/api/bridge/config', method: 'POST', body: { qq: 2 } }
  ];
  ctx.siteProfConfirmOpen = true;
  await ctx.applyConfigOverwrite();
  assert.ok(posted.length >= 3);
  assert.ok(posted[0].url.endsWith('/api/bridge/config'));
  assert.ok(posted[1].url.endsWith('/api/bridge/wecom/config'));
  assert.ok(posted[posted.length - 1].url.endsWith('/config/commit'));
  assert.strictEqual(ctx.configCache.pending.length, 0);
  assert.strictEqual(ctx.siteProfConfirmOpen, false);
});

test('discardConfigBlock：只丢该区块，其它区块保留', async () => {
  clearStore();
  const ctx = makeCtx();
  await ctx.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  ctx.configCache.pending = [
    { seq: 1, block: 'bridge', path: '/api/bridge/config', method: 'POST', body: { qq: 2 } },
    { seq: 2, block: 'rules', path: '/rules', method: 'POST', body: { name: 'r' } }
  ];
  await ctx.discardConfigBlock('bridge');
  assert.deepStrictEqual(ctx.configCache.pending.map((w) => w.block), ['rules']);
  assert.ok(!('bridge' in ctx.configBlockDirty));
});

test('renderBlockBadge：一致静默，仅未覆盖时亮', () => {
  const ctx = makeCtx();
  assert.strictEqual(D.renderBlockBadge(ctx, 'bridge'), null);
  ctx.configBlockDirty = { bridge: 2 };
  ctx.configDiffItems = [
    { block: 'bridge', section: 'bridge', label: '远程桥接 / 投递策略 · 待覆盖写入 a', detail: '' },
    { block: 'bridge', section: 'bridge', label: '远程桥接 / 投递策略 · 待覆盖写入 b', detail: '' }
  ];
  assert.ok(JSON.stringify(D.renderBlockBadge(ctx, 'bridge')).indexOf('2') >= 0);
});

test('状态栏：一致时不报平安；有待覆盖区块时逐块列出', () => {
  const ctx = makeCtx();
  ctx.configDirty = false; ctx.configOffline = false;
  const quiet = JSON.stringify(D.renderConfigStatusBar(ctx));
  assert.ok(quiet.indexOf('与服务端' + '一致') < 0);
  assert.ok(quiet.indexOf('覆盖') >= 0);
  ctx.configDirty = true;
  ctx.configDiffItems = [
    { block: 'bridge', section: 'bridge', label: '远程桥接 / 投递策略 · 待覆盖写入', detail: '' },
    { block: 'general', section: 'general', label: '公共配置 · 体积上限', detail: '' }
  ];
  ctx.configBlockDirty = { bridge: 1, general: 1 };
  const busy = JSON.stringify(D.renderConfigStatusBar(ctx));
  assert.ok(busy.indexOf('远程桥接') >= 0);
  assert.ok(busy.indexOf('未覆盖') >= 0);
});

test('applyPendingToRead：技能上线草稿合并到 skillsManage 行，不挂顶层', () => {
  const backend = {
    sections: [], skills: [],
    skillsManage: [
      { name: 'anatomy', enabled: false, tool_count: 1, enabled_count: 0,
        tools: [{ name: 'anatomy_illustration', enabled: false }] }
    ]
  };
  const ctx = { configCache: { pending: [
    { seq: 1, block: 'skills', path: '/skills/anatomy/enabled', method: 'PUT', body: { enabled: true } }
  ] } };
  const out = D.applyPendingToRead(ctx, '/prompt_sections', backend,
    D.matchConfigBlock('/prompt_sections', 'GET', false));
  assert.strictEqual(out.skillsManage[0].enabled, true);
  assert.strictEqual(out.skillsManage[0].tools[0].enabled, true);
  assert.strictEqual(out.skillsManage[0].enabled_count, 1);
  assert.ok(!('enabled' in out));
  assert.strictEqual(backend.skillsManage[0].enabled, false);
});

test('applyPendingToRead：多个技能待覆盖写入逐条生效', () => {
  const backend = { sections: [], skills: [], skillsManage: [
    { name: 'a', enabled: false, tools: [{ name: 't_a', enabled: false }] },
    { name: 'b', enabled: false, tools: [{ name: 't_b', enabled: false }] }
  ] };
  const ctx = { configCache: { pending: [
    { seq: 1, block: 'skills', path: '/skills/a/enabled', method: 'PUT', body: { enabled: true } },
    { seq: 2, block: 'skills', path: '/skills/b/enabled', method: 'PUT', body: { enabled: true } }
  ] } };
  const out = D.applyPendingToRead(ctx, '/prompt_sections', backend,
    D.matchConfigBlock('/prompt_sections', 'GET', false));
  assert.deepStrictEqual(out.skillsManage.map((s) => s.enabled), [true, true]);
});

test('applyPendingToRead：工具上下线草稿合并到 tools 行', () => {
  const backend = { tools: [{ name: 'foo', enabled: false, description: 'x' }], scanRoots: [] };
  const ctx = { configCache: { pending: [
    { seq: 1, block: 'custom_tools', path: '/custom_tools/foo', method: 'PUT', body: { enabled: true } }
  ] } };
  const out = D.applyPendingToRead(ctx, '/custom_tools', backend,
    D.matchConfigBlock('/custom_tools', 'GET', false));
  assert.strictEqual(out.tools[0].enabled, true);
  assert.ok(!('enabled' in out));
});

test('apiFetch：技能上线草稿模式下读 /prompt_sections 保持上线态', async () => {
  clearStore();
  global.fetch = async () => okResp({
    sections: [], skills: [],
    skillsManage: [{ name: 'anatomy', enabled: false, tool_count: 1, enabled_count: 0,
      tools: [{ name: 'anatomy_illustration', enabled: false }] }]
  });
  const ctx = makeCtx();
  const r = await D.apiFetch(ctx, '/skills/anatomy/enabled', { method: 'PUT', body: { enabled: true } });
  assert.strictEqual(r.draft, true);
  const data = await D.apiFetch(ctx, '/prompt_sections');
  assert.strictEqual(data.skillsManage[0].enabled, true);
});

