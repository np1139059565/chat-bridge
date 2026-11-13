/*
 * C-7 P2：11 份既有夹具原件共用的「标准入口」断言基准。
 * 唯一键为 tool_call.id 与 tool 消息；旧链断言由各原件自身保留，活链不摘。
 * 只依赖 C-7 声明契约面与适配层，不装配运行时、不引用 A-7/B-7 文件、
 * 不新建切换开关、不硬编码未交付实现。两笔交付后由分发方字段契约对拍。
 */
'use strict';
const C = require('../../../extend/lib/standard_chain_contract.js');
const A = require('../../../extend/lib/standard_chain_adapter.js');
const CALL = { id: 'call_n1', function: { name: 'run_command', arguments: '{}' } };
function run(a, face) {
  const id = C.makeToolCallId('n1');
  const msg = C.standardToolMessage(id, 'OK');
  const key = C.execKeyFromToolCall({ id: id, tool: 't', parameters: { a: 1 } }, 's1');
  // 各面共用的标准键基准：生成 / 剥前缀 / 契约 / tool 消息 / 去消息指纹
  a.equal(id, 'call_n1');
  a.equal(C.nonceFromToolCallId(id), 'n1');
  a.equal(C.assertStandardToolCall(CALL), true);
  a.equal(msg.role, 'tool'); a.equal(msg.tool_call_id, id);
  a.ok(key.indexOf('fingerprint') < 0);
  // 按夹具所属面补一条专属入口断言
  const faceAssert = {
    parse: () => a.equal(A.parse({ type: 'tool_calls', id: id }).by, A.KEY),
    parse_tolerant: () => a.equal(C.nonceFromToolCallId('legacy'), 'legacy'),
    card_build: () => a.equal(A.buildCard(CALL).id, id),
    adjacent_dup: () => a.equal(A.dedupe(id, id).by, A.KEY),
    same_dup: () => a.ok(C.execKeyFromToolCall(CALL, 's1').indexOf('fingerprint') < 0),
    scroll_autoexec: () => a.equal(A.execute({ id: id }).status, A.STATUS),
    sig_restore: () => a.equal(A.restore('s1', CALL).noMessageFingerprint, true),
    clear_sig: () => a.equal(C.execKeyFromToolCall(CALL, 's1'), C.execKeyFromToolCall(CALL, 's1')),
    translator: () => a.equal(A.reply({ tool_call_id: id }).role, 'tool'),
    wiring: () => a.ok(C.PRE_DISPATCH_HOOK_CONTRACT.signature.indexOf('fn(history)') >= 0),
    wiring_require: () => a.equal(C.PROTOCOL_RETIREMENT_CONTRACT.status, 'declared-placeholder')
  };
  (faceAssert[face] || faceAssert.parse)();
}
module.exports = { run: run };
