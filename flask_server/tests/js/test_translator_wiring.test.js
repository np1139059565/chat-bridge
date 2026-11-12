/* ============================================================
 * 阶段 2 返工：接线级验收（不是纯函数自往返）
 *
 * 一条网页 AI 回复 → 标准 tool_calls → 执行信封 → 网页回执，
 * 全程走真实模块链（全量 bootDialog），并用 spy 计数证明翻译函数
 * 真的被主路径调用——没接线时这些计数必然为 0，测试即失败。
 *
 * 断言：nonce 首尾一致（不含 call_ 前缀）、cardHasMessage 命中、
 *       卡片不重复、multiple_tool_calls 告警有落点。
 * ============================================================ */
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const fs = require('node:fs');
const { bootDialog } = require('./_dialog_fixture');

const ROOT = path.join(__dirname, '..', '..', '..');
const rd = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

/** 造一个 bridge-chat-call 代码块。 */
function callBlock(id, tool, params) {
  return { id: id, type: 'code', lang: 'json',
    code: JSON.stringify({ tool: tool, type: 'bridge-chat-call', parameters: params }) };
}

/** 全量启动抽屉脚本链，返回命名空间与译员本体。 */
function boot() {
  const { sandbox, errors } = bootDialog();
  assert.deepStrictEqual(errors.map((e) => e.file + ': ' + e.error.message), [],
    '全量启动不应有脚本崩');
  return { D: sandbox.AIMirrorDialog, M: sandbox.AIMirrorDialog.methods,
    T: sandbox.AIMirrorTranslator, sandbox: sandbox };
}

/** 造一个能承载建卡 / 回传方法的 ctx（原型链继承真实 methods）。 */
function makeCtx(M) {
  const ctx = Object.create(M);
  ctx.tools = [{ name: 'read_file', description: '读文件' },
    { name: 'write_to_file', description: '写文件' }];
  ctx.bridgePush = {};
  ctx.page_url = 'chat-page';
  ctx.autoSendEnabled = false;
  ctx.activeConv = 'c1';
  ctx.rules = [];
  ctx.promptSections = [];
  ctx.skills = [];
  ctx.config = { flaskUrl: '' };
  ctx._executedSig = () => null;
  ctx.cardInMirror = () => true;
  ctx.toolSilent = () => false;
  ctx._prevCardsInTree = () => null;
  ctx.keyOfId = () => '';
  ctx.msgId = () => 'mid';
  ctx.assistantQualityIssue = () => null;
  ctx._markIssueSent = () => true;
  return ctx;
}

/** 给译员的四个翻译函数套计数 spy（调用原实现）。 */
function installSpies(T) {
  const hits = { toToolCalls: 0, fromBlocks: 0, toToolMessage: 0, fromToolMessage: 0 };
  for (const name of Object.keys(hits)) {
    const orig = T[name];
    T[name] = function () {
      hits[name] += 1;
      return orig.apply(T, arguments);
    };
  }
  return hits;
}

