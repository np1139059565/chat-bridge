// 模块：配置块黄色图标与还原按钮图标的回归测试
// 用途：锁定图标标记、样式令牌与既有徽标/按钮文案兼容，防止改图标时丢断言。
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
require(P('08k_config_blocks.js'));
const D = global.window.AIMirrorDialog;

function makeCtx() {
  return {
    configBackend: { tools: {} }, configOffline: false,
    configBlockDirty: { bridge: 1 },
    configDiffItems: [
      { block: 'bridge', section: 'bridge', label: '远程桥接 · 待覆盖写入', detail: '' },
      { block: 'site_profiles', section: 'site_profiles', label: '网页 AI 站点配置 · glm.hosts', detail: '' },
      { block: 'tools', section: 'tools', label: '公共配置 · 工具上下线', detail: '' }
    ],
    publicIsDiff: () => true, restorePublicItem: () => {}, restoreProfileField: () => {}
  };
}

test('三个块头徽标带黄色图标标记，且保留既有文案与悬浮明细', () => {
  const c = makeCtx();
  const list = [
    D.renderBlockBadge(c, 'bridge'),
    D.renderSiteProfileBadge(c),
    D.renderConfigBadge(c, 'tools')
  ];
  list.forEach((v) => {
    assert.ok(v && v.props, '徽标未渲染');
    assert.strictEqual(v.props.class, 'sp-diff-badge');
    assert.strictEqual(v.props['data-warn-icon'], '1');
    assert.ok(v.props.title && v.props.title.length > 0);
    assert.ok(JSON.stringify(v).indexOf('未覆盖') >= 0);
  });
});

test('样式表用令牌给徽标注入黄色图标，不硬编码色值', () => {
  const css = fs.readFileSync(R('extend/dialog/styles/02f_site_profiles.css'), 'utf8');
  assert.ok(css.indexOf('[data-warn-icon]::before') >= 0);
  assert.ok(css.indexOf('var(--cb-warn)') >= 0);
  assert.ok(css.indexOf('.sp-restore-icon') >= 0);
});

test('逐项还原按钮是图标按钮，class 与文案兼容既有断言', () => {
  const c = makeCtx();
  const btn = D.publicRestoreBtn(c, 'tools', 'read_file', 'enabled', false);
  assert.ok(btn && btn.props);
  assert.strictEqual(btn.props.class, 'sp-restore-btn');
  assert.ok(btn.props.title.indexOf('还原') >= 0);
  const txt = JSON.stringify(btn);
  assert.ok(txt.indexOf('sp-restore-icon') >= 0);
  assert.ok(txt.indexOf('还原') >= 0);
  const g = fs.readFileSync(P('08g_site_profiles.js'), 'utf8');
  assert.ok(g.indexOf('sp-restore-icon') >= 0);
});

test('行数门禁：08j / 08g 均不超过 450 行', () => {
  ['08j_config_actions.js', '08g_site_profiles.js'].forEach((f) => {
    const n = fs.readFileSync(P(f), 'utf8').split(String.fromCharCode(10)).length;
    assert.ok(n <= 450, f + ' 行数 ' + n);
  });
});
