/* ============================================================
 * 清空会话时执行签名库必须一起清空
 *
 * 背景：
 *   执行签名库（executedSigs）是卡片「已执行」状态的唯一依据。
 *   它挂在会话对象上，却不在清空会话的清理范围内——
 *   清空后重新解析，新卡片凭旧签名被判成「已执行」，
 *   表现为「记录清空了、卡片状态还在」。
 *
 *   更隐蔽的一层：清空后会把内存会话写回后端（_persist），
 *   残留的签名被原样写回，等于把刚删掉的行重建出来。
 *
 * 本文件锁住两条清理路径都必须清掉签名库。
 *
 * 运行：node --test flask_server/tests/js/test_clear_sessions_sig.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const dialog = require('./_part_stub').installStub();
// 清空逻辑用到 messageFingerprint → 公共库，用生产实现不造假货
require(path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '04_sessions.js'));
// clearSession 定义在 04b，与 04 分属两个文件
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '04b_sessions.js'));

const M = dialog.methods;

/**
 * 造一个带签名库与消息的会话对象。
 *
 * @returns {Object} 会话
 */
function makeConv() {
  return {
    title: 't',
    page_url: 'http://x',
    msgTree: { 'k-m1': { id: 'm1', role: 'assistant', blocks: [], cards: { b1: { isTool: true } } } },
    visibleKeys: ['k-m1'],
    branchKeys: ['k-m1'],
    externalCards: [{ id: 'ec1' }],
    orphanSlice: [{ id: 'o1' }],
    // 关键：签名库里有一条已执行记录
    executedSigs: { 'c1|m1|read_file|{}': true },
    updatedAt: 0
  };
}

test('清空当前会话：签名库一并清空', () => {
  // 这是本 bug 的核心：只清消息树、不清签名库，状态就会残留
  const conv = makeConv();
  const ctx = {
    activeConv: 'c1',
    curConv: conv,
    entryChecked: { a: true },
    entryOpen: { b: true },
    eachCard: M.eachCard,
    _persist: null,
    toast: () => {},
  };
  // 跳过确认弹窗：测试环境没有 confirm
  global.confirm = () => true;
  M.clearSession.call(ctx);
  assert.deepStrictEqual(conv.executedSigs, {}, '签名库应为空对象');
  assert.deepStrictEqual(conv.msgTree, {}, '消息树应被清空');
  assert.deepStrictEqual(conv.externalCards, [], '外部卡片应被清空');
});

test('清空当前会话：签名库被替换为新对象而非残留引用', () => {
  // 直接置空原对象也行，但替换成新对象更稳妥：
  // 若有其它地方持有旧引用，改写旧对象会让它们看到清空后的状态
  const conv = makeConv();
  const oldSigs = conv.executedSigs;
  const ctx = {
    activeConv: 'c1',
    curConv: conv,
    entryChecked: {},
    entryOpen: {},
    eachCard: M.eachCard,
    _persist: null,
    toast: () => {},
  };
  global.confirm = () => true;
  M.clearSession.call(ctx);
  assert.notStrictEqual(conv.executedSigs, oldSigs, '应换成新对象');
});

// C-7 P2 [clear_sig]：原件新增标准 tool_call.id / tool 消息入口断言基准。
// 旧链断言逐条保留（运行时执行权仍在旧直调路径），活链保持、旧标记不摘。
// 唯一键断言由 _c7_standard_entry 统一提供，平行夹具保留作补充。
require('node:test')(
  'C-7 标准入口基准 [clear_sig]',
  () => require('./_c7_standard_entry').run(require('node:assert/strict'), 'clear_sig')
);
