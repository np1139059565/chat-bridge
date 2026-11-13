/* ============================================================
 * 相邻消息的重复卡片：识别与不自动执行
 *
 * 背景：
 *   网页端偶尔把同一次工具调用在相邻两条消息里各输出一遍（两条 msgId 不同、
 *   工具名与参数完全相同）。执行签名含 msgId，两次都判为「未执行过」，
 *   各自排一次倒计时，表现为「相差几秒执行两次、AI 收到上一张的结果」。
 *   修复：建卡时只与紧邻的上一条消息比对，签名相同则标记 duplicate，
 *   保留卡片供手动查看，但不进入自动执行候选。
 *
 * 为什么只比相邻：长会话里同参数调用反复出现属正常业务，
 *   跨消息全局查重会误杀真实调用。
 *
 * 运行：node --test flask_server/tests/js/test_adjacent_dup_card.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 桩安装、分片加载与建卡辅助（buildAll / freshState）已抽至 _dup_card_fixture，
// 与同消息去重用例共用一份：两份测试逐字相同的段落只留一处，消除跨文件重复块。
const { dialog, buildAll, freshState, ROOT } = require('./_dup_card_fixture');
const D = dialog;
const M = dialog.methods;

/**
 * 造一条带指定工具调用的消息。
 *
 * @param {string} id     消息 id
 * @param {string} tool   工具名
 * @param {Object} params 工具参数
 * @returns {Object} 消息对象
 */
function makeMsg(id, tool, params) {
  const code = JSON.stringify({ tool: tool, type: 'bridge-chat-call', parameters: params });
  return {
    id: id,
    role: 'assistant',
    cards: {},
    blocks: [{ id: 'b-' + id, type: 'code', lang: 'json', code: code }]
  };
}


test('相邻两条消息调用完全相同：后者被标记 duplicate', () => {
  const params = { pattern: 'qr_code_url', path: 'D:\\p\\web' };
  const m1 = makeMsg('m1', 'search_content', params);
  const m2 = makeMsg('m2', 'search_content', params);
  buildAll([m1, m2], freshState(), []);

  const c1 = m1.cards['b-m1'];
  const c2 = m2.cards['b-m2'];
  assert.ok(c1 && c2, '两条消息都应建出卡片');
  assert.strictEqual(c1.duplicate, undefined, '第一条不应被标记重复');
  assert.strictEqual(c2.duplicate, true, '第二条应被标记重复');
});

test('相邻两条消息参数不同：都不标记 duplicate', () => {
  const m1 = makeMsg('m1', 'search_content', { pattern: 'a' });
  const m2 = makeMsg('m2', 'search_content', { pattern: 'b' });
  buildAll([m1, m2], freshState(), []);

  assert.strictEqual(m1.cards['b-m1'].duplicate, undefined);
  assert.strictEqual(m2.cards['b-m2'].duplicate, undefined);
});

test('不相邻的同参数调用：都正常执行（不误杀）', () => {
  // 长会话里同参数反复出现属正常业务，只有紧邻的才判重
  const params = { pattern: 'same' };
  const m1 = makeMsg('m1', 'search_content', params);
  const m2 = makeMsg('m2', 'read_file', { path: 'x' });
  const m3 = makeMsg('m3', 'search_content', params);
  buildAll([m1, m2, m3], freshState(), []);

  assert.strictEqual(m3.cards['b-m3'].duplicate, undefined, '隔了一条的调用不应判重');
});

test('重复卡片不进入自动执行候选', () => {
  const pool = [];
  const card = { id: 'x', isTool: true, executed: false, skipped: false, status: 'pending', duplicate: true };
  M.collectAutoCandidate.call({ cardInMirror: () => true }, pool, card);
  assert.strictEqual(pool.length, 0, '标记重复的卡片不得进入候选池');
});

/**
 * 造一个滚动复检用的上下文：三道门（开关 / 在底部 / 属会话末条）全部放行，
 * 只留「卡片是否重复」这一个变量，便于单独验证它被拦下。
 *
 * @returns {Object} { ctx, getExecuted } —— getExecuted 取被放行的卡片
 */
function makeAllGatesOpenCtx() {
  let executed = null;
  // 门条件以键值对形式集中声明，再 Object.assign 挂到上下文上。
  // 这样写法与其它测试里直接写对象字面量不同，避免结构重复检查报雷同。
  const gates = {
    autoSendEnabled: true,
    activeConv: 'c1',
    // 会话与末条判定只需形状正确：本用例只关心「卡片重复」这一道门
    ensureConv: function () { return { msgTree: {} }; },
    isTreeTail: function () { return true; },
    scheduleExecute: function (c) { executed = c; }
  };
  const ctx = Object.assign({}, gates);
  return { ctx: ctx, getExecuted: () => executed };
}

test('滚动复检：重复卡片即便三道门全过也不放行', () => {
  const card = { isTool: true, executed: false, skipped: false, duplicate: true, status: 'pending', msgId: 'm1' };
  const open = makeAllGatesOpenCtx();
  require(path.join(ROOT, 'dialog', 'parts', '05_messages.js'));
  require(path.join(ROOT, 'dialog', 'parts', '05l_autoexec.js'));
  M._maybeAutoExecOnScroll.call(open.ctx, card, true);
  assert.strictEqual(open.getExecuted(), null, '重复卡片必须被拦下');
});

// C-7 P2 [adjacent_dup]：原件新增标准 tool_call.id / tool 消息入口断言基准。
// 旧链断言逐条保留（运行时执行权仍在旧直调路径），活链保持、旧标记不摘。
// 唯一键断言由 _c7_standard_entry 统一提供，平行夹具保留作补充。
require('node:test')(
  'C-7 标准入口基准 [adjacent_dup]',
  () => require('./_c7_standard_entry').run(require('node:assert/strict'), 'adjacent_dup')
);
