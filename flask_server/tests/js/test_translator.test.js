/* ============================================================
 * 阶段 2 翻译员本体与方言：纯逻辑验收
 *
 * 一个本体 + 多套方言（决策 1）、标准 tool_calls / tool 消息双向翻译、
 * 取回标准四段 / 语言包 / 服务端指令定义。注入式 apiFetch 与 dom 桩，
 * 不依赖浏览器，也不触碰既有建卡链路（阶段 2 行为不变）。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const LIB = path.join(__dirname, '..', '..', '..', 'extend', 'lib');

// lib 模块按 UMD 挂到 window；node 侧先立一个空 window 再 require。
global.window = {};
const DIA = require(path.join(LIB, 'dialects.js'));
const T = require(path.join(LIB, 'translator.js'));

// ---------- 1. 多套方言与语言包 ----------

test('方言表：登记多套且按站点分派，未知站点回退本体默认', () => {
  const ids = DIA.list();
  assert.ok(ids.length >= 5, '未体现「多套」：' + ids.join(','));
  assert.ok(ids.includes('glm') && ids.includes('qianwen'));
  for (const id of ids) assert.strictEqual(DIA.pick(id).id, id);
  const unknown = DIA.pick('never-seen-site');
  assert.strictEqual(unknown.id, 'never-seen-site');
  assert.strictEqual(typeof unknown.handlers.locate, 'function');
  assert.strictEqual(typeof unknown.handlers.generating, 'function');
});

test('语言包：custom_config 原样取回，中文/嵌套/null 不丢；显式「语言包」子对象优先', () => {
  const rich = { '输入框': '#x', '嵌套': { '层': [1, null, true] }, '空值': null };
  assert.deepStrictEqual(DIA.languagePack(rich), rich);
  const wrapped = { '语言包': rich, '其它': 1 };
  assert.deepStrictEqual(DIA.languagePack(wrapped), rich);
  assert.strictEqual(DIA.languagePack(null), null);
  assert.strictEqual(DIA.languagePack('junk'), null);
});

test('选择器解析：缺键/异常类型回退出厂值，数组去空', () => {
  assert.strictEqual(DIA.resolve(null, 'inputSelector'), DIA.FALLBACK.inputSelector);
  assert.strictEqual(DIA.resolve({ inputSelector: '  #mine  ' }, 'inputSelector'), '#mine');
  assert.deepStrictEqual(DIA.resolve({ generatingSelectors: [' .a ', '', '.b'] }, 'generatingSelectors'), ['.a', '.b']);
  assert.ok(Array.isArray(DIA.resolve({}, 'generatingSelectors')));
});

test('四支方言处理函数：locate / write / send / generating 都走注入的 dom 原语', () => {
  const hits = [];
  const dom = {
    query: (s) => { hits.push('q:' + s); return { tag: s }; },
    setValue: (el, t) => { hits.push('w:' + t); return true; },
    click: (b) => { hits.push('c'); return true; },
    press: (el) => { hits.push('p'); return true; },
    disabled: () => false
  };
  const h = DIA.handlers();
  const pack = { inputSelector: '#in', sendButton: '#send', generatingSelectors: ['.g'] };
  const c = { pack, dom, text: '你好' };
  h.locate(c); h.write(c); h.send(c);
  assert.ok(hits.some((x) => x === 'q:#in'));
  assert.ok(hits.some((x) => x === 'w:你好'));
  assert.ok(hits.some((x) => x === 'c'));
  // 按钮被禁用时改走回车
  const dom2 = Object.assign({}, dom, { disabled: () => true, press: () => { hits.push('p2'); return true; } });
  assert.strictEqual(h.send(Object.assign({}, c, { dom: dom2 })), true);
  assert.ok(hits.includes('p2'));
  // 生成态：命中选择器为真，空列表为假
  assert.strictEqual(h.generating(c), true);
  assert.strictEqual(h.generating(Object.assign({}, c, { pack: {} })), true);
  assert.strictEqual(h.generating(Object.assign({}, c, {
    pack: { generatingSelectors: [] }, dom: Object.assign({}, dom, { query: () => null })
  })), false);
  // write 未给 el 时自行定位
  const hits3 = [];
  h.write({ pack, dom: Object.assign({}, dom, { setValue: () => { hits3.push(1); } }), text: 'x' });
  assert.strictEqual(hits3.length, 1);
});

// ---------- 2. 提示词：标准四段 + 方言 ----------

test('兜底标准四段齐全，段落名与服务端 MARK_* 一致', () => {
  const s = T.FALLBACK_STANDARD;
  for (const mark of ['【身份】', '【规则】', '【技能】', '【调用前先查参数】']) {
    assert.ok(s.includes(mark), '缺段：' + mark);
  }
});

test('composePrompt：取回的标准四段在前，方言说明追加在后；缺参各走兜底', () => {
  const out = T.composePrompt('【身份】A', '【方言】B');
  assert.ok(out.indexOf('【身份】A') < out.indexOf('【方言】B'));
  const empty = T.composePrompt('', '');
  assert.ok(empty.includes('【身份】') && empty.includes('【方言·工具调用格式】'));
  assert.ok(T.composePrompt(null, null).includes('bridge-chat-call'));
});

test('defaultDialect：调用/回传格式齐全，语音开关控制朗读稿段落', () => {
  const off = T.defaultDialect({ toolLines: '1. read_file — 读文件' });
  assert.ok(off.includes('bridge-chat-call') && off.includes('bridge-chat-res'));
  assert.ok(off.includes('1. read_file — 读文件'));
  assert.ok(!off.includes('bridge-voice'));
  const on = T.defaultDialect({ voiceOn: true });
  assert.ok(on.includes('bridge-voice') && on.includes('【方言·朗读稿约定】'));
  assert.ok(T.defaultDialect({}).includes('（暂无工具）'));
});

// ---------- 3. 双向翻译 ----------

test('toToolCalls：bridge-chat-call → 标准 function 调用；非法输入返回空', () => {
  const calls = T.toToolCalls({ tool: 'read_file', type: 'bridge-chat-call', nonce: 'n1',
    parameters: { path: 'a.txt' } });
  assert.strictEqual(calls.length, 1);
  assert.strictEqual(calls[0].id, 'call_n1');
  assert.strictEqual(calls[0].type, 'function');
  assert.strictEqual(calls[0].function.name, 'read_file');
  assert.deepStrictEqual(JSON.parse(calls[0].function.arguments), { path: 'a.txt' });
  assert.deepStrictEqual(T.toToolCalls(null), []);
  assert.deepStrictEqual(T.toToolCalls({ type: 'other', tool: 'x' }), []);
  assert.deepStrictEqual(T.toToolCalls({ type: 'bridge-chat-call' }), []);
  assert.deepStrictEqual(JSON.parse(T.toToolCalls({ tool: 'x', type: 'bridge-chat-call' })[0].function.arguments), {});
});

test('fromBlocks：一轮多个调用只取首个并给 multiple_tool_calls 告警', () => {
  const one = T.fromBlocks([{ tool: 'a', type: 'bridge-chat-call', nonce: '1' }]);
  assert.strictEqual(one.calls.length, 1);
  assert.strictEqual(one.warning, '');
  const many = T.fromBlocks([
    { tool: 'a', type: 'bridge-chat-call', nonce: '1' },
    { tool: 'b', type: 'bridge-chat-call', nonce: '2' }
  ]);
  assert.strictEqual(many.calls.length, 1);
  assert.strictEqual(many.warning, 'multiple_tool_calls');
  assert.deepStrictEqual(T.fromBlocks(null), { calls: [], warning: '' });
  assert.deepStrictEqual(T.fromBlocks([{ type: 'x' }]).calls, []);
});

test('toToolMessage / fromToolMessage：标准 tool 消息与 bridge-chat-res 往返', () => {
  const env = { success: true, result: { lines: 3 }, executed: true };
  const msg = T.toToolMessage('call_9', 'read_file', env);
  assert.strictEqual(msg.role, 'tool');
  assert.strictEqual(msg.tool_call_id, 'call_9');
  assert.strictEqual(msg.name, 'read_file');
  assert.deepStrictEqual(JSON.parse(msg.content), env);
  const text = T.fromToolMessage(msg);
  const back = JSON.parse(text);
  assert.strictEqual(back.type, 'bridge-chat-res');
  assert.strictEqual(back.tool, 'read_file');
  // 阶段 2 返工：标准 id 的 call_ 前缀必须剥回原始 nonce，不能吐回前端。
  assert.strictEqual(back.nonce, '9');
  assert.strictEqual(back.nonce.indexOf('call_'), -1);
  assert.strictEqual(back.success, true);
  assert.deepStrictEqual(back.result, { lines: 3 });
  // 失败信封：success=false 且带 error/hint
  const bad = JSON.parse(T.fromToolMessage(T.toToolMessage('c2', 'run_command',
    { success: false, error: 'boom', hint: '改参数' })));
  assert.strictEqual(bad.success, false);
  assert.strictEqual(bad.error, 'boom');
  assert.strictEqual(bad.hint, '改参数');
  // 非 tool 消息 / 损坏 content
  assert.strictEqual(T.fromToolMessage({ role: 'user' }), '');
  assert.strictEqual(T.fromToolMessage(null), '');
  const broken = JSON.parse(T.fromToolMessage({ role: 'tool', name: 'x', content: '{oops' }));
  assert.strictEqual(broken.success, true);
  assert.strictEqual(T.toToolMessage('', '', null).content, '{}');
});

// ---------- 4. 异步取回（注入 apiFetch）----------

test('fetchStandard：取回 system_prompt；失败/缺字段回退空串由拼装层兜底', async () => {
  const ok = await T.fetchStandard(() => Promise.resolve({ system_prompt: '四段全文' }), {});
  assert.strictEqual(ok, '四段全文');
  assert.strictEqual(await T.fetchStandard(() => Promise.resolve({}), {}), '');
  assert.strictEqual(await T.fetchStandard(() => Promise.reject(new Error('offline')), {}), '');
});

test('fetchLanguagePack：按 site_key 取 custom_config；空 key / 404 不兜底但返回 null', async () => {
  let seen = '';
  const api = (ctx, p) => { seen = p; return Promise.resolve({ custom_config: { '输入框': '#x' } }); };
  assert.deepStrictEqual(await T.fetchLanguagePack(api, {}, 'qianwen'), { '输入框': '#x' });
  assert.ok(seen.includes('site_key=qianwen'));
  assert.strictEqual(await T.fetchLanguagePack(api, {}, ''), null);
  assert.strictEqual(await T.fetchLanguagePack(() => Promise.reject(new Error('404')), {}, 'glm'), null);
  assert.strictEqual(await T.fetchLanguagePack(() => Promise.resolve({}), {}, 'glm'), null);
});

test('fetchCommands：清单与帮助文本同批取回；单接口失败给空值不阻断', async () => {
  const paths = [];
  const api = (ctx, p) => { paths.push(p); return Promise.resolve(
    p.includes('/help') ? { help: '内置指令\n/x' } : { commands: [{ name: '/x', source: 'builtin' }] }); };
  const out = await T.fetchCommands(api, {});
  assert.deepStrictEqual(out.commands, [{ name: '/x', source: 'builtin' }]);
  assert.strictEqual(out.help, '内置指令\n/x');
  assert.ok(paths.includes('/api/commands') && paths.includes('/api/commands/help'));
  const partial = await T.fetchCommands((ctx, p) => p.includes('/help')
    ? Promise.reject(new Error('x')) : Promise.resolve({ commands: [1] }), {});
  assert.deepStrictEqual(partial.commands, [1]);
  assert.strictEqual(partial.help, '');
  const none = await T.fetchCommands(() => Promise.reject(new Error('offline')), {});
  assert.deepStrictEqual(none, { commands: [], help: '' });
});

test('dialectFor：本体薄包装 dialects.pick，不为每站新建本体', () => {
  assert.strictEqual(T.dialectFor('glm').id, 'glm');
  assert.strictEqual(typeof T.dialectFor('').handlers.write, 'function');
});

// ---------- 5. 既有文件接线核对（阶段 2 落地）----------

test('05c 接线：标准四段前置 + 原模板方言；C-4 的 toFlatParams 与工具清单不回退', () => {
  const fs = require('node:fs');
  const R5 = path.join(__dirname, '..', '..', '..');
  const dialog = { methods: {}, log: () => {} };
  global.window = {
    AIMirrorDialog: dialog,
    AIMirrorDialects: DIA,
    AIMirrorTranslator: T,
    AIMirrorDomUtils: { toArray: (v) => (Array.isArray(v) ? v : []) },
    AIMirrorToolSchema: { toFlatParams: () => [] },
    parent: { postMessage: () => {} }, addEventListener: () => {}
  };
  global.Vue = { h: () => ({}) };
  require(path.join(R5, 'extend', 'dialog', 'parts', '05c_prompt.js'));
  const M = dialog.methods;
  const ctx = { tools: [{ name: 'read_file', description: '读文件' }],
    rules: [], promptSections: [], skills: [], bridgePush: null };
  T.state.standard = '【身份】标准四段';
  const out = M.generateSystemPrompt.call(ctx);
  assert.ok(out.startsWith('【身份】标准四段'), '标准四段未前置');
  assert.ok(out.indexOf('【身份】标准四段') < out.indexOf('Tool·调用说明'));
  assert.ok(out.includes('parameters 是标准 JSON Schema'), 'C-4 文案被回退');
  assert.ok(out.includes('1. read_file — 读文件'), '工具清单渲染被回退');
  assert.ok(out.includes('bridge-chat-call') && out.includes('bridge-chat-res'));
  T.state.standard = '';
  const fb = M.generateSystemPrompt.call(ctx);
  assert.ok(fb.includes('【调用前先查参数】'), '后端不可达未走兜底四段');
  assert.ok(fb.includes('Tool·调用说明'));
  const src = fs.readFileSync(path.join(R5, 'extend', 'dialog', 'parts', '05c_prompt.js'), 'utf8');
  assert.ok(src.includes('window.AIMirrorToolSchema.toFlatParams'), 'L180 调用丢失');
  assert.ok(src.includes('T.composePrompt(T.state.standard, dialect)'));
});

test('05c 兜底：本体未挂载时逐字退回原模板（旧夹具行为不变）', () => {
  const R7 = path.join(__dirname, '..', '..', '..');
  const fs = require('node:fs');
  const dialog2 = { methods: {}, log: () => {} };
  global.window = {
    AIMirrorDialog: dialog2,
    AIMirrorDomUtils: { toArray: (v) => (Array.isArray(v) ? v : []) },
    AIMirrorToolSchema: { toFlatParams: () => [] },
    parent: { postMessage: () => {} }, addEventListener: () => {}
  };
  global.Vue = { h: () => ({}) };
  // 删缓存后重新加载，确保这次 IIFE 读到的是「无本体」的 window
  const p = path.join(R7, 'extend', 'dialog', 'parts', '05c_prompt.js');
  delete require.cache[require.resolve(p)];
  require(p);
  const ctx = { tools: [], rules: [], promptSections: [], skills: [], bridgePush: null };
  const text = dialog2.methods.generateSystemPrompt.call(ctx);
  assert.ok(text.startsWith('本会话通过'), '未逐字退回原模板');
  assert.ok(!text.includes('【调用前先查参数】'));
});

test('接线静态核对：两份挂载 + 五文件取用 + BUILD_TAG v21', () => {
  const fs = require('node:fs');
  const R6 = path.join(__dirname, '..', '..', '..');
  const rd = (p) => fs.readFileSync(path.join(R6, p), 'utf8');
  const html = rd('extend/dialog/dialog.html');
  const mf = JSON.parse(rd('extend/manifest.json'));
  assert.ok(html.includes('lib/dialects.js') && html.includes('lib/translator.js'));
  const js = mf.content_scripts[0].js;
  assert.ok(js.indexOf('lib/dialects.js') < js.indexOf('content/00_state.js'));
  assert.ok(js.includes('lib/translator.js'));
  const b = rd('extend/dialog/parts/01b_bridge.js');
  assert.ok(b.includes('/api/commands') && b.includes('refreshCommandDefinitions') && b.includes('T.fetchCommands'));
  assert.ok(b.includes('T.fetchLanguagePack') && b.includes('T.fetchStandard'));
  const c6 = rd('extend/dialog/parts/01c_bridge_cmd.js');
  assert.ok(c6.includes('commandSource') && c6.includes('commandDefinitions'));
  assert.ok(rd('extend/content/00_state.js').includes('languagePack: null'));
  const ix = rd('extend/content/05_index.js');
  assert.ok(ix.includes('A.applyLanguagePack') && ix.includes('c5-translator-v21'));
  assert.ok(ix.includes('A.applyLanguagePack(resp.profiles)'));
});

// C-7 P2 [translator]：原件新增标准 tool_call.id / tool 消息入口断言基准。
// 旧链断言逐条保留（运行时执行权仍在旧直调路径），活链保持、旧标记不摘。
// 唯一键断言由 _c7_standard_entry 统一提供，平行夹具保留作补充。
require('node:test')(
  'C-7 标准入口基准 [translator]',
  () => require('./_c7_standard_entry').run(require('node:assert/strict'), 'translator')
);
