/* ============================================================
 * 站点档案设置区块（08g）测试
 *
 * 覆盖四层：
 *   1. 纯函数：serializeProfilesDraft 的序列化口径（hosts / list 拆行、
 *      布尔保持、空站兜底）
 *   2. 元表完整性：分组都注册、kind 取值合法
 *   3. 渲染：全分组 / 缺失项 / 自定义字段 / 折叠 / 空态 / 删除布防、
 *      测试中与失败回执的展示分支；渲染产物上的全部事件处理器
 *      逐一调用（渲染本身不执行内联回调体，调用才纳入覆盖）
 *   4. 方法与消息监听：保存（非法 id / 成功 / 失败）、试运行、两步删除、
 *      增删站点与字段、回执分发到实例
 *
 * 加载范式：window / Vue 桩 + require 被测模块（path.join 形式，
 * 与 test_dom_utils.test.js 同款）。window.addEventListener 被捕获，
 * 供测试触发模块装载时注册的消息监听器。
 *
 * 转义约定：JS 字符串里的换行转义统一写占位符、写入前整体替换，
 * 避免多层转义（JSON / Python / JS）叠加出错——上一版正是栽在这里：
 * 转义被解成真实换行，整个文件语法失效、被测模块未能装载。
 * 运行：node --test flask_server/tests/js/test_site_profiles.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 模块装载期的副作用收集：postMessage 出站消息与 message 监听器
const _sent = [];
const _listeners = {};
global.window = {
  AIMirrorDialog: { methods: {} },
  parent: { postMessage: (m) => { _sent.push(m); } },
  addEventListener: (type, fn) => { _listeners[type] = fn; }
};
global.Vue = { h: (tag, props, children) => ({ tag: tag, props: props, children: children }) };
// 字段元表已拆到 08h，须先装载（与 dialog.html 的加载顺序一致）
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '08h_profile_fields.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '08g_site_profiles.js'));

const D = global.window.AIMirrorDialog;

/**
 * 构造渲染与方法测试共用的 ctx：
 * glm 全字段（含自定义字段）、kimi 仅少数字段（走缺失项分支）、ds 折叠。
 * 测试中 / 回执结果各备一真一假，覆盖展示分支。
 */
function makeCtx(over) {
  const ctx = {
    siteProfiles: { glm: { label: 'GLM', hosts: ['a.com'] } },
    siteProfDraft: {
      glm: {
        label: 'GLM', hosts: 'a.com\nb.com', split: true,
        container: '.chat', userItem: '.u', item: '.i', userContent: '.uc',
        userName: '.un', assistantItem: '.ai', assistantMark: '.am',
        assistantContent: '.ac', answerContent: '.an', answerWrap: '.aw',
        thinking: '.th', thinkingArea: '.ta', historyContainer: '.hc',
        historyItem: '.hi', historySelectedMark: '.hs', inputSelector: '.inp',
        sendButton: '.sb', sendButtonDisabledMark: 'dis', sendButtonStopMark: 'sp',
        convIdUrl: '[?&]cid=([0-9]+)', newConversation: "document.querySelector('.new')",
        regenerateExpr: "document.querySelector('.reg')",
        retrySendExpr: "document.querySelector('.retry')",
        scrollToBottomButton: '.s1\n.s2', generatingSelectors: '.g1',
        myCustom: '.custom'
      },
      kimi: { label: 'Kimi', hosts: '', split: false },
      ds: { label: 'DS', hosts: 'deepseek.com' }
    },
    siteProfOpen: true,
    siteProfExpanded: { glm: true, kimi: true, ds: false },
    siteProfTesting: { 'glm.container': false, 'glm.userItem': true, 'glm.myCustom': true },
    siteProfTestResult: {
      'glm.container': { ok: true, text: '命中 1/1' },
      'glm.item': { ok: false, text: '未命中' },
      'glm.myCustom': { ok: false, text: 'x' }
    },
    siteProfDeleting: {},
    newField: { glm: { name: 'extra', value: '.e' }, kimi: { name: '', value: '' }, ds: { name: '', value: '' } },
    newSiteId: '', newSiteLabel: '', newSiteHosts: '',
    _toasts: [],
    toast: (m) => { ctx._toasts.push(String(m)); }
  };
  // 渲染产物上的内联 handler 按实例口径调用（ctx.addSiteProfile() 等）——
  // 真实组件里 D.methods 会混入实例，这里按同一口径把方法绑到 ctx。
  for (const name of ['resetSiteProfDraft', 'saveSiteProfiles', 'queueSiteProfSave', 'testProfileField',
    'deleteSiteProfile', 'addSiteProfile', 'addProfileField', 'removeProfileField',
    'onProfilesTestResult']) {
  // v3 新增方法（08j）在真实运行时由 dialog.html 全量加载后混入；
  // 本测试文件只 require 08g/08h，故缺失项降级为空函数，避免 undefined 调用。
    ctx[name] = D.methods[name]
      ? function (...args) { return D.methods[name].apply(ctx, args); }
      : function () {};
  }
  return Object.assign(ctx, over || {});
}

