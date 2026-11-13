// C-7 P1 覆盖率补正：05j_card_sig.js 分支覆盖。
// 覆盖 _executedSig 双键 / 旧键回退 / 缺字段 / 无库。
// 覆盖 _markExecutedSig 三种键 / 各短路 / 库新建。
// 覆盖 _restoreExecutedCards 命中 / 各短路 / 无树。
// 覆盖 cardMatchesBySig 命中 / 参数不同 / 空块。
// 唯一键为 tool_call.id 与 tool 消息，不含消息指纹。
// 旧链断言由 11 份原件保留，平行夹具作补充。
// 门禁阈值 90 / 70 与仓库基线不变，未改钩子。

/* C-7 P1：05j_card_sig.js 行/分支覆盖补正（标准 tool_call.id 双键 + 旧 msgId 回退 + 恢复重判 + 镜像比对）。 */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const dialog = { methods: {}, log: () => {} };
global.window = { AIMirrorDialog: dialog, AIMirrorDomUtils: { toArray: (v) => Array.isArray(v) ? v : [] } };
require(path.join(__dirname,'..','..','..','extend','dialog','parts','05j_card_sig.js'));
const M = dialog.methods;
const TAIL = '|t|{"a":1}';
function mk(sigs, extra) {
  const conv = { executedSigs: sigs, msgTree: {} };
  const base = {
    activeConv: 'c1', ensureConv: () => conv, log: () => {},
    messages: [], parseToolCall: (b) => (b && b.call) || null
  };
  const c = Object.assign(base, extra || {});
  return { c, conv };
}
const call = (o) => Object.assign({ tool:'t', parameters:{a:1} }, o||{});
const card = (o) => Object.assign({ isTool:true, tool:'t', parameters:{a:1}, msgId:'msg-1', executed:false, status:'pending' }, o||{});

