/* ============================================================
 * 模块：G-C 阶段 2 翻译员验收 · 纯逻辑逐项实跑夹具
 * 用途：按规格第七节阶段 2 五项与 4.1-4.6，逐项跑通翻译员本体，
 *       给出 pass/fail 分母；不依赖浏览器、不改运行时状态。
 * 依赖：extend/lib/dialects.js 与 extend/lib/translator.js（UMD 先立 window）。
 * 边界：只读加载本体，不装配运行时 M、不翻 STATUS、不碰活链九文件。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
// 工程根目录：由本夹具所在目录向上三级取得。
const ROOT = path.join(__dirname, '..', '..', '..');
// lib 模块按 UMD 挂到 window；node 侧先立一个空 window 再 require。
global.window = {};
// 方言层：语言包与四支处理函数。
const DIA = require(path.join(ROOT, 'extend', 'lib', 'dialects.js'));
// 翻译员本体：提示词拼装、双向翻译、取回入口。
const T = require(path.join(ROOT, 'extend', 'lib', 'translator.js'));

// GC-1：验证取回的标准四段前置、方言说明追加在后。
// 同时验证后端不可达时 composePrompt 落兜底四段，流程不中断。
test('GC-1 提示词：标准四段前置、方言追加、后端不可达兜底', () => {
  // 拼装结果以标准四段开头，且标准段在方言段之前。
  const out = T.composePrompt('【身份】A', '【方言】B');
  assert.ok(out.startsWith('【身份】A'));
  assert.ok(out.indexOf('【身份】A') < out.indexOf('【方言】B'));
  // 空入参时兜底四段仍在，提示词不为空。
  assert.ok(T.composePrompt('', '').includes('【调用前先查参数】'));
});

// GC-2：验证 bridge-chat-call 翻成标准 tool_calls。
// 单块产 function 调用，多块只取首个并告警，非法输入返回空。
test('GC-2 调用解析：单个/多个/非法输入', () => {
  // 单个调用：id 带 call_ 前缀、type 为 function、参数 JSON 化。
  const c = T.toToolCalls({ tool: 'read_file', type: 'bridge-chat-call', nonce: 'n1', parameters: { path: 'a.txt' } });
  assert.strictEqual(c[0].id, 'call_n1');
  assert.strictEqual(c[0].type, 'function');
  assert.deepStrictEqual(JSON.parse(c[0].function.arguments), { path: 'a.txt' });
  // 一轮多块：网页 AI 单线程，只送首个并给拦截告警。
  const many = T.fromBlocks([{ tool: 'a', type: 'bridge-chat-call', nonce: '1' },
                             { tool: 'b', type: 'bridge-chat-call', nonce: '2' }]);
  assert.strictEqual(many.calls.length, 1);
  assert.strictEqual(many.warning, 'multiple_tool_calls');
  // 非法入参不产生调用。
  assert.deepStrictEqual(T.toToolCalls(null), []);
});

// GC-3：验证标准 tool 消息与 bridge-chat-res 往返。
// call_ 前缀必须剥回原始 nonce，失败信封与非 tool 消息也要稳。
test('GC-3 结果回传：标准 tool 消息到 bridge-chat-res 往返且剥 call_ 前缀', () => {
  // 执行信封包进 content，标准三键齐全。
  const env = { success: true, result: { lines: 3 }, executed: true };
  const msg = T.toToolMessage('call_9', 'read_file', env);
  assert.strictEqual(msg.role, 'tool');
  assert.strictEqual(msg.tool_call_id, 'call_9');
  // 回前端时 nonce 剥回 9，结果字段原样带出。
  const back = JSON.parse(T.fromToolMessage(msg));
  assert.strictEqual(back.type, 'bridge-chat-res');
  assert.strictEqual(back.nonce, '9');
  assert.deepStrictEqual(back.result, { lines: 3 });
  // 失败信封保留 success=false 与诊断字段。
  const bad = JSON.parse(T.fromToolMessage(T.toToolMessage('c2', 'run_command',
    { success: false, error: 'boom', hint: '改参数' })));
  assert.strictEqual(bad.success, false);
  // 非 tool 消息不翻译，返回空串。
  assert.strictEqual(T.fromToolMessage({ role: 'user' }), '');
});

// GC-4：验证语言包从 custom_config 原样取回。
// 中文、嵌套、null 不丢；缺键回退出厂值；后端不可达不中断。
test('GC-4 语言包：中文嵌套 null 原样、缺键回退、未注册不中断', async () => {
  // 构造含中文键、嵌套数组、null 的站点档案。
  const rich = { '输入框': '#x', '嵌套': { '层': [1, null, true] }, '空值': null };
  // 整份 custom_config 即语言包；显式「语言包」子对象优先。
  assert.deepStrictEqual(DIA.languagePack(rich), rich);
  assert.deepStrictEqual(DIA.languagePack({ '语言包': rich }), rich);
  // 缺键时回退出厂选择器，不抛错。
  assert.strictEqual(DIA.resolve(null, 'inputSelector'), DIA.FALLBACK.inputSelector);
  // 注入 apiFetch 模拟 /api/clients 取回，原样不解释。
  const got = await T.fetchLanguagePack((c, p) => Promise.resolve({ custom_config: rich }), {}, 'qianwen');
  assert.deepStrictEqual(got, rich);
  // 后端不可达返回 null，由上层兜底，不抛异常。
  assert.strictEqual(await T.fetchLanguagePack((c, p) => Promise.reject(new Error('offline')), {}, 'glm'), null);
});

// GC-5：验证指令执行端对接服务端下发的指令定义。
// 清单与帮助文本同批取回；单接口失败给空值，全流程不阻断。
test('GC-5 指令对接：清单与帮助文本同批取回、单接口失败不阻断', async () => {
  // 记录请求路径，确认两个接口都被打到。
  const paths = [];
  const api = (c, p) => { paths.push(p); return Promise.resolve(
    p.includes('/help') ? { help: '内置指令 /x' } : { commands: [{ name: '/x', source: 'builtin' }] }); };
  const out = await T.fetchCommands(api, {});
  assert.deepStrictEqual(out.commands, [{ name: '/x', source: 'builtin' }]);
  assert.strictEqual(out.help, '内置指令 /x');
  assert.ok(paths.includes('/api/commands') && paths.includes('/api/commands/help'));
  // 整体离线时返回空清单与空帮助，不阻断启动。
  const none = await T.fetchCommands((c, p) => Promise.reject(new Error('offline')), {});
  assert.deepStrictEqual(none, { commands: [], help: '' });
});

// GC-6：验证一个本体配多套方言、四支处理函数与标准提示词取回。
// 站点覆盖表含 yuanbao；取回失败返回空串交拼装层兜底。
test('GC-6 方言与兜底：多套分派、四支处理函数、标准提示词取回', async () => {
  // 已登记方言数不少于五套，且按站点 id 分派。
  const ids = DIA.list();
  assert.ok(ids.length >= 5);
  assert.ok(ids.includes('yuanbao'));
  for (const id of ids) assert.strictEqual(DIA.pick(id).id, id);
  // 四支处理函数均为可调用实现。
  const h = DIA.handlers();
  for (const k of ['locate','write','send','generating']) assert.strictEqual(typeof h[k], 'function');
  // /v1/system_prompt 正常取回与失败兜底。
  assert.strictEqual(await T.fetchStandard(() => Promise.resolve({ system_prompt: '四段' }), {}), '四段');
  assert.strictEqual(await T.fetchStandard(() => Promise.reject(new Error('x')), {}), '');
});