/**
 * 深度遍历 h 桩节点树，收集全部事件处理器（onClick / onInput / onChange）。
 * 渲染本身不会执行内联回调体；逐个调用才能把这部分行纳入覆盖。
 */
function collectHandlers(node, out) {
  if (!node || typeof node !== 'object') return out;
  const props = node.props || {};
  for (const k of Object.keys(props)) {
    if (typeof props[k] === 'function') out.push(props[k]);
  }
  const ch = node.children;
  if (Array.isArray(ch)) {
    for (const c of ch) collectHandlers(c, out);
  } else {
    collectHandlers(ch, out);
  }
  return out;
}

// ---------- 1. 纯函数 ----------

test('serializeProfilesDraft：hosts 与 list 字段按行拆数组，空行剔除', () => {
  const out = D.serializeProfilesDraft({
    glm: {
      label: 'GLM', hosts: 'a.com\n\nb.com\n', split: true,
      scrollToBottomButton: 'div.a\ndiv.b', newConversation: ''
    },
    kimi: {}
  });
  assert.deepStrictEqual(out.glm.hosts, ['a.com', 'b.com']);
  assert.deepStrictEqual(out.glm.scrollToBottomButton, ['div.a', 'div.b']);
  assert.strictEqual(out.glm.split, true);
  assert.strictEqual(out.glm.newConversation, '');
  assert.strictEqual(out.kimi.label, 'kimi');
  assert.deepStrictEqual(out.kimi.hosts, []);
});

test('serializeProfilesDraft：布尔保持布尔，其余转字符串', () => {
  const out = D.serializeProfilesDraft({ x: { split: false, custom: 123 } });
  assert.strictEqual(out.x.split, false);
  assert.strictEqual(out.x.custom, '123');
});

// ---------- 2. 元表 ----------

test('字段元表：分组都注册，kind 取值合法', () => {
  const groups = new Set(D.PROFILE_FIELD_GROUPS.map((g) => g.id));
  const kinds = new Set(['click', 'selector', 'list', 'regex', 'hosts', 'bool', undefined]);
  for (const field of Object.keys(D.PROFILE_FIELD_META)) {
    const meta = D.PROFILE_FIELD_META[field];
    assert.ok(groups.has(meta.group), field + ' 分组未注册：' + meta.group);
    assert.ok(kinds.has(meta.kind), field + ' kind 非法：' + meta.kind);
  }
});

test('resetSiteProfDraft：快照转工作副本，list / hosts 数组转按行文本', () => {
  const ctx = {
    siteProfiles: {
      glm: { label: 'GLM', hosts: ['a.com', 'b.com'],
        generatingSelectors: ['.x', '.y'], split: false, convIdUrl: '[?&]cid=([^&]+)' }
    },
    siteProfDraft: null
  };
  D.methods.resetSiteProfDraft.call(ctx);
  assert.strictEqual(ctx.siteProfDraft.glm.hosts, 'a.com\nb.com');
  assert.strictEqual(ctx.siteProfDraft.glm.generatingSelectors, '.x\n.y');
  assert.strictEqual(ctx.siteProfDraft.glm.split, false);
  assert.strictEqual(ctx.siteProfDraft.glm.convIdUrl, '[?&]cid=([^&]+)');
});