test('接线：回复 → 标准 tool_calls → 执行信封 → 网页回执，nonce 首尾一致', () => {
  const { D, M, T } = boot();
  D.extractFile = D.extractFile || (() => []);
  const hits = installSpies(T);
  const ctx = makeCtx(M);
  const conv = { msgTree: {} };
  const m = { role: 'assistant', name: 'AI', blocks: [callBlock('b1', 'read_file', { path: 'a.txt' })] };

  // 1) 解析主路径：真实入口 _buildCardsForIncoming
  const res = M._buildCardsForIncoming.call(ctx, conv, [m], 'generate', null, false, false);
  assert.ok(hits.toToolCalls >= 1, 'toToolCalls 未进解析主路径');
  assert.ok(hits.fromBlocks >= 1, 'fromBlocks 未进解析主路径');
  const card = m.cards['b1'];
  assert.ok(card && card.isTool, '工具卡片未建');
  assert.ok(card.toolCall, '卡片未挂标准 tool_call');
  assert.strictEqual(card.toolCall.id, 'call_' + card.nonce);
  assert.strictEqual(card.toolCall.type, 'function');
  assert.strictEqual(card.toolCall.function.name, 'read_file');
  assert.deepStrictEqual(JSON.parse(card.toolCall.function.arguments), { path: 'a.txt' });
  assert.strictEqual(res.toolCalls.length, 1, '未产出标准 tool_calls');
  assert.strictEqual(res.toolCalls[0].id, card.toolCall.id);

  // 2) 执行信封 → 标准 tool 消息 → 网页回执（回传主路径）
  card.status = 'done';
  card.result = { lines: 3 };
  card.executed = true;
  const text = M.resultText.call(ctx, card);
  assert.ok(hits.toToolMessage >= 1, 'toToolMessage 未进回传主路径');
  assert.ok(hits.fromToolMessage >= 1, 'fromToolMessage 未进回传主路径');
  const back = JSON.parse(text);
  assert.strictEqual(back.type, 'bridge-chat-res');
  assert.strictEqual(back.tool, 'read_file');
  assert.strictEqual(back.nonce, card.nonce, '回执 nonce 与卡片不一致');
  assert.strictEqual(back.nonce.indexOf('call_'), -1, 'call_ 前缀被吐回前端');
  assert.strictEqual(back.success, true);
  assert.strictEqual(back.executed, true, '诊断字段在标准往返中丢失');
  assert.deepStrictEqual(back.result, { lines: 3 });

  // 3) 回执落地为 user 消息后，nonce 配对命中，卡片不重复
  const conv2 = {
    msgTree: { k1: { role: 'user', blocks: [{ type: 'code', code: text }] } },
    externalCards: [card]
  };
  assert.strictEqual(D.cardHasMessage(conv2, card), true, 'cardHasMessage 未命中');
  const timeline = D.buildTimeline(conv2, ['k1']);
  assert.ok(timeline.every((it) => it.card !== card), '卡片与回执重复渲染');
});

test('接线：一轮多个调用块 → warning 落 preIssue，标准 tool_calls 只取首个', () => {
  const { M, T } = boot();
  const hits = installSpies(T);
  const ctx = makeCtx(M);
  const conv = { msgTree: {} };
  const m = { role: 'assistant', name: 'AI', blocks: [
    callBlock('b1', 'read_file', { path: 'a.txt' }),
    callBlock('b2', 'write_to_file', { path: 'b.txt' })
  ] };
  const res = M._buildCardsForIncoming.call(ctx, conv, [m], 'generate', null, false, false);
  assert.ok(hits.fromBlocks >= 1);
  assert.strictEqual(res.toolCalls.length, 1, '单线程一轮不应产出多个 tool_calls');
  const c1 = m.cards['b1'], c2 = m.cards['b2'];
  const warned = [c1, c2].some((c) => c && c.preIssue && c.preIssue.error === 'multiple_tool_calls');
  assert.ok(warned, 'multiple_tool_calls 告警没有落点');
});

test('接线：screenshotMark 也经标准往返，nonce 不带 call_ 前缀且紧凑', () => {
  const { M, T } = boot();
  const hits = installSpies(T);
  const ctx = makeCtx(M);
  const card = { tool: 'screenshot', nonce: 'shot-1', status: 'done',
    result: { data: { saved: { name: 's.png', path: 'p' } } } };
  const text = M.screenshotMark.call(ctx, card);
  assert.ok(hits.toToolMessage >= 1 && hits.fromToolMessage >= 1);
  const back = JSON.parse(text);
  assert.strictEqual(back.type, 'bridge-chat-res');
  assert.strictEqual(back.nonce, 'shot-1');
  assert.strictEqual(text.indexOf('\n'), -1, '截图标记应保持紧凑');
});

test('本体：callIdFromNonce / nonceFromCallId 互逆，剥前缀不误伤旧 id', () => {
  const { T } = boot();
  assert.strictEqual(T.callIdFromNonce('n1'), 'call_n1');
  assert.strictEqual(T.nonceFromCallId('call_n1'), 'n1');
  assert.strictEqual(T.nonceFromCallId('legacy-id'), 'legacy-id');
  assert.strictEqual(T.nonceFromCallId(''), '');
});

