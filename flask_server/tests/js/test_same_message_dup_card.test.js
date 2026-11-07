/* ============================================================
 * 同一条消息内的重复卡片：识别与不自动执行
 *
 * 背景：
 *   实测 ChatGLM 网页端会把同一回复里的一次工具调用输出成两个代码块，
 *   两块同属一条消息（msgId 相同、工具名与参数完全相同、块 id 不同），
 *   各自排一次倒计时，表现为「相差几秒执行两次、AI 收到上一张的结果」。
 *   相邻消息去重只比对上一条消息，覆盖不到同消息场景。
 *   修复：建卡时在同一 msgId 的卡片集合内比对签名，相同则标记 duplicate，
 *   保留卡片供手动查看，但不进入自动执行候选。
 *
 * 为什么限定同 msgId：跨消息的同参数调用属正常业务，
 *   全局查重会误杀真实调用。
 *
 * 运行：node --test flask_server/tests/js/test_same_message_dup_card.test.js
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

// 桩安装、分片加载与建卡辅助（buildAll / freshState）已抽至 _dup_card_fixture，
// 与相邻消息去重用例共用一份：两份测试逐字相同的段落只留一处，消除跨文件重复块。
const { freshState, buildAll, dialog } = require('./_dup_card_fixture');
const D = dialog;
const M = dialog.methods;

/**
 * 造一条带多个工具调用代码块的消息。
 *
 * @param {string} id      消息 id
 * @param {Array} calls    工具调用数组，每项为 { tool, params }
 * @returns {Object} 消息对象
 */
function makeMsg(id, calls) {
  const blocks = calls.map((c, i) => ({
    id: 'b-' + id + '-' + i,
    type: 'code',
    lang: 'json',
    code: JSON.stringify({ tool: c.tool, type: 'bridge-chat-call', parameters: c.params })
  }));
  return { id: id, role: 'assistant', cards: {}, blocks: blocks };
}


test('同一条消息内两个相同调用：后建卡被标记 duplicate', () => {
  const params = { pattern: 'qr_code_url', path: 'D:\\p\\web' };
  const m = makeMsg('m1', [
    { tool: 'search_file', params: params },
    { tool: 'search_file', params: params }
  ]);
  const autoCandidates = [];
  buildAll([m], freshState(), autoCandidates);

  const ids = Object.keys(m.cards);
  assert.strictEqual(ids.length, 2, '应建出两张卡片');
  const first = m.cards['b-m1-0'];
  const second = m.cards['b-m1-1'];
  assert.ok(first.isTool, '第一块是工具卡');
  assert.ok(second.isTool, '第二块是工具卡');
  assert.strictEqual(first.duplicate, undefined, '首卡不应标记 duplicate');
  assert.strictEqual(second.duplicate, true, '后建卡应标记 duplicate');
  // 首卡是末条消息里的正常调用，仍应进入候选；只有被标记的那张被拦下
  assert.strictEqual(autoCandidates.length, 1, '只有首卡进入自动执行候选');
  assert.ok(autoCandidates.indexOf(m.cards['b-m1-1']) === -1, '重复卡不得出现在候选池');
  assert.ok(autoCandidates.indexOf(m.cards['b-m1-0']) !== -1, '首卡应在候选池中');
});

test('同一条消息内两个不同调用：均不标记 duplicate', () => {
  const m = makeMsg('m2', [
    { tool: 'search_file', params: { pattern: 'abc', path: 'D:\\p' } },
    { tool: 'search_file', params: { pattern: 'xyz', path: 'D:\\p' } }
  ]);
  const autoCandidates = [];
  buildAll([m], freshState(), autoCandidates);

  const ids = Object.keys(m.cards);
  assert.strictEqual(ids.length, 2, '应建出两张卡片');
  ids.forEach((id) => {
    assert.strictEqual(m.cards[id].duplicate, undefined, '不同调用不应标记 duplicate');
  });
  assert.strictEqual(autoCandidates.length, 2, '两张卡都应进入候选');
});

test('同消息内三块：两同调用夹一不同调用，仅重复那块标记', () => {
  const p1 = { pattern: 'same', path: 'D:\\p' };
  const m = makeMsg('m3', [
    { tool: 'search_file', params: p1 },
    { tool: 'read_file', params: { path: 'D:\\q.txt' } },
    { tool: 'search_file', params: p1 }
  ]);
  const autoCandidates = [];
  buildAll([m], freshState(), autoCandidates);

  assert.ok(m.cards['b-m3-0'].isTool, '第一块是工具卡');
  assert.ok(m.cards['b-m3-1'].isTool, '第二块是工具卡');
  assert.ok(m.cards['b-m3-2'].isTool, '第三块是工具卡');
  assert.strictEqual(m.cards['b-m3-0'].duplicate, undefined, '首块不标记');
  assert.strictEqual(m.cards['b-m3-1'].duplicate, undefined, '中间不同调用不标记');
  assert.strictEqual(m.cards['b-m3-2'].duplicate, true, '末块与首块同签名，应标记');
  assert.strictEqual(autoCandidates.length, 2, '两张不重复卡进入候选');
});

test('不同消息相同调用仍由相邻去重处理，同消息逻辑不越界', () => {
  const params = { pattern: 'cross', path: 'D:\\p' };
  const m1 = makeMsg('m4', [{ tool: 'search_file', params: params }]);
  const m2 = makeMsg('m5', [{ tool: 'search_file', params: params }]);
  const autoCandidates = [];
  buildAll([m1, m2], freshState(), autoCandidates);

  assert.strictEqual(m1.cards['b-m4-0'].duplicate, undefined, '前一消息卡不标记');
  assert.strictEqual(m2.cards['b-m5-0'].duplicate, true, '后一消息卡由相邻去重标记');
});