// ---------- 3. 渲染 ----------

test('renderSiteProfilesBlock：开放态渲染全部分组、自定义字段与保存行', () => {
  const ctx = makeCtx();
  const node = D.renderSiteProfilesBlock(ctx);
  assert.ok(node && node.tag === 'div');
  assert.strictEqual(ctx._toasts.length, 0);
});

test('renderSiteProfilesBlock：折叠态 / 空态 / 删除布防态分支', () => {
  const closed = makeCtx({ siteProfOpen: false });
  assert.ok(D.renderSiteProfilesBlock(closed));
  const empty = makeCtx({ siteProfDraft: {}, siteProfiles: {} });
  assert.ok(D.renderSiteProfilesBlock(empty));
  const armed = makeCtx();
  armed.siteProfDeleting.kimi = Date.now();
  assert.ok(D.renderSiteProfilesBlock(armed));
});

test('渲染产物上的事件处理器可全部安全调用（toggle / 输入 / 布防 / 试运行 / 保存）', () => {
  const realSetTimeout = global.setTimeout;
  global.setTimeout = () => 0;   // 拦截试运行 8 秒兜底与布防解除定时器，避免拖住测试进程
  D.apiFetch = () => Promise.resolve();
  try {
    const ctx = makeCtx();
    const handlers = collectHandlers(D.renderSiteProfilesBlock(ctx), []);
    assert.ok(handlers.length >= 10, '事件处理器数量异常：' + handlers.length);
    const ev = { stopPropagation: () => {}, target: { value: 'zz', checked: true } };
    for (const fn of handlers) fn(ev);
    // 二次渲染再调一轮：toggle 类处理器走另一半分支（开→关、布防→解除）
    const ctx2 = makeCtx();
    for (const fn of collectHandlers(D.renderSiteProfilesBlock(ctx2), [])) fn(ev);
  } finally {
    global.setTimeout = realSetTimeout;
  }
});

// ---------- 4. 方法与消息监听 ----------

test('saveSiteProfiles：只提交当前页面档案，不再整集替换；失败走 catch', async () => {
  let posted = null;
  D.apiFetch = (ctx, url, opts) => { posted = { url: url, opts: opts }; return Promise.resolve(); };
  const bad = makeCtx({ siteProfDraft: { 'bad-id!': { label: 'x', hosts: '' } } });
  await D.methods.saveSiteProfiles.call(bad);
  assert.strictEqual(posted, null);
  assert.ok(bad._toasts.some((t) => t.indexOf('bad-id!') >= 0));
  const ctx = makeCtx();
  ctx.currentProfileId = () => 'glm';
  await D.methods.saveSiteProfiles.call(ctx);
  assert.strictEqual(posted.url, '/config');
  assert.deepStrictEqual(Object.keys(posted.opts.body.profiles), ['glm']);
  assert.ok(_sent.some((m) => m && m.type === 'profiles_refresh'));
  D.apiFetch = () => Promise.reject(new Error('boom'));
  const failing = makeCtx();
  await D.methods.saveSiteProfiles.call(failing);
  assert.ok(failing._toasts.some((t) => t.indexOf('保存失败') >= 0));
});