test('边界分支：非助手 / 无工具块 / 本体未挂 / 告警去重', () => {
  const { M, T, sandbox } = boot();
  const ctx = makeCtx(M);
  const state = { msgIssues: [], toolCalls: [] };
  const userMsg = { role: 'user', blocks: [callBlock('u1', 'read_file', {})] };
  const holder1 = { cards: {} };
  // vm realm 里构造的对象与测试 realm 原型不同，逐字段比较而非 deepStrictEqual。
  const out1 = M._translateToolCalls.call(ctx, holder1, userMsg, userMsg.blocks, state);
  assert.strictEqual(out1.calls.length, 0);
  assert.strictEqual(out1.warning, '');
  const holder2 = { cards: {} };
  const out2 = M._translateToolCalls.call(ctx, holder2,
    { role: 'assistant', blocks: [] }, [], state);
  assert.strictEqual(out2.calls.length, 0);
  assert.strictEqual(out2.warning, '');
  const saved = sandbox.AIMirrorTranslator;
  sandbox.AIMirrorTranslator = undefined;
  const out3 = M._translateToolCalls.call(ctx, holder2,
    { role: 'assistant', blocks: [] }, [], state);
  assert.strictEqual(out3.calls.length, 0);
  assert.strictEqual(out3.warning, '');
  sandbox.AIMirrorTranslator = saved;
  const holder3 = { cards: {
    x: { isTool: true, tool: 'read_file', parameters: {}, nonce: 'n-x' },
    y: { isTool: true, tool: 'write_to_file', parameters: {}, nonce: 'n-y' }
  } };
  const blocks3 = [callBlock('x', 'read_file', {}), callBlock('y', 'write_to_file', {})];
  const st3 = { msgIssues: [], toolCalls: [] };
  M._translateToolCalls.call(ctx, holder3, { role: 'assistant', blocks: blocks3 }, blocks3, st3);
  const before = st3.msgIssues.length;
  M._translateToolCalls.call(ctx, holder3, { role: 'assistant', blocks: blocks3 }, blocks3, st3);
  assert.strictEqual(st3.msgIssues.length, before, '同一消息同一告警不应重复登记');
});

test('静态核对：dialectFor 有真实调用点，05c 重复注释已清，toFlatParams 保留', () => {
  assert.ok(rd('extend/dialog/parts/01b_bridge.js').includes('T.dialectFor('));
  assert.ok(rd('extend/content/05_index.js').includes('T.dialectFor('));
  const c5 = rd('extend/dialog/parts/05c_prompt.js');
  const line = '    // 取回的标准四段在前，原模板整体作为方言说明追加在后（阶段 2 口径）。';
  assert.strictEqual(c5.split(line).length - 1, 1, '重复注释未清理干净');
  assert.ok(c5.includes('window.AIMirrorToolSchema.toFlatParams'), 'C-4 成果回退');
});

// ---------- 覆盖率补齐：接线代码的兜底与低频分支 ----------

test('回传：失败态诊断字段整体带出，call_ 前缀仍剥回', () => {
  const { M } = boot();
  const ctx = makeCtx(M);
  const card = { tool: 'run_command', nonce: 'err-1', status: 'error',
    origin: 'environment', errorType: 'TimeoutError', error: '超时',
    location: { file: 'a.py', line: 3 }, hint: '重试', stack: 'Traceback...',
    toolCall: { id: 'call_err-1' } };
  const back = JSON.parse(M.resultText.call(ctx, card));
  assert.strictEqual(back.type, 'bridge-chat-res');
  assert.strictEqual(back.nonce, 'err-1');
  assert.strictEqual(back.success, false);
  assert.strictEqual(back.origin, 'environment');
  assert.ok(back.originNote.includes('environment='));
  assert.strictEqual(back.executed, true);
  assert.strictEqual(back.errorType, 'TimeoutError');
  assert.strictEqual(back.error, '超时');
  assert.strictEqual(back.hint, '重试');
  assert.strictEqual(back.stack, 'Traceback...');
  assert.deepStrictEqual(back.location, { file: 'a.py', line: 3 });
});

test('回传：失败态各归因档与最小字段（未知归因兜底 / not_executed）', () => {
  const { M } = boot();
  const ctx = makeCtx(M);
  for (const origin of ['precheck', 'parameter', 'tool_internal', 'weird']) {
    const back = JSON.parse(M.resultText.call(ctx, {
      tool: 'x', nonce: 'n-' + origin, status: 'error', origin: origin
    }));
    assert.strictEqual(back.success, false);
    assert.ok(back.originNote && back.originNote.length > 3);
    assert.strictEqual(back.nonce, 'n-' + origin);
  }
  const bare = JSON.parse(M.resultText.call(ctx, {
    tool: 'y', nonce: 'n-bare', status: 'error', errorType: 'not_executed'
  }));
  assert.strictEqual(bare.executed, false);
  assert.strictEqual(bare.origin, 'unknown');
  assert.ok(bare.originNote.includes('unknown='));
  assert.strictEqual(bare.error, undefined);
});