test('_executedSig: 标准键/id/旧键回退/未命中/无库/缺字段', () => {
  let x = mk({ ['c1|call_n1'+TAIL]: true });
  assert.equal(M._executedSig.call(x.c,'msg-1',call({toolCallId:'call_n1'})), 'c1|call_n1'+TAIL);
  x = mk({ ['c1|call_x'+TAIL]: true });
  assert.equal(M._executedSig.call(x.c,'msg-1',call({id:'call_x'})), 'c1|call_x'+TAIL);
  x = mk({ ['c1|msg-1'+TAIL]: true });
  assert.equal(M._executedSig.call(x.c,'msg-1',call({toolCallId:'call_n1'})), 'c1|msg-1'+TAIL);
  x = mk({});
  assert.equal(M._executedSig.call(x.c,'msg-1',call({toolCallId:'call_n1'})), '');
  x = mk(undefined);
  assert.equal(M._executedSig.call(x.c,'msg-1',call({toolCallId:'call_n1'})), '');
  x = mk({});
  assert.equal(M._executedSig.call(x.c,'',call()), '');
  assert.equal(M._executedSig.call(x.c,'m',null), '');
  assert.equal(M._executedSig.call(x.c,'m',{parameters:{}}), '');
  x = mk({ ['c1|call_n1|t|{}']: true }, { ensureConv:()=>null });
  assert.equal(M._executedSig.call(x.c,'m',{toolCallId:'call_n1',tool:'t'}), '');
  x = mk({ ['c1|call_n1|t|{}']: true });
  assert.equal(M._executedSig.call(x.c,'m',{toolCallId:'call_n1',tool:'t'}), 'c1|call_n1|t|{}');
});
test('_markExecutedSig: 三键形态/无参/各短路/库新建', () => {
  let x = mk({});
  M._markExecutedSig.call(x.c,{toolCallId:'call_n1',tool:'t',parameters:{a:1}});
  assert.equal(x.conv.executedSigs['c1|call_n1'+TAIL], true);
  x = mk({});
  M._markExecutedSig.call(x.c,{toolCall:{id:'call_x'},tool:'t',parameters:{a:1}});
  assert.equal(x.conv.executedSigs['c1|call_x'+TAIL], true);
  x = mk({});
  M._markExecutedSig.call(x.c,{msgId:'msg-1',tool:'t',parameters:{a:1}});
  assert.equal(x.conv.executedSigs['c1|msg-1'+TAIL], true);
  x = mk({});
  M._markExecutedSig.call(x.c,{toolCallId:'call_z',tool:'t'});
  assert.equal(x.conv.executedSigs['c1|call_z|t|{}'], true);
  x = mk({});
  M._markExecutedSig.call(Object.assign({},x.c,{activeConv:''}),{toolCallId:'a',tool:'t'});
  M._markExecutedSig.call(x.c,null);
  M._markExecutedSig.call(x.c,{tool:'t'});
  M._markExecutedSig.call(x.c,{toolCallId:'a'});
  assert.equal(Object.keys(x.conv.executedSigs).length,0);
  x = mk(undefined);
  M._markExecutedSig.call(x.c,{toolCallId:'call_n1',tool:'t'});
  assert.equal(x.conv.executedSigs['c1|call_n1|t|{}'], true);
});
test('_restoreExecutedCards: 命中/旧键/未命中/各短路/无树/无conv', () => {
  let x = mk({ ['c1|call_n1'+TAIL]: true });
  x.conv.msgTree = { k1:{ cards:{ b1:card({toolCallId:'call_n1'}) } } };
  M._restoreExecutedCards.call(x.c,x.conv,'c1');
  assert.equal(x.conv.msgTree.k1.cards.b1.executed,true);
  assert.equal(x.conv.msgTree.k1.cards.b1.restoredFromSig,true);
  x = mk({ ['c1|msg-1'+TAIL]: true });
  x.conv.msgTree = { k1:{ cards:{ b1:card() } } };
  M._restoreExecutedCards.call(x.c,x.conv);
  assert.equal(x.conv.msgTree.k1.cards.b1.executed,true);
  x = mk({ ['c1|other'+TAIL]: true });
  x.conv.msgTree = { k1:{ cards:{ b1:card() } } };
  M._restoreExecutedCards.call(x.c,x.conv,'c1');
  assert.equal(x.conv.msgTree.k1.cards.b1.executed,false);
  x = mk({ ['c1|msg-1'+TAIL]: true });
  x.conv.msgTree = { k1: { cards: {
    n: null,
    nt: card({ isTool: false }),
    done: card({ executed: true }),
    noTool: card({ tool: '' }),
    noKey: card({ msgId: '', toolCallId: '' })
  } } };
  M._restoreExecutedCards.call(x.c,x.conv,'c1');
  const x2 = mk({}, { ensureConv:()=>null });
  M._restoreExecutedCards.call(x2.c,null,'c1');
  x = mk({}); delete x.conv.msgTree;
  M._restoreExecutedCards.call(x.c,x.conv,'c1');
});
test('cardMatchesBySig: 命中/参数不同/工具不同/非code/空块/空消息/空卡片', () => {
  let x = mk({}, { messages:[ { blocks:[ {type:'code',call:{tool:'t',parameters:{a:1}}} ] } ] });
  assert.equal(M.cardMatchesBySig.call(x.c,card()),true);
  x = mk({}, { messages:[ { blocks:[ {type:'code',call:{tool:'t',parameters:{a:2}}} ] } ] });
  assert.equal(M.cardMatchesBySig.call(x.c,card()),false);
  x = mk({}, { messages: [
    { blocks: [ { type: 'code', call: { tool: 'x', parameters: { a: 1 } } } ] },
    { blocks: [ { type: 'text' }, null, { type: 'code', call: null } ] },
    { blocks: [] }
  ] });
  assert.equal(M.cardMatchesBySig.call(x.c,card()),false);
  assert.equal(M.cardMatchesBySig.call(x.c,card({parameters:null})),false);
  assert.equal(M.cardMatchesBySig.call(x.c,null),false);
  assert.equal(M.cardMatchesBySig.call(x.c,{parameters:{}}),false);
  x = mk({});
  assert.equal(M.cardMatchesBySig.call(x.c,card()),false);
});
console.log('C7_05J_COVERAGE_OK');