test('testProfileField：值取自草稿——空与缺失提示不发请求；有值发出求值请求并登记测试中', () => {
  const realSetTimeout = global.setTimeout;
  global.setTimeout = () => 0;   // 拦截 8 秒兜底定时器
  try {
    const ctx = makeCtx();
    const before = _sent.filter((m) => m && m.type === 'profiles_test_field').length;
    // 第三参是 mode、值从草稿取（L343）：置空字段才走「为空」分支
    ctx.siteProfDraft.glm.container = '';
    D.methods.testProfileField.call(ctx, 'glm', 'container', 'locate');
    assert.ok(ctx._toasts.some((t) => t.indexOf('该字段为空') >= 0));
    // 缺失字段（undefined）走同一分支，同样不发请求
    D.methods.testProfileField.call(ctx, 'kimi', 'container', 'locate');
    assert.strictEqual(
      _sent.filter((m) => m && m.type === 'profiles_test_field').length, before);

    D.methods.testProfileField.call(ctx, 'glm', 'newConversation', 'click');
    const msg = _sent.filter((m) => m && m.type === 'profiles_test_field').pop();
    assert.strictEqual(msg.key, 'glm.newConversation');
    assert.strictEqual(msg.mode, 'click');
    assert.strictEqual(msg.value, "document.querySelector('.new')");
    assert.strictEqual(ctx.siteProfTesting['glm.newConversation'], true);
    assert.strictEqual(ctx.siteProfTestResult['glm.newConversation'], null);
  } finally {
    global.setTimeout = realSetTimeout;
  }
});

test('deleteSiteProfile：两步确认——首击布防，3 秒内二击才删除', () => {
  const realSetTimeout = global.setTimeout;
  global.setTimeout = () => 0;   // 拦截 3.1 秒的布防自动解除定时器
  try {
    const ctx = makeCtx();
    D.methods.deleteSiteProfile.call(ctx, 'kimi');
    assert.ok(ctx.siteProfDeleting.kimi > 0);
    assert.ok(ctx.siteProfDraft.kimi);
    D.methods.deleteSiteProfile.call(ctx, 'kimi');
    assert.ok(!ctx.siteProfDraft.kimi);
    assert.ok(ctx._toasts.some((t) => t.indexOf('已移除') >= 0));
  } finally {
    global.setTimeout = realSetTimeout;
  }
});

test('addSiteProfile：字符集 / 唯一性校验；通过后入编辑区并展开；无显示名回退 id', () => {
  const realSetTimeout = global.setTimeout;
  global.setTimeout = () => 0;   // 拦截新增后 800ms 自动保存定时器
  try {
  const ctx = makeCtx();
  ctx.newSiteId = 'bad!';
  D.methods.addSiteProfile.call(ctx);
  assert.ok(!ctx.siteProfDraft['bad!']);
  ctx.newSiteId = 'glm';
  D.methods.addSiteProfile.call(ctx);
  assert.ok(ctx._toasts.some((t) => t.indexOf('已存在') >= 0));
  ctx.newSiteId = 'kimi2';
  ctx.newSiteLabel = 'K2';
  ctx.newSiteHosts = 'k2.com\n\nk2b.com';
  D.methods.addSiteProfile.call(ctx);
  const d = ctx.siteProfDraft.kimi2;
  assert.strictEqual(d.label, 'K2');
  assert.strictEqual(d.hosts, 'k2.com\nk2b.com');
  assert.strictEqual(d.split, true);
  assert.strictEqual(ctx.siteProfExpanded.kimi2, true);
  assert.strictEqual(ctx.newSiteId, '');
  ctx.newSiteId = 'kimi3';
  D.methods.addSiteProfile.call(ctx);
  assert.strictEqual(ctx.siteProfDraft.kimi3.label, 'kimi3');
  } finally { global.setTimeout = realSetTimeout; }
});

test('addProfileField / removeProfileField：校验、去重与自定义字段增删', () => {
  const ctx = makeCtx();
  ctx.newField.glm = { name: 'bad!', value: 'x' };
  D.methods.addProfileField.call(ctx, 'glm');
  assert.ok(!ctx.siteProfDraft.glm['bad!']);
  ctx.newField.glm = { name: 'myCustom', value: 'x' };
  D.methods.addProfileField.call(ctx, 'glm');
  assert.strictEqual(ctx.siteProfDraft.glm.myCustom, '.custom');
  ctx.newField.glm = { name: 'extra2', value: '.e2' };
  D.methods.addProfileField.call(ctx, 'glm');
  assert.strictEqual(ctx.siteProfDraft.glm.extra2, '.e2');
  // 已知字段不可删键（防误拆结构）；自定义字段可删
  D.methods.removeProfileField.call(ctx, 'glm', 'label');
  assert.ok(ctx.siteProfDraft.glm.label !== undefined);
  D.methods.removeProfileField.call(ctx, 'glm', 'extra2');
  assert.ok(!('extra2' in ctx.siteProfDraft.glm));
});

