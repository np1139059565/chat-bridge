/* ============================================================
 * 命中边不连续时不得丢弃尾部新消息（抽屉「切片命中多处」问题）
 *
 * 背景：msgId = messageFingerprint，按「角色 + 名称 + 块内容」算，
 * 相同内容的两条消息指纹相同（04_sessions.js 已注明不能当唯一序号键）。
 * 网页把同一段内容重复输出时，切片里会出现重复的「父-子」边，
 * upsertTree 收集的 matched 下标因此看似「不连续」。旧实现一律判
 * collision、清空 orphanSlice、整片不入树 —— 尾部真正的新回复被一起
 * 丢掉，抽屉消息列表停在旧内容，弹「切片命中多处，已跳过本次入库」。
 *
 * 期望：以切片里最后一个已在树的节点为锚，只补其后的新节点；
 * 已有边不覆盖、不把历史接到树末端；无新增时不往树里乱加节点。
 *
 * 运行：node --test flask_server/tests/js/test_tree_collision_append.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const fx = require('./_dialog_fixture');

/** 按 dialog.html 的真实顺序加载抽屉脚本，返回方法表。 */
function loadMethods() {
  const booted = fx.bootDialog();
  const bad = booted.errors.map((e) => e.file);
  if (bad.length) throw new Error('抽屉脚本加载失败：' + JSON.stringify(bad));
  return booted.sandbox.window.AIMirrorDialog.methods;
}

/** 造一条最小消息，返回消息对象与它的真实内容指纹。 */
function entry(M, body) {
  const m = { role: 'assistant', blocks: [{ type: 'text', text: body }] };
  return { node: m, fp: M.msgId(m) };
}

/** 造一个最小会话记录，只带 upsertTree 会触碰的字段。 */
function blankConv() {
  return { msgTree: {}, visibleKeys: [], branchKeys: [], orphanSlice: [] };
}

test('重复内容让命中边不连续：尾部新回复仍须入树', () => {
  const M = loadMethods();
  const A = entry(M, 'A');
  const B = entry(M, 'B');
  const C = entry(M, 'C');
  const c = blankConv();

  const first = M.upsertTree.call(M, c, [A.node, B.node], 'generate', true);
  assert.strictEqual(first.mode, 'new');
  assert.ok(c.msgTree['0-' + A.fp] && c.msgTree[A.fp + '-' + B.fp]);

  // ids = [A,B,A,B,C]，边 = [A-B, B-A, A-B, B-C]；树里已有 A-B，
  // 于是 matched = [0, 2]，被判为「不连续」。C 是唯一的新内容。
  const second = M.upsertTree.call(M, c,
    [A.node, B.node, A.node, B.node, C.node], 'generate', true);
  assert.notStrictEqual(second.mode, 'collision', '不连续不应再整片判碰撞');
  assert.ok(c.msgTree[B.fp + '-' + C.fp],
    '尾部新回复 C 必须补进树，否则抽屉列表永远停在旧内容');
});

test('不连续且无新增：节点数保持不变，不往树里乱接历史', () => {
  const M = loadMethods();
  const A = entry(M, 'A');
  const B = entry(M, 'B');
  const c = blankConv();
  M.upsertTree.call(M, c, [A.node, B.node], 'generate', true);
  const before = Object.keys(c.msgTree).length;

  // [A,B,A,B] 的 matched = [0, 2]，末尾 B 已在树，没有新节点可补
  const r = M.upsertTree.call(M, c,
    [A.node, B.node, A.node, B.node], 'generate', true);
  assert.notStrictEqual(r.mode, 'collision');
  assert.strictEqual(Object.keys(c.msgTree).length, before);
});

test('正常连续命中仍走前缀追加，不受本次改动影响', () => {
  const M = loadMethods();
  const A = entry(M, 'A');
  const B = entry(M, 'B');
  const C = entry(M, 'C');
  const c = blankConv();
  M.upsertTree.call(M, c, [A.node, B.node], 'generate', true);
  const r = M.upsertTree.call(M, c,
    [A.node, B.node, C.node], 'generate', true);
  assert.strictEqual(r.mode, 'append');
  assert.ok(c.msgTree[B.fp + '-' + C.fp]);
});
test('同一 id 有两个父边时：尾部新内容补入且抽屉分支指向新末条', () => {
  const M = loadMethods();
  const A = entry(M, 'A');
  const B = entry(M, 'B');
  const X = entry(M, 'X');
  const C = entry(M, 'C');
  const c = blankConv();
  // A 以两条不同父边挂在树里，模拟内容指纹碰撞后的真实歧义形态
  c.msgTree = {
    ['0-' + A.fp]: A.node,
    [X.fp + '-' + A.fp]: A.node,
    [A.fp + '-' + B.fp]: B.node
  };
  const slice = [A.node, B.node, X.node, A.node, C.node];
  // 边命中下标为 [0, 2]：A-B 与 X-A 命中，中间断开；C 是唯一新内容
  const r = M.upsertTree.call(M, c, slice, 'generate', true);
  assert.notStrictEqual(r.mode, 'collision', '歧义树下也不该整片丢弃新回复');
  assert.ok(c.msgTree[A.fp + '-' + C.fp], '尾部新回复必须补进树');
  assert.ok(c.msgTree['0-' + A.fp] && c.msgTree[X.fp + '-' + A.fp],
    '两个父边都要保留：不 prepend 改根、不把历史接到末端');
  const branch = M.assembleBranchKeys.call(M, c, slice);
  assert.strictEqual(branch[branch.length - 1], A.fp + '-' + C.fp,
    '抽屉分支末条须指向新节点，否则消息列表不会更新');
});

test('命中位于中间：尾部新内容补入，原有链与根不变', () => {
  const M = loadMethods();
  const A = entry(M, 'A');
  const B = entry(M, 'B');
  const C = entry(M, 'C');
  const D = entry(M, 'D');
  const E = entry(M, 'E');
  const Z = entry(M, 'Z');
  const c = blankConv();
  const chain = [
    ['0-' + A.fp, A.node],
    [A.fp + '-' + B.fp, B.node],
    [B.fp + '-' + C.fp, C.node],
    [C.fp + '-' + D.fp, D.node]
  ];
  chain.forEach(function (pair) { c.msgTree[pair[0]] = pair[1]; });
  const slice = [Z.node, B.node, C.node, D.node, E.node];
  // 命中边为 [1, 2]：a>0 且 b<n-2，旧实现会在这里判 middle 并整片忽略
  const r = M.upsertTree.call(M, c, slice, 'generate', true);
  assert.notStrictEqual(r.mode, 'middle');
  assert.ok(c.msgTree[D.fp + '-' + E.fp], '尾部新回复必须补进树');
  chain.forEach(function (pair) {
    assert.ok(c.msgTree[pair[0]], '原有链不应被删改：' + pair[0]);
  });
  const branch = M.assembleBranchKeys.call(M, c, slice);
  assert.strictEqual(branch[branch.length - 1], D.fp + '-' + E.fp,
    '抽屉分支末条须指向新节点');
});