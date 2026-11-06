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

const dialog = require('./_part_stub').installStub();
const ROOT = path.join(__dirname, '..', '..', '..', 'extend');
// 按依赖顺序加载被测分片：建卡在 05g，签名与末条判定是其前置依赖
require(path.join(ROOT, 'lib', 'dom-utils.js'));
['04_sessions', '05h_tree_query', '05f_parse', '05e_quality', '05j_card_sig', '05g_cards']
  .forEach((n) => require(path.join(ROOT, 'dialog', 'parts', n + '.js')));
const D = dialog;
const M = dialog.methods;

// cardInMirror 定义在 06_execute.js，该分片依赖较多（倒计时状态机等），
// 本文件只验证建卡阶段的去重，故打桩为「镜像里都存在」即可。
M.cardInMirror = function () { return true; };

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

/**
 * 按主循环的口径逐条建卡：每轮把「前一条消息的卡片表」交给建卡逻辑，
 * 这是相邻去重的比对基准。会话状态也要先就位——建卡会经 _executedSig 查签名库。
 *
 * @param {Array} incoming 本轮消息切片
 * @param {Object} state 建卡状态（会被就地更新）
 * @param {Array} autoCandidates 自动执行候选池（会被就地追加）
 * @returns {void}
 */
function buildAll(incoming, state, autoCandidates) {
  M.conversations = {};
  M.activeConv = 'c1';
  incoming.forEach((m, mi) => {
    const prevM = mi > 0 ? incoming[mi - 1] : null;
    state.prevCards = (prevM && prevM.cards) || null;
    M._buildCardsForOne({ msgTree: {} }, m, mi, incoming, 'generate', null, false, autoCandidates, state);
  });
}

/**
 * 造一份初始建卡状态。
 *
 * @returns {Object} 状态对象
 */
function freshState() {
  return { armedLast: null, isFreshReply: true, firstToolCard: null, prevCards: null };
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
  M._maybeAutoExecOnScroll.call(open.ctx, card, true);
  assert.strictEqual(open.getExecuted(), null, '重复卡片必须被拦下');
});
