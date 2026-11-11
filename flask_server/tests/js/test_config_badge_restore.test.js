// 模块：块头徽标批量还原与还原按钮纯图标的回归测试
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
require(P('08i_config_cache.js'));
require(P('08j_config_actions.js'));
require(P('08k_config_blocks.js'));
require(P('08m_config_restore.js'));
const D = global.window.AIMirrorDialog;
const NL = String.fromCharCode(10);

const BACKEND = {
  profiles: { glm: { label: '智谱清言 GLM', hosts: ['chatglm.cn', 'chatglm.com'], split: true } },
  tools: { read_file: { enabled: true } },
  limits: { max_json_chars: 1000 },
  tool_config: {}, system_config: [], default_profile: 'glm'
};

function makeCtx() {
  const ctx = {
    configBackend: JSON.parse(JSON.stringify(BACKEND)), configOffline: false,
    configCache: {
      profiles: { glm: { label: '智谱清言 GLM111', hosts: { 0: 'chatglm.cn', 1: 'chatglm.com' }, split: true } },
      tools: { read_file: { enabled: false } },
      pending: [
        { seq: 1, block: 'bridge', path: '/api/bridge/config', method: 'POST', body: { a: 1 } },
        { seq: 2, block: 'wecom', path: '/api/wecom/config', method: 'POST', body: { b: 2 } }
      ],
      blockFields: { bridge: { app_id: { current: 'x', baseline: 'y' } } }
    },
    siteProfiles: {}, siteProfDraft: { glm: { label: '智谱清言 GLM111',
      hosts: '{"0":"chatglm.cn","1":"chatglm.com"}', split: true } },
    configTools: { read_file: { enabled: false } }, toolConfig: {}, systemConfig: [],
    maxJsonChars: 2000, config: { profile: 'glm' },
    configDiff: {}, configPublicDiff: {}, configDiffItems: [], configBlockDirty: {},
    siteProfOpen: true, siteProfExpanded: { glm: true }, siteProfShowAll: false,
    siteProfDeleting: {}, siteProfTesting: {}, siteProfTestResult: {}, newField: {},
    newSiteId: '', newSiteLabel: '', newSiteHosts: '', _configRemovedSites: [],
    currentProfileId: () => 'glm', publicIsDiff: () => true,
    restoreProfileField: () => {}, restorePublicItem: () => {},
    _toasts: [], toast: (m) => ctx._toasts.push(String(m)),
    persistConfigCache: async () => { D.methods.recomputeConfigDiff.call(ctx); }
  };
  for (const n of Object.keys(D.methods)) {
    if (n === 'persistConfigCache') continue;
    ctx[n] = function (...a) { return D.methods[n].apply(ctx, a); };
  }
  D.methods.recomputeConfigDiff.call(ctx);
  return ctx;
}

function findClass(node, name, out) {
  if (!node || typeof node !== 'object') return out;
  if (Array.isArray(node)) { node.forEach((n) => findClass(n, name, out)); return out; }
  const cl = node.props && node.props.class;
  if (typeof cl === 'string' && cl.split(/\s+/).indexOf(name) >= 0) out.push(node);
  if (node.children) findClass(node.children, name, out);
  return out;
}

test('三个块头徽标是可点击按钮，title 明示批量还原', () => {
  const c = makeCtx();
  [D.renderConfigBadge(c, 'tools'), D.renderSiteProfileBadge(c), D.renderBlockBadge(c, 'bridge')].forEach((v) => {
    assert.ok(v && v.props);
    assert.strictEqual(v.tag, 'button');
    assert.strictEqual(v.props.class, 'sp-diff-badge');
    assert.strictEqual(typeof v.props.onClick, 'function');
    assert.ok(v.props.title.indexOf('点击批量还原') >= 0);
    assert.ok(JSON.stringify(v).indexOf('未覆盖') >= 0);
  });
});

test('点击站点块徽标：批量还原全部字段，hosts 乱码归位，差异归零', async () => {
  const c = makeCtx();
  await D.restoreBlockDiff(c, 'site_profiles');
  assert.strictEqual(c.siteProfDraft.glm.label, '智谱清言 GLM');
  assert.strictEqual(c.siteProfDraft.glm.hosts, 'chatglm.cn' + NL + 'chatglm.com');
  assert.deepStrictEqual(c.configCache.profiles.glm.hosts, ['chatglm.cn', 'chatglm.com']);
  assert.ok(!c.configDiff.glm || !c.configDiff.glm.label, 'label 差异未清');
  assert.ok(c._toasts.join('').indexOf('批量还原') >= 0);
});

test('点击 bridge 徽标：只丢该块 pending，其它块保留', async () => {
  const c = makeCtx();
  await D.restoreBlockDiff(c, 'bridge');
  assert.ok(!c.configCache.pending.some((w) => w.block === 'bridge'));
  assert.ok(c.configCache.pending.some((w) => w.block === 'wecom'), '误清其它块 pending');
  assert.ok(!c.configCache.blockFields.bridge, 'bridge 输入态未清');
});

test('状态栏徽标可点击，一次还原全部区块', async () => {
  const c = makeCtx();
  const bar = D.renderConfigStatusBar(c);
  const badges = findClass(bar, 'sp-diff-badge', []);
  assert.ok(badges.length >= 1);
  assert.strictEqual(badges[0].tag, 'button');
  assert.strictEqual(typeof badges[0].props.onClick, 'function');
  await badges[0].props.onClick();
  assert.strictEqual(c.siteProfDraft.glm.hosts, 'chatglm.cn' + NL + 'chatglm.com');
  assert.strictEqual(c.configTools.read_file.enabled, true);
  assert.ok(!c.configCache.pending.length, 'pending 未全清');
});

test('还原按钮纯图标：无可见文字，仅 ↺，title 保留语义', () => {
  const c = makeCtx();
  const b = D.publicRestoreBtn(c, 'tools', 'read_file', 'enabled', false);
  assert.ok(b && b.props.title.indexOf('还原') >= 0);
  const kids = Array.isArray(b.children) ? b.children : [b.children];
  assert.strictEqual(kids.filter((k) => typeof k === 'string').length, 0, '按钮仍带可见文字');
  assert.ok(JSON.stringify(b).indexOf('sp-restore-icon') >= 0);
  assert.ok(JSON.stringify(b).indexOf('↺') >= 0);
  const gs = fs.readFileSync(P('08g_site_profiles.js'), 'utf8');
  const js = fs.readFileSync(P('08j_config_actions.js'), 'utf8');
  assert.strictEqual(gs.indexOf("' 还原'"), -1);
  assert.strictEqual(js.indexOf("' 还原'"), -1);
});

test('样式与引入：徽标 pointer、图标按钮收窄、dialog 加载 08m', () => {
  const s = fs.readFileSync(R('extend/dialog/styles/02f_site_profiles.css'), 'utf8');
  assert.ok(s.indexOf('button.sp-diff-badge') >= 0);
  assert.ok(s.indexOf('min-width: 22px') >= 0);
  const h = fs.readFileSync(R('extend/dialog/dialog.html'), 'utf8');
  assert.ok(h.indexOf('08m_config_restore.js') >= 0);
});

test('行数门禁：08g / 08j 均不超过 450 行', () => {
  ['08g_site_profiles.js', '08j_config_actions.js'].forEach((f) => {
    const n = fs.readFileSync(P(f), 'utf8').split(NL).length;
    assert.ok(n <= 450, f + ' 行数 ' + n);
  });
});
