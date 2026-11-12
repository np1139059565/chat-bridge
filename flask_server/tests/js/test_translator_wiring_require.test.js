/* ============================================================
 * 阶段 2 返工：普通 require 路径的接线覆盖
 *
 * bootDialog 经 vm.runInContext 加载 parts，那些脚本不计入 V8 覆盖率；
 * 05c / 05g 的覆盖率条目实际由「普通 require」的测试贡献。此文件用同一套
 * _part_stub 真实加载两文件并执行接线新增行，把覆盖率分母补回基线之上。
 * 与 test_translator_wiring.test.js 的区别只在加载方式，断言口径一致。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const ROOT = path.join(__dirname, '..', '..', '..');

const dialog = require('./_part_stub').installStub();
const W = global.window;
// 防御性补齐：_part_stub 若未提供，运行时才用得到，不依赖加载顺序。
W.AIMirrorDomUtils = W.AIMirrorDomUtils || {};
W.AIMirrorDomUtils.toArray = W.AIMirrorDomUtils.toArray ||
  ((v) => Array.prototype.slice.call(v || []));
W.AIMirrorDomUtils.messageFingerprint = W.AIMirrorDomUtils.messageFingerprint || (() => 'fp');

// UMD lib 挂到 W；顺序：dialects → translator → tool-schema → parts
require(path.join(ROOT, 'extend', 'lib', 'dialects.js'));
require(path.join(ROOT, 'extend', 'lib', 'translator.js'));
require(path.join(ROOT, 'extend', 'lib', 'tool-schema-adapter.js'));
require(path.join(ROOT, 'extend', 'dialog', 'parts', '05f_parse.js'));
require(path.join(ROOT, 'extend', 'dialog', 'parts', '05g_cards.js'));
require(path.join(ROOT, 'extend', 'dialog', 'parts', '05c_prompt.js'));

const M = dialog.methods;
const D = W.AIMirrorDialog;
const T = W.AIMirrorTranslator;
D.extractFile = D.extractFile || (() => []);
D.enqueueSend = D.enqueueSend || (() => {});

function makeCtx() {
  const c = Object.create(M);
  c.tools = [{ name: 'read_file', description: '读文件' },
    { name: 'write_to_file', description: '写文件' }];
  c.bridgePush = {}; c.page_url = 'p'; c.autoSendEnabled = false;
  c.activeConv = 'c'; c.rules = []; c.promptSections = []; c.skills = [];
  c.config = { flaskUrl: '' };
  c._executedSig = () => null; c.cardInMirror = () => true;
  c.toolSilent = () => false; c._prevCardsInTree = () => null;
  c.keyOfId = () => ''; c.msgId = () => 'mid';
  c.assistantQualityIssue = () => null; c._markIssueSent = () => true;
  // 普通 require 只加载了 05f/05g/05c，ensureNonce（05_messages）不在链上，
  // 按真实实现给一份等价桩，供建卡与回传主路径使用。
  c.ensureNonce = (h) => {
    if (!h.nonce) h.nonce = 'n-' + Math.random().toString(36).slice(2, 8);
    return h.nonce;
  };
  return c;
}
function callBlock(id, tool, params) {
  return { id: id, type: 'code', lang: 'json',
    code: JSON.stringify({ tool: tool, type: 'bridge-chat-call', parameters: params }) };
}

test('require 路径：解析主路径产出标准 tool_calls，nonce 首尾闭合', () => {
  const ctx = makeCtx();
  const conv = { msgTree: {} };
  const m = { role: 'assistant', name: 'AI', blocks: [callBlock('b1', 'read_file', { path: 'a.txt' })] };
  const res = M._buildCardsForIncoming.call(ctx, conv, [m], 'generate', null, false, false);
  const card = m.cards['b1'];
  assert.ok(card && card.toolCall);
  assert.strictEqual(card.toolCall.id, 'call_' + card.nonce);
  assert.strictEqual(res.toolCalls.length, 1);
  card.status = 'done'; card.result = { lines: 3 }; card.executed = true;
  const back = JSON.parse(M.resultText.call(ctx, card));
  assert.strictEqual(back.nonce, card.nonce);
  assert.strictEqual(back.nonce.indexOf('call_'), -1);
  assert.strictEqual(back.executed, true);
});

test('require 路径：resultText 失败态 / 文件附件 / 兜底三分支', () => {
  const ctx = makeCtx();
  const bad = JSON.parse(M.resultText.call(ctx, { tool: 'x', nonce: 'e1',
    status: 'error', origin: 'environment', errorType: 'TimeoutError',
    error: '超时', hint: '重试', stack: 'TB', location: { file: 'a.py' } }));
  assert.strictEqual(bad.success, false);
  assert.strictEqual(bad.nonce, 'e1');
  assert.strictEqual(bad.error, '超时');
  const orig = D.extractFile;
  D.extractFile = () => [{ name: 'a.txt', mime: 'text/plain' }];
  const file = JSON.parse(M.resultText.call(ctx, { tool: 'read_file', nonce: 'f1',
    status: 'done', result: { content: 'BIG', path: 'p', lines: 9 } }));
  assert.deepStrictEqual(file.result.files, [{ name: 'a.txt', mime: 'text/plain' }]);
  D.extractFile = orig;
  const saved = W.AIMirrorTranslator;
  W.AIMirrorTranslator = undefined;
  const raw = JSON.parse(M.resultText.call(ctx, { tool: 'y', nonce: 'raw',
    status: 'done', result: { ok: 1 } }));
  assert.strictEqual(raw.nonce, 'raw');
  W.AIMirrorTranslator = saved;
});

test('require 路径：screenshotMark 正常 / 紧凑 / 兜底', () => {
  const ctx = makeCtx();
  const card = { tool: 'screenshot', nonce: 's1',
    result: { data: { saved: { name: 's.png', path: 'p' } } } };
  const text = M.screenshotMark.call(ctx, card);
  assert.strictEqual(JSON.parse(text).nonce, 's1');
  assert.strictEqual(text.indexOf('\n'), -1);
  const saved = W.AIMirrorTranslator;
  W.AIMirrorTranslator = undefined;
  assert.strictEqual(JSON.parse(M.screenshotMark.call(ctx, card)).nonce, 's1');
  W.AIMirrorTranslator = saved;
});

test('require 路径：generateSystemPrompt 本体挂载 / 未挂载两分支', () => {
  const ctx = makeCtx();
  const on = M.generateSystemPrompt.call(ctx);
  assert.ok(on.includes('【调用前先查参数】'));
  assert.ok(on.includes('Tool·调用说明'));
  ctx.bridgePush = { voice: true };
  assert.ok(M.generateSystemPrompt.call(ctx).includes('bridge-voice'));
  const saved = W.AIMirrorTranslator;
  W.AIMirrorTranslator = undefined;
  assert.ok(M.generateSystemPrompt.call(ctx).startsWith('本会话通过'));
  W.AIMirrorTranslator = saved;
});

test('require 路径：双调用 warning 落点 / 非助手早退 / 本体缺失 / 告警去重', () => {
  const ctx = makeCtx();
  const m = { role: 'assistant', name: 'AI', blocks: [
    callBlock('b1', 'read_file', {}), callBlock('b2', 'write_to_file', {})
  ] };
  const res = M._buildCardsForIncoming.call(ctx, { msgTree: {} }, [m], 'generate', null, false, false);
  assert.strictEqual(res.toolCalls.length, 1);
  assert.ok([m.cards['b1'], m.cards['b2']].some((c) =>
    c && c.preIssue && c.preIssue.error === 'multiple_tool_calls'));
  const st = { msgIssues: [], toolCalls: [] };
  const user = { role: 'user', blocks: [callBlock('u1', 'read_file', {})] };
  const out1 = M._translateToolCalls.call(ctx, { cards: {} }, user, user.blocks, st);
  assert.strictEqual(out1.calls.length, 0);
  const saved = W.AIMirrorTranslator;
  W.AIMirrorTranslator = undefined;
  const out2 = M._translateToolCalls.call(ctx, { cards: {} },
    { role: 'assistant', blocks: [] }, [], st);
  assert.strictEqual(out2.calls.length, 0);
  W.AIMirrorTranslator = saved;
  const holder = { cards: { x: { isTool: true, tool: 'read_file', parameters: {}, nonce: 'nx' },
    y: { isTool: true, tool: 'write_to_file', parameters: {}, nonce: 'ny' } } };
  const bl = [callBlock('x', 'read_file', {}), callBlock('y', 'write_to_file', {})];
  const st2 = { msgIssues: [], toolCalls: [] };
  M._translateToolCalls.call(ctx, holder, { role: 'assistant', blocks: bl }, bl, st2);
  const n = st2.msgIssues.length;
  M._translateToolCalls.call(ctx, holder, { role: 'assistant', blocks: bl }, bl, st2);
  assert.strictEqual(st2.msgIssues.length, n);
});

test('require 路径：空返回不挂 toolCall / 空块跳过 / 复用与滚动分支', () => {
  const ctx = makeCtx();
  const orig = T.toToolCalls;
  T.toToolCalls = () => [];
  const m = { role: 'assistant', name: 'AI', blocks: [callBlock('z1', 'read_file', {})] };
  M._buildCardsForIncoming.call(ctx, { msgTree: {} }, [m], 'generate', null, false, false);
  assert.strictEqual(m.cards['z1'].toolCall, undefined);
  T.toToolCalls = orig;
  const plain = { role: 'assistant', name: 'AI',
    blocks: [{ id: 't1', type: 'text', text: 'hi' }, { type: 'code', code: 'x' }] };
  const r = M._buildCardsForIncoming.call(ctx, { msgTree: {} }, [plain], 'generate', null, false, false);
  assert.strictEqual(r.toolCalls.length, 0);
  ctx.keyOfId = () => 'mid';
  const conv = { msgTree: { mid: { role: 'assistant', blocks: [], cards: {} } } };
  const m2 = { role: 'assistant', name: 'AI', blocks: [callBlock('b2', 'read_file', {})] };
  M._buildCardsForIncoming.call(ctx, conv, [m2], 'generate', null, false, false);
  const card = conv.msgTree['mid'].cards['b2'];
  card.autoArmed = true; card.executed = false;
  const r2 = M._buildCardsForIncoming.call(ctx, conv, [m2], 'generate', null, false, false);
  assert.ok(r2.autoCandidates.length >= 1);
  ctx.keyOfId = () => '';
  const m3 = { role: 'assistant', name: 'AI', blocks: [callBlock('b3', 'read_file', {})] };
  const r3 = M._buildCardsForIncoming.call(ctx, { msgTree: {} }, [m3], 'scroll', null, true, false);
  assert.strictEqual(m3.cards['b3'].autoArmed, true);
});

test('require 路径：05g 低频分支（去重 / 候选挑选 / 告警调度 / 非工具块 / body 兜底）', () => {
  const ctx = makeCtx();
  // 1) 非工具块：_buildCardForBlock 的 if (!call) return，_makeCard 全 null 分支
  const userMsg = { role: 'user', name: 'U',
    blocks: [{ id: 'u1', type: 'code', lang: 'js', code: 'console.log(1)' }] };
  M._buildCardsForIncoming.call(ctx, { msgTree: {} }, [userMsg], 'generate', null, false, false);
  assert.strictEqual(userMsg.cards['u1'].isTool, false);

  // 2) _markDuplicateCard：同消息内重复 / 相邻消息重复 / 不命中
  const dup = { role: 'assistant', name: 'AI', blocks: [
    callBlock('d1', 'read_file', { path: 'a' }),
    callBlock('d2', 'read_file', { path: 'a' })
  ] };
  M._buildCardsForIncoming.call(ctx, { msgTree: {} }, [dup], 'generate', null, false, false);
  assert.strictEqual(dup.cards['d2'].duplicate, true);
  const holderA = { cards: { d3: {} } };
  M._markDuplicateCard.call(ctx, holderA, {}, { id: 'd3' },
    { tool: 'read_file', parameters: { path: 'a' } },
    { prevCards: { p1: { isTool: true, tool: 'read_file', parameters: { path: 'a' } } } });
  assert.strictEqual(holderA.cards['d3'].duplicate, true);
  const holderB = { cards: { d4: {} } };
  M._markDuplicateCard.call(ctx, holderB, {}, { id: 'd4' },
    { tool: 'write_to_file', parameters: { path: 'b' } }, { prevCards: {} });
  assert.strictEqual(holderB.cards['d4'].duplicate, undefined);

  // 3) _pickOwnToolCard：候选优先 / 未执行 / 全已执行 / 空表
  const c1 = { isTool: true }, c2 = { isTool: true }, c3 = { isTool: true, executed: true };
  assert.strictEqual(M._pickOwnToolCard.call(ctx, { cards: { a: c1, b: c2 } }, [c2]), c2);
  assert.strictEqual(M._pickOwnToolCard.call(ctx, { cards: { a: c1 } }, []), c1);
  assert.strictEqual(M._pickOwnToolCard.call(ctx, { cards: { a: c3 } }, []), c3);
  assert.strictEqual(M._pickOwnToolCard.call(ctx, { cards: {} }, []), null);

  // 4) _scheduleMessageIssue：非新鲜 / 开关关闭 / 去重命中 / 正常入队（补 msg_id）
  let sent = 0;
  const origSend = D.enqueueSend;
  D.enqueueSend = () => { sent += 1; };
  M._scheduleMessageIssue.call(ctx, {}, { error: 'x', message: 'y' }, false);
  assert.strictEqual(sent, 0);
  ctx.autoSendEnabled = false;
  M._scheduleMessageIssue.call(ctx, {}, { error: 'x', message: 'y' }, true);
  assert.strictEqual(sent, 0);
  ctx.autoSendEnabled = true;
  ctx._markIssueSent = () => false;
  M._scheduleMessageIssue.call(ctx, {}, { error: 'x', message: 'y' }, true);
  assert.strictEqual(sent, 0);
  ctx._markIssueSent = () => true;
  const iss = { error: 'x', message: 'y', msg_id: '' };
  M._scheduleMessageIssue.call(ctx, {}, iss, true);
  assert.strictEqual(sent, 1);
  assert.ok(iss.msg_id && iss.msg_id.length > 0);
  D.enqueueSend = origSend;

  // 5) _messageIssue 既有「多调用 fatal」路径（check_multi_call 开）与早退
  ctx.bridgePush = { check_multi_call: true };
  const mi = { role: 'assistant', blocks: [
    callBlock('x1', 'read_file', {}), callBlock('x2', 'read_file', {}) ] };
  const fatal = M._messageIssue.call(ctx, mi, 0, 1, 'generate', null, mi.blocks, true);
  assert.ok(fatal && fatal.error === 'multiple_tool_calls');
  assert.strictEqual(M._messageIssue.call(ctx, mi, 0, 1, 'generate', null, mi.blocks, false), null);
  ctx.bridgePush = {};

  // 6) _decideIssueTarget：有卡片挂 preIssue / 无卡片走调度
  const holderC = { cards: { k: { isTool: true, preIssue: null } } };
  M._decideIssueTarget.call(ctx, [], { msgIssues: [{ holder: holderC, issue: { error: 'a' } }] }, 'generate', false);
  assert.strictEqual(holderC.cards.k.preIssue.error, 'a');
  M._decideIssueTarget.call(ctx, [], { msgIssues: [{ holder: { cards: {} }, issue: { error: 'b' } }] }, 'generate', false);

  // 7) 本体 fromToolMessage / toToolMessage 的兜底分支
  assert.strictEqual(T.fromToolMessage({ role: 'user' }), '');
  const broken = JSON.parse(T.fromToolMessage({ role: 'tool', name: 'x', content: '{oops' }));
  assert.strictEqual(broken.success, true);
  assert.strictEqual(broken.nonce, '');
  const viaBody = JSON.parse(T.fromToolMessage({ role: 'tool', name: '', content: JSON.stringify({ nonce: 'nb', tool: 'z' }) }));
  assert.strictEqual(viaBody.nonce, 'nb');
  assert.strictEqual(viaBody.tool, 'z');
  assert.strictEqual(T.toToolMessage('', '', null).content, '{}');
  const failed = JSON.parse(T.fromToolMessage(
    T.toToolMessage('call_c', 'c', { success: false, error: 'e', hint: 'h' })));
  assert.strictEqual(failed.success, false);
  assert.strictEqual(failed.error, 'e');
  assert.strictEqual(failed.hint, 'h');
  assert.strictEqual(failed.nonce, 'c');
});