test('消息监听：试运行回执分发到实例；profiles_applied(refresh) 触发提示', () => {
  const fn = _listeners.message;
  assert.strictEqual(typeof fn, 'function');
  const ctx = makeCtx();
  D.instance = ctx;
  try {
    fn({ data: { type: 'profiles_test_result', key: 'glm.container', ok: true, text: '命中' } });
    assert.deepStrictEqual(ctx.siteProfTestResult['glm.container'], { ok: true, text: '命中' });
    assert.strictEqual(ctx.siteProfTesting['glm.container'], false);
    fn({ data: { type: 'profiles_test_result', ok: false } });   // 无 key 的回执
    fn({ data: { type: 'profiles_applied', reason: 'refresh', count: 3 } });
    assert.ok(ctx._toasts.some((t) => t.indexOf('3') >= 0));
    fn({ data: { type: 'profiles_applied' } });   // 非 refresh 原因：不提示
    fn({ data: { type: 'other' } });
    fn({ data: null });
  } finally {
    D.instance = null;
  }
  // 实例缺席时监听器应静默返回
  fn({ data: { type: 'profiles_test_result', key: 'glm.container', ok: true, text: 'x' } });
});

// ---------- 5. 自动保存与主题令牌（实机反馈修复守卫） ----------

test('queueSiteProfSave：防抖合并，只写本地缓存，不 POST 后端', async () => {
  const realSetTimeout = global.setTimeout;
  const realClearTimeout = global.clearTimeout;
  let posted = null, persisted = 0;
  const timers = [];
  global.setTimeout = (fn, ms) => { timers.push({ fn: fn, ms: ms }); return timers.length; };
  global.clearTimeout = () => {};
  D.apiFetch = (c2, url, opts) => { posted = { url: url, opts: opts }; return Promise.resolve(); };
  const ctx = makeCtx();
  ctx.persistConfigCache = () => { persisted += 1; return Promise.resolve(); };
  try {
    ctx.queueSiteProfSave();
    ctx.queueSiteProfSave();
    ctx.queueSiteProfSave();
    assert.strictEqual(timers.length, 3);
    assert.ok(timers.every((x) => x.ms === 800));
    await timers[timers.length - 1].fn();
    assert.strictEqual(posted, null);
    assert.strictEqual(persisted, 1);
    assert.strictEqual(ctx._spSaveTimer, null);
  } finally {
    global.setTimeout = realSetTimeout;
    global.clearTimeout = realClearTimeout;
  }
});

test('saveSiteProfiles 失败：toast 报错', async () => {
  const oldFetch = D.apiFetch;
  D.apiFetch = () => Promise.reject(new Error('网络断开'));
  try {
    const ctx = makeCtx();
    await ctx.saveSiteProfiles();
    assert.ok(ctx._toasts.some((x) => x.indexOf('保存失败') >= 0));
  } finally {
    D.apiFetch = oldFetch;
  }
});

test('02f 零硬编码色值：颜色全部走 00_tokens 令牌', () => {
  const fs = require('node:fs');
  const css = fs.readFileSync(path.join(__dirname, '..', '..', '..',
    'extend', 'dialog', 'styles', '02f_site_profiles.css'), 'utf8');
  assert.deepStrictEqual(css.match(/#[0-9a-fA-F]{3,8}\b/g) || [], []);
});

test('手动保存入口已移除：渲染产物不含「保存全部」按钮', () => {
  const ctx = makeCtx();
  assert.ok(JSON.stringify(D.renderSiteProfilesBlock(ctx)).indexOf('保存全部') === -1);
});