test('回传：文件附件结果换成元信息摘要，非附件结果原样带出', () => {
  const { D, M } = boot();
  const ctx = makeCtx(M);
  const orig = D.extractFile;
  D.extractFile = () => [{ name: 'a.txt', mime: 'text/plain' }];
  const withFile = JSON.parse(M.resultText.call(ctx, {
    tool: 'read_file', nonce: 'f1', status: 'done',
    result: { content: 'BIG-DATA', path: 'p', lines: 9, total_lines: 9, count: 1 }
  }));
  assert.deepStrictEqual(withFile.result.files, [{ name: 'a.txt', mime: 'text/plain' }]);
  assert.strictEqual(withFile.result.content, undefined);
  assert.strictEqual(withFile.result.path, 'p');
  D.extractFile = () => [];
  const plain = JSON.parse(M.resultText.call(ctx, {
    tool: 'echo', nonce: 'f2', status: 'done', result: { ok: 1 }
  }));
  assert.deepStrictEqual(plain.result, { ok: 1 });
  D.extractFile = orig;
});

test('回传：本体未挂载时 resultText / screenshotMark 逐字退回原 payload', () => {
  const { M, sandbox } = boot();
  const ctx = makeCtx(M);
  const saved = sandbox.AIMirrorTranslator;
  sandbox.AIMirrorTranslator = undefined;
  const c1 = { tool: 'x', nonce: 'raw1', status: 'done', result: { a: 1 } };
  const back = JSON.parse(M.resultText.call(ctx, c1));
  assert.strictEqual(back.type, 'bridge-chat-res');
  assert.strictEqual(back.nonce, 'raw1');
  assert.strictEqual(back.executed, true);
  assert.deepStrictEqual(back.result, { a: 1 });
  const c2 = { tool: 'screenshot', nonce: 'raw2',
    result: { data: { saved: { name: 's.png', path: 'p' } } } };
  const mark = JSON.parse(M.screenshotMark.call(ctx, c2));
  assert.strictEqual(mark.nonce, 'raw2');
  assert.strictEqual(mark.type, 'bridge-chat-res');
  sandbox.AIMirrorTranslator = saved;
});

test('提示词：语音开关打开时注入朗读约定，本体未挂时逐字退回原模板', () => {
  const { M, sandbox } = boot();
  const ctx = makeCtx(M);
  ctx.bridgePush = { voice: true };
  ctx.systemPrompt = '';
  const on = M.generateSystemPrompt.call(ctx);
  assert.ok(on.includes('【调用前先查参数】'));
  assert.ok(on.includes('bridge-voice') && on.includes('【语音·朗读文本约定】'));
  const saved = sandbox.AIMirrorTranslator;
  sandbox.AIMirrorTranslator = undefined;
  const off = M.generateSystemPrompt.call(ctx);
  assert.ok(off.startsWith('本会话通过'));
  assert.ok(off.includes('bridge-voice'));
  assert.strictEqual(off.includes('【调用前先查参数】'), false);
  sandbox.AIMirrorTranslator = saved;
});

