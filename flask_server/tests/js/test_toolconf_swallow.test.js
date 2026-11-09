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
require(P('08e_toolconf.js'));
const D = global.window.AIMirrorDialog;
const STORE = {};
D.configCacheGet = (k) => Promise.resolve(STORE[k] || null);
D.configCacheSet = (k, v) => { STORE[k] = v; return Promise.resolve(true); };
function clearStore() { Object.keys(STORE).forEach((k) => delete STORE[k]); }

const SPECS = {
  read_file: [
    { key: 'max_files', label: '上传文件最大数量', type: 'integer', value: 5, min: 1, max: 20 },
    { key: 'as_upload', label: '是否以文件上传', type: 'boolean', value: false }
  ]
};
const BACKEND = {
  flask: { host: '127.0.0.1', port: 5000, url: 'http://127.0.0.1:5000' },
  limits: { max_json_chars: 1000 }, default_profile: 'glm',
  profiles: { glm: { label: 'GLM', hosts: ['chatglm.cn'] } },
  tools: { read_file: { enabled: true } },
  tool_config: JSON.parse(JSON.stringify(SPECS)),
  system_config: [{ key: 'queue_max', label: '队列上限', type: 'integer', value: 5 }],
  available_tools: ['read_file'], site_profiles: { 'chatglm.cn': 'glm' }
};
function makeCtx(over) {
  const ctx = Object.assign({
    siteKey: 'chatglm.cn', configCache: null, configBackend: null,
    configDiff: {}, configPublicDiff: {}, configBlockDirty: {}, configOffline: false,
    configDirty: false, configDiffCount: 0, siteProfShowAll: false,
    siteProfConfirmOpen: false, siteProfiles: {}, siteProfDraft: {},
    _configRemovedSites: [], configTools: {}, toolConfig: {}, systemConfig: [],
    maxJsonChars: 1000, config: { profile: 'glm', flaskUrl: 'http://127.0.0.1:5000' },
    _siteProfLoaded: false, _toasts: [], toast: (m) => ctx._toasts.push(String(m))
  }, over || {});
  for (const n of Object.keys(D.methods)) {
    ctx[n] = function (...a) { return D.methods[n].apply(ctx, a); };
  }
  return ctx;
}

test('configPublicToBody 不再原地污染 cache.tool_config：spec 数组仍在', () => {
  const cache = JSON.parse(JSON.stringify(BACKEND));
  const before = JSON.stringify(cache.tool_config);
  D.configPublicToBody(D.configPublic(cache));
  assert.strictEqual(JSON.stringify(cache.tool_config), before);
  assert.ok(Array.isArray(cache.tool_config.read_file));
  assert.strictEqual(cache.tool_config.read_file[0].label, '上传文件最大数量');
});

test('未被污染的缓存：read_file 仍渲染出整数输入框与布尔复选框', async () => {
  clearStore();
  const c = makeCtx();
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  const txt = JSON.stringify(D.renderToolConfig(c, 'read_file'));
  assert.ok(txt.indexOf('tc-row') >= 0);
  assert.ok(txt.indexOf('上传文件最大数量') >= 0);
  assert.ok(txt.indexOf('是否以文件上传') >= 0);
  assert.ok(txt.indexOf('checkbox') >= 0);
});

test('旧缓存已被污染成扁平对象：configLoadAndDiff 自愈后输入框回来', async () => {
  clearStore();
  STORE['chatglm.cn'] = JSON.parse(JSON.stringify(BACKEND));
  STORE['chatglm.cn'].tool_config = { read_file: { max_files: 9, as_upload: true } };
  const c = makeCtx();
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  assert.ok(Array.isArray(c.toolConfig.read_file));
  assert.strictEqual(c.toolConfig.read_file[0].value, 9);
  assert.strictEqual(c.toolConfig.read_file[1].value, true);
  assert.ok(JSON.stringify(D.renderToolConfig(c, 'read_file')).indexOf('上传文件最大数量') >= 0);
});

