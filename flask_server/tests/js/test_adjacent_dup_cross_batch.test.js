/* ============================================================
 * 相邻消息去重（跨上报批次）测试
 *
 * 背景（实机日志 2026-11-07 07:41 实证）：
 *   网页把同一次工具调用拆进两个上报批次：
 *     批次一 … mlqspnt, m1askbw5   （卡 c1kaujgl）
 *     批次二 m1askbw5, m1jf46w4, m13lwpcw（卡 custhyw）
 *   两处参数完全相同、msgId 不同。原实现的比对基准是
 *   「本批切片内的前一条」，而重复调用恰是第二批首条，
 *   切片内没有前一条 → 比对基准为空 → 去重落空 → 两张卡各执行一次。
 *
 * 修法：比对基准改从「消息树里的前一条」取（树边「父id-子id」
 * 天然记录相邻关系，跨批次也能对上）。
 *
 * 本文件直接驱动 _prevCardsInTree 验证该取值正确，
 * 并覆盖无前驱、父为根、消息不在树中三种边界。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const fx = require('./_dialog_fixture');

/**
 * 取跑完脚本后的方法表。
 *
 * @returns {Object} D.methods
 */
function methods() {
  const { sandbox, errors } = fx.bootDialog();
  assert.deepStrictEqual(errors.map((e) => e.file), [],
    '抽屉脚本应全部加载成功，失败项：' + JSON.stringify(errors.map((e) => e.file)));
  const D = sandbox.window.AIMirrorDialog;
  assert.ok(D && D.methods, '应挂载 AIMirrorDialog.methods');
  return D.methods;
}

/**
 * 构造一条最小消息对象，并返回它的真实指纹。
 *
 * msgId 复用 messageFingerprint（按内容算），不读 m.id，
 * 因此树键必须由指纹拼出，自造 id 字段对不上任何树键。
 *
 * @param {Object} M 方法表（提供 msgId）
 * @param {string} body 消息正文，用于区分不同消息
 * @param {Object} [cards] 卡片表
 * @returns {{ m: Object, id: string }} 消息对象与其指纹
 */
function msg(M, body, cards) {
  const m = { role: 'assistant', blocks: [{ type: 'text', text: body }], cards: cards || {} };
  return { m: m, id: M.msgId(m) };
}

test('跨批次去重：前一条在树中但不在本批切片里，仍能取到其卡片表', () => {
  const M = methods();
  // 树：根 → a → b → c，其中 c 属第二批，a 属第一批
  const a = msg(M, 'a', { blk1: { isTool: true, tool: 'run_command' } });
  const b = msg(M, 'b');
  const c = msg(M, 'c');
  const conv = { msgTree: { ['0-' + a.id]: a.m, [a.id + '-' + b.id]: b.m, [b.id + '-' + c.id]: c.m } };
  // c 的前一条是 b，b 无卡片 → 取到的是空表而非 null
  assert.deepStrictEqual(M._prevCardsInTree(conv, c.m), {});
  // b 的前一条是 a，其卡片表应原样取回（这正是跨批次能比对的依据）
  assert.strictEqual(M._prevCardsInTree(conv, b.m), a.m.cards);
});

test('父为根时返回 null：会话首条没有可比对的前一条', () => {
  const M = methods();
  const first = msg(M, 'first', { blk: {} });
  const conv = { msgTree: { ['0-' + first.id]: first.m } };
  assert.strictEqual(M._prevCardsInTree(conv, first.m), null);
});

test('消息不在树中时返回 null：调用方回退到原逻辑，不比现状更差', () => {
  const M = methods();
  const ghost = msg(M, 'ghost');
  const conv = { msgTree: {} };
  assert.strictEqual(M._prevCardsInTree(conv, ghost.m), null);
});

test('前驱节点没有卡片字段时返回 null：不误判为「前一条有卡片」', () => {
  const M = methods();
  // 前驱故意不带 cards 字段：keyOfId 只按指纹找键，指纹由内容决定
  const prev = { role: 'assistant', blocks: [{ type: 'text', text: 'p' }] };
  const prevId = M.msgId(prev);
  const cur = msg(M, 'c');
  const conv = { msgTree: { ['0-' + prevId]: prev, [prevId + '-' + cur.id]: cur.m } };
  assert.strictEqual(M._prevCardsInTree(conv, cur.m), null);
});

test('入参缺失时安全返回 null：不抛异常', () => {
  const M = methods();
  assert.strictEqual(M._prevCardsInTree(null, msg(M, 'x').m), null);
  assert.strictEqual(M._prevCardsInTree({ msgTree: {} }, null), null);
});

test('树键按第一个分隔符切分：父 id 取到的是完整消息指纹', () => {
  const M = methods();
  const prev = msg(M, 'prev', { blk: { isTool: true } });
  const cur = msg(M, 'cur');
  const conv = { msgTree: { [prev.id + '-' + cur.id]: cur.m, ['0-' + prev.id]: prev.m } };
  assert.strictEqual(M._prevCardsInTree(conv, cur.m), prev.m.cards);
});