test('解析：复用已存在卡片 / autoArmed / rerun / 签名恢复 / 滚动上膛', () => {
  const { M } = boot();
  const ctx = makeCtx(M);
  // keyOfId 返回树节点 key，holder 取节点，二次进入走 exist 复用分支。
  ctx.keyOfId = () => 'mid';
  const conv = { msgTree: { 'mid': { role: 'assistant', blocks: [], cards: {} } } };
  const m = { role: 'assistant', name: 'AI', blocks: [callBlock('b1', 'read_file', { path: 'a.txt' })] };
  M._buildCardsForIncoming.call(ctx, conv, [m], 'generate', null, false, false);
  const card = conv.msgTree['mid'].cards['b1'];
  assert.ok(card && card.isTool);
  // 场景 A：autoArmed 且未执行 → 末条转为自动候选
  card.autoArmed = true;
  card.executed = false;
  const r2 = M._buildCardsForIncoming.call(ctx, conv, [m], 'generate', null, false, false);
  assert.ok(r2.autoCandidates.length >= 1, 'autoArmed 未转候选');
  assert.strictEqual(card.executed, false);
  // 场景 B：已执行 + fresh + 末条 → 登记 rerun（候选会拒绝已执行卡片，两者互斥）
  card.autoArmed = false;
  card.executed = true;
  const r3 = M._buildCardsForIncoming.call(ctx, conv, [m], 'generate', null, false, true);
  assert.strictEqual(r3.rerunCard, card, '已执行卡片未登记 rerun');
  // 签名恢复：_executedSig 返回真值 → 卡片恢复为已执行态
  ctx.keyOfId = () => '';
  ctx._executedSig = () => ({ done: 1 });
  const conv3 = { msgTree: {} };
  const m3 = { role: 'assistant', name: 'AI', blocks: [callBlock('b3', 'read_file', {})] };
  M._buildCardsForIncoming.call(ctx, conv3, [m3], 'generate', null, false, false);
  assert.strictEqual(m3.cards['b3'].executed, true);
  assert.strictEqual(m3.cards['b3'].restoredFromSig, true);
  // 滚动轮次：末条卡片上膛
  ctx._executedSig = () => null;
  const conv4 = { msgTree: {} };
  const m4 = { role: 'assistant', name: 'AI', blocks: [callBlock('b4', 'read_file', {})] };
  const r4 = M._buildCardsForIncoming.call(ctx, conv4, [m4], 'scroll', null, true, false);
  assert.strictEqual(m4.cards['b4'].autoArmed, true);
  assert.strictEqual(r4.armedLast, m4.cards['b4']);
  // 非工具块 / 非代码块：直接跳过，不建卡
  const conv5 = { msgTree: {} };
  const m5 = { role: 'assistant', name: 'AI', blocks: [
    { id: 't1', type: 'text', text: 'hi' }, { type: 'code', code: 'x' }
  ] };
  const r5 = M._buildCardsForIncoming.call(ctx, conv5, [m5], 'generate', null, false, false);
  assert.strictEqual(r5.toolCalls.length, 0);
});

test('告警：无卡片可搭时独立回传，去重跳过分支与 msg_id 补齐', () => {
  const { D, M, sandbox } = boot();
  const ctx = makeCtx(M);
  sandbox.AIMirrorDomUtils.messageFingerprint = () => 'fp-1';
  let sent = 0;
  const origSend = D.enqueueSend;
  D.enqueueSend = () => { sent += 1; };
  ctx.autoSendEnabled = true;
  ctx.assistantQualityIssue = () => ({ error: 'advisory_x', message: '补充告警', scope: 'message' });
  ctx._markIssueSent = () => true;
  const m = { role: 'assistant', name: 'AI', blocks: [{ id: 't1', type: 'text', text: 'hi' }] };
  const conv = { msgTree: {} };
  M._buildCardsForIncoming.call(ctx, conv, [m], 'generate', null, false, true);
  assert.strictEqual(sent, 1, '消息级告警未独立入队');
  // 去重跳过：_markIssueSent 返回 false 时不再入队
  ctx._markIssueSent = () => false;
  const m2 = { role: 'assistant', name: 'AI', blocks: [{ id: 't2', type: 'text', text: 'hi2' }] };
  M._buildCardsForIncoming.call(ctx, conv, [m2], 'generate', null, false, true);
  assert.strictEqual(sent, 1, '去重命中的告警不应重复入队');
  // 自动开关关闭：直接跳过，不入队
  ctx.autoSendEnabled = false;
  ctx._markIssueSent = () => true;
  const m3 = { role: 'assistant', name: 'AI', blocks: [{ id: 't3', type: 'text', text: 'hi3' }] };
  M._buildCardsForIncoming.call(ctx, conv, [m3], 'generate', null, false, true);
  assert.strictEqual(sent, 1);
  D.enqueueSend = origSend;
});

test('解析：toToolCalls 返回空时不挂 toolCall，protocol 仍进 fromBlocks', () => {
  const { M, T } = boot();
  const ctx = makeCtx(M);
  const orig = T.toToolCalls;
  T.toToolCalls = () => [];
  const conv = { msgTree: {} };
  const m = { role: 'assistant', name: 'AI', blocks: [callBlock('z1', 'read_file', {})] };
  M._buildCardsForIncoming.call(ctx, conv, [m], 'generate', null, false, false);
  // 只断言「空返回不挂 toolCall」；fromBlocks 用闭包内原函数，spy 不影响其汇总。
  assert.strictEqual(m.cards['z1'].toolCall, undefined);
  T.toToolCalls = orig;
});
