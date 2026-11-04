/* ============================================================
 * 刷新后卡片状态恢复测试
 *
 * 背景：
 *   已执行卡片在刷新页面后退回「待执行」。根因是时序——
 *   卡片建好之后签名库才从后端恢复，而建卡时查询签名库为空，
 *   于是卡片被建成待执行态，此后没有任何环节纠正它。
 *
 * 修复思路：
 *   会话加载完成时，遍历消息树里的卡片，按恢复好的签名库重新判定一次，
 *   把确实执行过的卡片改回已执行态。
 *
 * 本文件覆盖该重判逻辑：
 *   - 签名命中 → 卡片转为已执行
 *   - 签名未命中 → 卡片保持原状
 *   - 已执行的卡片不被重复处理
 *   - 签名库为空时不做任何改动
 *
 * 运行：node --test flask_server/tests/js/*.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// ---- 全局桩：必须在加载被测模块之前就位 ----
const dialog = { methods: {}, log: () => {} };
global.window = { AIMirrorDialog: dialog, AIMirrorDomUtils: { toArray: (v) => (Array.isArray(v) ? v : []) } };

// 加载被测模块：签名存取与卡片重判在 05j，建卡逻辑在 05g
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05j_card_sig.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05g_cards.js'));

const M = dialog.methods;

/**
 * 造一个最小会话：一条消息，挂一张工具卡。
 *
 * @param {Object} cardOverrides 覆盖卡片字段
 * @returns {Object} 会话对象
 */
function makeConv(cardOverrides) {
  const card = Object.assign({
    id: 'block-1',
    isTool: true,
    tool: 'read_file',
    parameters: { path: 'a.txt' },
    msgId: 'msg-1',
    executed: false,
    status: 'pending'
  }, cardOverrides || {});
  return {
    title: 't',
    msgTree: {
      'msg-1': { id: 'msg-1', role: 'assistant', cards: { 'block-1': card } }
    },
    executedSigs: {}
  };
}

/**
 * 组装一个只够跑重判逻辑的上下文。
 *
 * @param {Object} conv 会话
 * @returns {Object} 带 activeConv 与 ensureConv 的最小 this
 */
function makeCtx(conv) {
  return {
    activeConv: 'conv-1',
    ensureConv: () => conv
  };
}

test('签名命中：卡片被恢复为已执行', () => {
  const conv = makeConv();
  // 签名库里有这条调用，格式与 _markExecutedSig 一致
  conv.executedSigs['conv-1|msg-1|read_file|{"path":"a.txt"}'] = true;
  M._restoreExecutedCards.call(makeCtx(conv), conv);
  const card = conv.msgTree['msg-1'].cards['block-1'];
  assert.strictEqual(card.executed, true);
  assert.strictEqual(card.status, 'done');
  // 标记来源，便于排查
  assert.strictEqual(card.restoredFromSig, true);
});

test('签名未命中：卡片保持待执行', () => {
  const conv = makeConv();
  // 签名库里是别的一条调用
  conv.executedSigs['conv-1|msg-9|other_tool|{}'] = true;
  M._restoreExecutedCards.call(makeCtx(conv), conv);
  const card = conv.msgTree['msg-1'].cards['block-1'];
  assert.strictEqual(card.executed, false);
  assert.strictEqual(card.status, 'pending');
});

test('已执行的卡片不被重复处理', () => {
  const conv = makeConv({ executed: true, status: 'done' });
  conv.executedSigs['conv-1|msg-1|read_file|{"path":"a.txt"}'] = true;
  M._restoreExecutedCards.call(makeCtx(conv), conv);
  const card = conv.msgTree['msg-1'].cards['block-1'];
  // 保持已执行，且不打上恢复标记（它本来就不是恢复来的）
  assert.strictEqual(card.executed, true);
  assert.notStrictEqual(card.restoredFromSig, true);
});

test('签名库为空：不做任何改动', () => {
  const conv = makeConv();
  M._restoreExecutedCards.call(makeCtx(conv), conv);
  const card = conv.msgTree['msg-1'].cards['block-1'];
  assert.strictEqual(card.executed, false);
});

test('非工具卡片不被改动', () => {
  const conv = makeConv({ isTool: false, tool: '', status: 'idle' });
  conv.executedSigs['conv-1|msg-1||{}'] = true;
  M._restoreExecutedCards.call(makeCtx(conv), conv);
  const card = conv.msgTree['msg-1'].cards['block-1'];
  assert.notStrictEqual(card.executed, true);
});

test('遍历多张卡片：只恢复命中的那些', () => {
  const conv = {
    title: 't',
    msgTree: {
      'msg-1': { id: 'msg-1', cards: {
        'b1': { id: 'b1', isTool: true, tool: 'read_file', parameters: { p: '1' }, msgId: 'msg-1', executed: false, status: 'pending' },
        'b2': { id: 'b2', isTool: true, tool: 'read_file', parameters: { p: '2' }, msgId: 'msg-1', executed: false, status: 'pending' }
      } }
    },
    executedSigs: { 'conv-1|msg-1|read_file|{"p":"2"}': true }
  };
  M._restoreExecutedCards.call(makeCtx(conv), conv);
  const cards = conv.msgTree['msg-1'].cards;
  // 只有 b2 命中
  assert.strictEqual(cards.b1.executed, false);
  assert.strictEqual(cards.b2.executed, true);
});