test('renderToolConfig 对畸形输入不抛错，用服务端 spec 兜底', () => {
  const c = makeCtx({ toolConfig: { read_file: { max_files: 3 } },
    configBackend: JSON.parse(JSON.stringify(BACKEND)) });
  assert.doesNotThrow(() => D.renderToolConfig(c, 'read_file'));
  assert.ok(JSON.stringify(D.renderToolConfig(c, 'read_file')).indexOf('tc-row') >= 0);
  assert.doesNotThrow(() => D.renderSystemConfig(c));
});

test('system_config 同样自愈，资源上限输入框不被吞', async () => {
  clearStore();
  STORE['chatglm.cn'] = JSON.parse(JSON.stringify(BACKEND));
  STORE['chatglm.cn'].system_config = { queue_max: 8 };
  const c = makeCtx();
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  assert.ok(Array.isArray(c.systemConfig));
  assert.strictEqual(c.systemConfig[0].value, 8);
  assert.ok(JSON.stringify(D.renderSystemConfig(c)).indexOf('队列上限') >= 0);
});

// 端到端：真正展开 read_file 工具行，确认内部配置项没有被吞。
require(P('08_settings.js'));
const TOOL = {
  name: 'read_file', description: '读取文件',
  parameters: [{ name: 'path', type: 'string', required: true, description: '路径' }]
};
function expandedCtx(c) {
  c.expanded = { read_file: true };
  c.configTools = { read_file: { enabled: true } };
  c.usageOf = () => 'usage';
  c.toggleTool = () => {};
  c.setToolEnabled = () => {};
  return c;
}

test('renderUnifiedToolRow 展开：read_file 参数表 + 上传文件最大数量输入框 + 是否以文件上传复选框全在', async () => {
  clearStore();
  const c = expandedCtx(makeCtx());
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  const vnode = D.renderUnifiedToolRow(c, TOOL);
  const txt = JSON.stringify(vnode);
  assert.ok(txt.indexOf('上传文件最大数量') >= 0, '整数输入框被吞');
  assert.ok(txt.indexOf('是否以文件上传') >= 0, '布尔复选框被吞');
  assert.ok(txt.indexOf('checkbox') >= 0, '复选框控件丢失');
  assert.ok(txt.indexOf('params') >= 0, '参数表丢失');
  assert.ok(txt.indexOf('usage') >= 0, 'usage 丢失');
});

test('原 bug 触发路径：构造一次覆盖提交体后，read_file 展开区两个控件仍完整', async () => {
  clearStore();
  const c = expandedCtx(makeCtx());
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  // configPublicToBody 曾借浅拷贝引用原地扁平化 cache.tool_config，导致 .map 抛错、控件消失。
  const body = D.configPublicToBody(D.configPublic(c.configCache));
  assert.ok(body.tool_config && body.tool_config.read_file);
  assert.ok(Array.isArray(c.toolConfig.read_file), '缓存 spec 数组被污染成对象');
  assert.doesNotThrow(() => D.renderUnifiedToolRow(c, TOOL));
  const txt = JSON.stringify(D.renderUnifiedToolRow(c, TOOL));
  assert.ok(txt.indexOf('上传文件最大数量') >= 0);
  assert.ok(txt.indexOf('是否以文件上传') >= 0);
});

test('端到端自愈：旧缓存被污染 → configLoadAndDiff → 展开 read_file 两个控件回来', async () => {
  clearStore();
  STORE['chatglm.cn'] = JSON.parse(JSON.stringify(BACKEND));
  STORE['chatglm.cn'].tool_config = { read_file: { max_files: 12, as_upload: true } };
  const c = expandedCtx(makeCtx());
  await c.configLoadAndDiff(JSON.parse(JSON.stringify(BACKEND)));
  assert.strictEqual(c.toolConfig.read_file[0].value, 12);
  assert.strictEqual(c.toolConfig.read_file[1].value, true);
  const txt = JSON.stringify(D.renderUnifiedToolRow(c, TOOL));
  assert.ok(txt.indexOf('上传文件最大数量') >= 0);
  assert.ok(txt.indexOf('是否以文件上传') >= 0);
});
