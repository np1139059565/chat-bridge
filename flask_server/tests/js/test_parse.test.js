/* ============================================================
 * 前端解析逻辑测试（node 自带测试运行器）
 *
 * 覆盖 extend/dialog/parts/05f_parse.js 中的纯逻辑：
 *   - _repairJsonControlChars 修复字符串内裸控制字符
 *   - parseToolCall           识别工具调用代码块
 *   - parseVoiceBlock         提取语音朗读块
 *   - parseExternalCall       识别外部调用信封
 *   - msgSource               判定消息来源（user/assistant/tool）
 *
 * 运行方式：
 *   node --test flask_server/tests/js/
 *
 * 说明：05f_parse.js 依赖 window.AIMirrorDialog（methods）与 window.AIMirrorDomUtils。
 * 本文件先构造这两个全局桩，再加载被测模块。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// ---- 全局桩：必须在加载被测模块之前就位 ----
// AIMirrorDomUtils.toArray：与真实实现一致（数组原样，对象取 values，其余空）
function toArray(v) {
  if (Array.isArray(v)) return v;
  if (v && typeof v === 'object') return Object.values(v);
  return [];
}

// AIMirrorDialog：提供 methods 命名空间与 log 兜底
const dialog = { methods: {}, log: () => {} };
global.window = { AIMirrorDialog: dialog, AIMirrorDomUtils: { toArray } };

// 加载被测模块（路径相对本测试文件）
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05f_parse.js'));

// 被测方法集合：05f_parse 把方法挂到 dialog.methods
const M = dialog.methods;

// ---------- _repairJsonControlChars ----------

test('修复控制字符：字符串内的裸换行被转义', () => {
  const src = '{"a":"x\ny"}';           // 字符串内真实换行（非法 JSON）
  const fixed = M._repairJsonControlChars(src);
  assert.strictEqual(fixed, '{"a":"x\\ny"}');
  assert.doesNotThrow(() => JSON.parse(fixed));
});

test('修复控制字符：制表符被转义', () => {
  const fixed = M._repairJsonControlChars('{"a":"x\ty"}');
  assert.strictEqual(fixed, '{"a":"x\\ty"}');
  assert.doesNotThrow(() => JSON.parse(fixed));
});

test('修复控制字符：字符串外的换行（结构缩进）原样保留', () => {
  const src = '{\n"a":1\n}';
  assert.strictEqual(M._repairJsonControlChars(src), src);
});

test('修复控制字符：已转义的换行不重复处理', () => {
  const src = '{"a":"x\\ny"}';          // 已经是合法 \n
  assert.strictEqual(M._repairJsonControlChars(src), src);
});

test('修复控制字符：无控制字符时原样返回', () => {
  const src = '{"a":"hello"}';
  assert.strictEqual(M._repairJsonControlChars(src), src);
});

test('修复控制字符：空输入返回空串', () => {
  assert.strictEqual(M._repairJsonControlChars(''), '');
  assert.strictEqual(M._repairJsonControlChars(null), '');
});

test('修复控制字符：其它控制字符转为 \\uXXXX', () => {
  const src = '{"a":"x\u0001y"}';        // 真实 0x01 控制字符
  const fixed = M._repairJsonControlChars(src);
  assert.ok(fixed.indexOf('\\u0001') >= 0);
  assert.doesNotThrow(() => JSON.parse(fixed));
});

// ---------- parseToolCall ----------

test('工具调用：标准代码块被识别', () => {
  const block = { type: 'code', code: '{"tool":"t","type":"bridge-chat-call","parameters":{"a":1}}' };
  assert.deepStrictEqual(M.parseToolCall(block), { tool: 't', parameters: { a: 1 } });
});

test('工具调用：非代码块返回 null', () => {
  assert.strictEqual(M.parseToolCall({ type: 'text', text: 'x' }), null);
  assert.strictEqual(M.parseToolCall(null), null);
});

test('工具调用：缺少 bridge-chat-call 标记返回 null', () => {
  const block = { type: 'code', code: '{"tool":"t","parameters":{}}' };
  assert.strictEqual(M.parseToolCall(block), null);
});

test('工具调用：非 JSON 返回 null', () => {
  assert.strictEqual(M.parseToolCall({ type: 'code', code: 'console.log(1)' }), null);
});

test('工具调用：字符串内裸换行时自动修复后解析成功', () => {
  const block = { type: 'code', code: '{"tool":"t","type":"bridge-chat-call","parameters":{"a":"x\ny"}}' };
  const got = M.parseToolCall(block);
  assert.strictEqual(got.tool, 't');
  assert.strictEqual(got.parameters.a, 'x\ny');
});

test('工具调用：parameters 缺失时回退空对象', () => {
  const block = { type: 'code', code: '{"tool":"t","type":"bridge-chat-call"}' };
  assert.deepStrictEqual(M.parseToolCall(block), { tool: 't', parameters: {} });
});

// ---------- parseVoiceBlock ----------

test('语音块：标准代码块提取 text', () => {
  const block = { type: 'code', code: '{"type":"bridge-voice","text":"你好"}' };
  assert.strictEqual(M.parseVoiceBlock(block), '你好');
});

test('语音块：段落里漂移成裸 JSON 也能提取', () => {
  const block = { type: 'paragraph', text: '说明 {"type":"bridge-voice","text":"hi"} 结尾' };
  assert.strictEqual(M.parseVoiceBlock(block), 'hi');
});

test('语音块：代码块内漂移的裸 JSON 也能提取', () => {
  const block = { type: 'code', code: '前缀 {"type":"bridge-voice","text":"hi"} 后缀' };
  assert.strictEqual(M.parseVoiceBlock(block), 'hi');
});

test('语音块：非语音块返回空串', () => {
  assert.strictEqual(M.parseVoiceBlock({ type: 'code', code: '{"a":1}' }), '');
  assert.strictEqual(M.parseVoiceBlock({ type: 'paragraph', text: '普通文字' }), '');
  assert.strictEqual(M.parseVoiceBlock(null), '');
});

test('语音块：多个语音块取第一个', () => {
  const text = '{"type":"bridge-voice","text":"first"} 与 {"type":"bridge-voice","text":"second"}';
  assert.strictEqual(M.parseVoiceBlock({ type: 'paragraph', text }), 'first');
});

test('语音块：嵌套大括号内文本正确配平', () => {
  const block = { type: 'paragraph', text: '{"type":"bridge-voice","text":"a{b}c"}' };
  assert.strictEqual(M.parseVoiceBlock(block), 'a{b}c');
});

// ---------- parseExternalCall ----------

test('外部信封：user 消息的代码块被识别', () => {
  const m = { role: 'user', blocks: [{ code: '{"type":"external-call","nonce":"n1","request":"r1"}' }] };
  assert.deepStrictEqual(M.parseExternalCall(m), { nonce: 'n1', request: 'r1' });
});

test('外部信封：assistant 消息不识别', () => {
  const m = { role: 'assistant', blocks: [{ code: '{"type":"external-call","nonce":"n","request":"r"}' }] };
  assert.strictEqual(M.parseExternalCall(m), null);
});

test('外部信封：text 块也能识别', () => {
  const m = { role: 'user', blocks: [{ text: '{"type":"external-call","nonce":"n","request":"r"}' }] };
  assert.deepStrictEqual(M.parseExternalCall(m), { nonce: 'n', request: 'r' });
});

test('外部信封：非信封返回 null', () => {
  assert.strictEqual(M.parseExternalCall({ role: 'user', blocks: [{ text: 'hi' }] }), null);
  assert.strictEqual(M.parseExternalCall(null), null);
});

test('外部信封：缺字段时回退空串', () => {
  const m = { role: 'user', blocks: [{ code: '{"type":"external-call"}' }] };
  assert.deepStrictEqual(M.parseExternalCall(m), { nonce: '', request: '' });
});

// ---------- msgSource ----------

test('消息来源：assistant 判为 assistant', () => {
  assert.strictEqual(M.msgSource({ role: 'assistant', blocks: [] }), 'assistant');
});

test('消息来源：含 bridge-chat-res 的 user 判为 tool', () => {
  assert.strictEqual(M.msgSource({ role: 'user', blocks: [{ code: 'bridge-chat-res' }] }), 'tool');
});

test('消息来源：普通 user 判为 user', () => {
  assert.strictEqual(M.msgSource({ role: 'user', blocks: [{ text: 'hi' }] }), 'user');
});

test('消息来源：空消息判为 user', () => {
  assert.strictEqual(M.msgSource(null), 'user');
  assert.strictEqual(M.msgSource({}), 'user');
});

test('消息来源：非 user/assistant 角色判为 user', () => {
  assert.strictEqual(M.msgSource({ role: 'system', blocks: [] }), 'user');
});

// ---------- toolSilent ----------

test('silent 判定：标记 silent 的工具返回真', () => {
  const ctx = { tools: [{ name: 'a', silent: true }, { name: 'b' }] };
  assert.strictEqual(M.toolSilent.call(ctx, 'a'), true);
  assert.strictEqual(M.toolSilent.call(ctx, 'b'), false);
});

test('silent 判定：未知工具返回假', () => {
  const ctx = { tools: [] };
  assert.strictEqual(M.toolSilent.call(ctx, 'x'), false);
});
