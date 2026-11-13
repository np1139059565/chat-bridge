/* ============================================================
 * 卡片构造行为测试
 *
 * 背景：
 *   extend/dialog/parts/ 下的业务逻辑此前只有「语法没错、方法还在」
 *   这一层安全网（test_dialog_boot / test_dialog_contracts 验证的是
 *   脚本能否跑完、方法是否挂上），字段漏一个、参数副本没存、
 *   告警挂错位置都不会报错。本文件补上「卡片字段构造是否正确」
 *   这一类的行为断言。
 *
 * 覆盖点：
 *   1. 工具卡片的字段完整性（id / lang / code / isTool / tool）
 *   2. 参数双份保存：parameters 供执行，origParameters 供一键还原
 *   3. origParameters 是深拷贝：改 parameters 不能污染它
 *   4. 用户可编辑文本与执行参数分离（paramsText / paramsError）
 *   5. noReply 只在显式声明 true 时成立
 *   6. preIssue 只挂在工具卡片上，非工具块不挂
 *
 * 运行：node --test flask_server/tests/js/*.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// ---- 全局桩：必须在加载被测模块之前就位（公共实现见 _part_stub）----
const dialog = require('./_part_stub').installStub();

// 加载被测模块：建卡逻辑在 05g；_makeCard 内部要用 toolSilent，它在 05f
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05f_parse.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05g_cards.js'));

const M = dialog.methods;

/**
 * 造一个工具调用块。
 *
 * @param {Object} [callOverrides] 覆盖解析出的调用字段
 * @returns {Object} 代码块对象
 */
function makeToolBlock(callOverrides) {
  const call = Object.assign({
    tool: 'read_file',
    parameters: { path: 'a.txt', limit: 10 }
  }, callOverrides || {});
  return {
    id: 'block-1',
    type: 'code',
    lang: 'json',
    code: JSON.stringify({ type: 'bridge-chat-call' }),
    _call: call
  };
}

/**
 * 造一个普通代码块（非工具调用）。
 *
 * @returns {Object} 代码块对象
 */
function makePlainBlock() {
  return { id: 'block-2', type: 'code', lang: 'js', code: 'console.log(1)' };
}

test('工具卡片：核心字段按块与调用填入', () => {
  const b = makeToolBlock();
  const card = M._makeCard(b, b._call, null);
  assert.strictEqual(card.id, 'block-1');
  assert.strictEqual(card.lang, 'json');
  assert.strictEqual(card.code, b.code);
  assert.strictEqual(card.isTool, true);
  assert.strictEqual(card.tool, 'read_file');
  assert.deepStrictEqual(card.parameters, { path: 'a.txt', limit: 10 });
});

test('工具卡片：初始状态是待执行', () => {
  const b = makeToolBlock();
  const card = M._makeCard(b, b._call, null);
  assert.strictEqual(card.status, 'pending');
  assert.strictEqual(card.executed, false);
  assert.strictEqual(card.result, null);
  assert.strictEqual(card.error, null);
  assert.strictEqual(card.finishedAt, null);
});

test('工具卡片：origParameters 是深拷贝，改 parameters 不污染它', () => {
  const b = makeToolBlock();
  const card = M._makeCard(b, b._call, null);
  assert.deepStrictEqual(card.origParameters, { path: 'a.txt', limit: 10 });
  // 模拟用户编辑参数
  card.parameters.path = 'changed.txt';
  // 还原用的副本必须还是原值
  assert.strictEqual(card.origParameters.path, 'a.txt');
});

test('工具卡片：paramsText 是格式化后的 JSON 文本', () => {
  const b = makeToolBlock();
  const card = M._makeCard(b, b._call, null);
  assert.strictEqual(typeof card.paramsText, 'string');
  // 能被解析回原参数
  assert.deepStrictEqual(JSON.parse(card.paramsText), { path: 'a.txt', limit: 10 });
  assert.strictEqual(card.paramsError, '');
});

test('工具卡片：未声明 no_reply 时 noReply 为假', () => {
  const b = makeToolBlock();
  const card = M._makeCard(b, b._call, null);
  assert.strictEqual(card.noReply, false);
});

test('工具卡片：显式声明 no_reply 为 true 时 noReply 为真', () => {
  const b = makeToolBlock({ parameters: { no_reply: true } });
  const card = M._makeCard(b, b._call, null);
  assert.strictEqual(card.noReply, true);
});

test('工具卡片：no_reply 为字符串时不误判为真', () => {
  // 严格等于 true 才算，避免 "false" 这类字符串把回传关掉
  const b = makeToolBlock({ parameters: { no_reply: 'true' } });
  const card = M._makeCard(b, b._call, null);
  assert.strictEqual(card.noReply, false);
});

test('工具卡片：致命告警挂在 preIssue 上', () => {
  const b = makeToolBlock();
  const issue = { error: 'multiple_tool_calls', severity: 'fatal' };
  const card = M._makeCard(b, b._call, issue);
  assert.deepStrictEqual(card.preIssue, issue);
});

test('普通代码块：isTool 为假，不挂 preIssue', () => {
  const b = makePlainBlock();
  const issue = { error: 'x', severity: 'fatal' };
  const card = M._makeCard(b, null, issue);
  assert.strictEqual(card.isTool, false);
  assert.strictEqual(card.tool, '');
  assert.deepStrictEqual(card.parameters, {});
  assert.strictEqual(card.paramsText, '');
  // 非工具块不该承载工具类致命告警
  assert.strictEqual(card.preIssue, null);
});

test('普通代码块：origParameters 为空对象而非 null', () => {
  const b = makePlainBlock();
  const card = M._makeCard(b, null, null);
  // 空对象便于调用方直接展开，不必判空
  assert.deepStrictEqual(card.origParameters, {});
});

// C-7 P2 [card_build]：原件新增标准 tool_call.id / tool 消息入口断言基准。
// 旧链断言逐条保留（运行时执行权仍在旧直调路径），活链保持、旧标记不摘。
// 唯一键断言由 _c7_standard_entry 统一提供，平行夹具保留作补充。
require('node:test')(
  'C-7 标准入口基准 [card_build]',
  () => require('./_c7_standard_entry').run(require('node:assert/strict'), 'card_build')
);
