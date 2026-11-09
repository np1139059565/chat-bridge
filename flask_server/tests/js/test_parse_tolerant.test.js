/* ============================================================
 * 代码块文本被站点装饰污染时的工具调用识别测试
 *
 * 覆盖 extend/dialog/parts/05f_parse.js 的容错解析：
 *   - 工具条把语言标签（json）与复制按钮文案混进代码文本
 *   - 代码块左侧渲染行号栏
 *   - 文本里夹带零宽字符
 * 这些污染都会让整段 JSON 直接解析失败，卡片退化成普通代码块。
 *
 * 运行方式：node --test flask_server/tests/js/
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const { installStub } = require('./_part_stub.js');

// 公共桩：立起 window.AIMirrorDialog 后再加载被测分片
const dialog = installStub();
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05f_parse.js'));
const M = dialog.methods;

// 标准工具调用信封
const CALL = { tool: 'list_rules', type: 'bridge-chat-call', parameters: {} };
const WANT = { tool: 'list_rules', parameters: {} };

/**
 * 构造代码块对象。
 * @param {string} code 代码文本
 * @returns {Object} 代码块
 */
function block(code) {
  return { type: 'code', lang: 'json', code: code };
}

test('语言标签混在首行时仍识别', () => {
  const code = 'json\n' + JSON.stringify(CALL, null, 2);
  assert.deepStrictEqual(M.parseToolCall(block(code)), WANT);
});

test('复制按钮文案混在末行时仍识别', () => {
  const code = JSON.stringify(CALL, null, 2) + '\n复制代码';
  assert.deepStrictEqual(M.parseToolCall(block(code)), WANT);
});

test('语言标签与复制文案同时存在时仍识别', () => {
  const code = 'json\n' + JSON.stringify(CALL, null, 2) + '\n复制代码';
  assert.deepStrictEqual(M.parseToolCall(block(code)), WANT);
});

test('左侧行号栏混入时仍识别', () => {
  const lines = JSON.stringify(CALL, null, 2).split('\n');
  const code = lines.map((l, i) => (i + 1) + ' ' + l).join('\n');
  assert.deepStrictEqual(M.parseToolCall(block(code)), WANT);
});

test('零宽字符夹在结构里时仍识别', () => {
  const code = '\u200b' + JSON.stringify(CALL, null, 2) + '\ufeff';
  assert.deepStrictEqual(M.parseToolCall(block(code)), WANT);
});

test('前置说明文字后跟 JSON 时仍识别', () => {
  const code = '工具调用如下：\n' + JSON.stringify(CALL, null, 2);
  assert.deepStrictEqual(M.parseToolCall(block(code)), WANT);
});

test('普通代码块不误判为工具调用', () => {
  assert.strictEqual(M.parseToolCall(block('const a = 1;\nconsole.log(a);')), null);
});

test('普通 JSON 代码块不误判为工具调用', () => {
  assert.strictEqual(M.parseToolCall(block('{\n  "name": "张三"\n}')), null);
});

test('行号栏判定从严：行号不连续时按原文处理', () => {
  assert.strictEqual(M._stripLineNumbers('1 {"a": 1}\n3 {"b": 2}'), '1 {"a": 1}\n3 {"b": 2}');
});

test('行号独占一行且夹空行时仍识别（千问实测形态）', () => {
  const code = '1\n{\n\n2\n  "tool": "list_rules",\n\n3\n  "type": "bridge-chat-call",\n\n4\n  "parameters": {}\n\n5\n}';
  assert.deepStrictEqual(M.parseToolCall(block(code)), WANT);
});

test('行号独占一行：纯数字行被剥离，内容行保留', () => {
  assert.strictEqual(M._stripNumberLines('1\n{\n\n2\n}\n'), '{\n\n}\n');
});

test('JSON 里独立成行的数字不被误删', () => {
  const src = '{\n  "a": [\n    1,\n    2\n  ]\n}';
  assert.strictEqual(M._stripNumberLines(src), src);
});
