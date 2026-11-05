/* ============================================================
 * 滚动轮次的自动执行：上膛与复检
 *
 * 背景：
 *   滚动分支曾用「末位 + isFreshReply」判定上膛，但 isFreshReply 的定义里
 *   含 !scrollOnly——两者互斥，分支永远进不去，成为死代码。
 *   表现为末条卡片明明在待执行态、开关也开着、视口也在底部，却从不执行。
 *   本文件锁住修复后的行为：滚动轮次只按末位发预备标记，
 *   是否真执行由复检的三道门（开关 / 在底部 / 属于会话末条）决定。
 *
 * 运行：node --test flask_server/tests/js/test_scroll_autoexec.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

const dialog = require('./_part_stub').installStub();
// 加载被测分片：建卡与复检都定义在 05g_cards；末条判定依赖 05h_tree_query
// 消息指纹链：msgId → messageFingerprint → 公共库；用生产实现，不造假货
require(path.join(__dirname, '..', '..', '..', 'extend', 'lib', 'dom-utils.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '04_sessions.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05h_tree_query.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05f_parse.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05j_card_sig.js'));
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05g_cards.js'));
// _maybeAutoExecOnScroll 定义在消息主文件，复检用例需要它
require(path.join(__dirname, '..', '..', '..', 'extend', 'dialog', 'parts', '05_messages.js'));
const D = dialog;
const M = dialog.methods;

/**
 * 造一条消息，带一个可执行代码块。
 *
 * @param {string} id    消息 id
 * @param {string} role  角色
 * @returns {Object} 消息对象
 */
function makeMsg(id, role) {
  return {
    id: id,
    role: role,
    // 代码块须是合法的工具调用：带 tool 与 type=bridge-chat-call，否则不会建卡
    blocks: [{ id: 'b-' + id, type: 'code', lang: 'json', code: '{"tool":"read_file","type":"bridge-chat-call","parameters":{}}' }]
  };
}

/**
 * 造一张待执行的工具卡片，挂在给定 holder 上。
 *
 * @param {Object} holder 承载卡片的对象
 * @param {string} blockId 代码块 id
 * @returns {Object} 卡片
 */
function makeCard(holder, blockId) {
  holder.cards = holder.cards || {};
  holder.cards[blockId] = {
    id: blockId,
    isTool: true,
    executed: false,
    skipped: false,
    status: 'pending',
    msgId: 'm1'
  };
  return holder.cards[blockId];
}

test('滚动轮次：末条消息上的卡片会被上膛', () => {
  // 这是修复的核心：滚动时不再要求 isFreshReply，末位卡片就该拿到预备标记
  const state = { armedLast: null, isFreshReply: false, firstToolCard: null };
  const msg = makeMsg('m1', 'assistant');
  // 卡片容器由上层 _buildCardsForOne 初始化，直接调 _buildCardForBlock 时须自行补上
  msg.cards = {};
  // 建卡流程会经 _executedSig 查执行签名，进而调用 ensureConv 取会话；
  // 直接调下层函数时这些上层状态也须就位。
  M.conversations = {};
  M.activeConv = 'c1';
  const autoCandidates = [];
  // 不预置卡片：交给真实建卡函数创建，才能走到「新卡片」分支（预置会命中已存在分支）
  M._buildCardForBlock(msg, msg, msg.blocks[0], 0, [msg], 'scroll', true, null, autoCandidates, state);
  assert.ok(state.armedLast, '末条卡片应被上膛');
  assert.strictEqual(state.armedLast.autoArmed, true, '卡片应带预备标记');
});

test('滚动轮次：非末位消息上的卡片不上膛', () => {
  // 向上滚动加载历史时，切片末位可能是旧消息；只认真正末位
  const state = { armedLast: null, isFreshReply: false, firstToolCard: null };
  const m1 = makeMsg('m1', 'assistant');
  const m2 = makeMsg('m2', 'assistant');
  makeCard(m1, 'b-m1');
  makeCard(m2, 'b-m2');
  const incoming = [m1, m2];
  const autoCandidates = [];
  // 处理第一条（非末位）
  M._buildCardForBlock(m1, m1, m1.blocks[0], 0, incoming, 'scroll', true, null, autoCandidates, state);
  assert.strictEqual(state.armedLast, null, '非末位不应上膛');
});

test('复检：三道门全过时放行执行', () => {
  const card = { isTool: true, executed: false, skipped: false, status: 'pending', msgId: 'm1' };
  let executed = null;
  const ctx = {
    autoSendEnabled: true,
    activeConv: 'c1',
    ensureConv: () => ({ msgTree: { 'k-m1': { id: 'm1' } } }),
    isTreeTail: () => true,
    scheduleExecute: (c) => { executed = c; }
  };
  M._maybeAutoExecOnScroll.call(ctx, card, true);
  assert.strictEqual(executed, card, '三道门全过应放行');
});

test('复检：视口不在底部时不放行', () => {
  // 防止用户正在往上翻看历史时，新卡片突然被执行
  const card = { isTool: true, executed: false, skipped: false, status: 'pending', msgId: 'm1' };
  let executed = null;
  const ctx = {
    autoSendEnabled: true,
    activeConv: 'c1',
    ensureConv: () => ({ msgTree: { 'k-m1': { id: 'm1' } } }),
    isTreeTail: () => true,
    scheduleExecute: (c) => { executed = c; }
  };
  M._maybeAutoExecOnScroll.call(ctx, card, false);
  assert.strictEqual(executed, null, '不在底部不应放行');
});

test('复检：卡片不属于会话末条时拒绝执行', () => {
  // 这是「向上滚动加载历史」的兜底：历史卡片即便被上膛也要被拦下
  const card = { isTool: true, executed: false, skipped: false, status: 'pending', msgId: 'old' };
  let executed = null;
  const ctx = {
    autoSendEnabled: true,
    activeConv: 'c1',
    ensureConv: () => ({ msgTree: { 'k-m1': { id: 'm1' } } }),
    isTreeTail: () => false,
    scheduleExecute: (c) => { executed = c; }
  };
  M._maybeAutoExecOnScroll.call(ctx, card, true);
  assert.strictEqual(executed, null, '非末条卡片必须拒绝');
});

test('复检：自动开关关闭时不放行', () => {
  const card = { isTool: true, executed: false, skipped: false, status: 'pending', msgId: 'm1' };
  let executed = null;
  const ctx = {
    autoSendEnabled: false,
    activeConv: 'c1',
    ensureConv: () => ({ msgTree: { 'k-m1': { id: 'm1' } } }),
    isTreeTail: () => true,
    scheduleExecute: (c) => { executed = c; }
  };
  M._maybeAutoExecOnScroll.call(ctx, card, true);
  assert.strictEqual(executed, null, '开关关闭不应放行');
});
