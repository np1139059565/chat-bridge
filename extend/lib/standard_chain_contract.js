/*
 * C-7 标准执行链契约面骨架（阶段 3 删除序列第三笔）
 * 以标准 tool_call.id 与 tool 消息为唯一键的纯函数契约面；不装配运行时、不注册钩子、
 * 不新建切换开关、不探测 A-7/B-7 是否存在、不硬编码其未交付实现。
 * A-7 声明 fn(history)->None|list，B-7 声明 bridge-chat-call/res 协议字段退役方向；
 * 两笔交付后由分发方字段契约对拍，不一致定向裁定补正。
 */
'use strict';
var PREFIX = 'call_';
function makeToolCallId(nonce) { return PREFIX + String(nonce == null ? '' : nonce); }
function nonceFromToolCallId(id) {
  var s = String(id == null ? '' : id);
  return s.indexOf(PREFIX) === 0 ? s.slice(PREFIX.length) : s;
}
function standardToolMessage(callId, content) {
  return { role: 'tool', tool_call_id: String(callId), content: String(content == null ? '' : content) };
}
/* 刷新恢复键：会话 id + tool_call.id + 工具名 + 参数摘要，不含消息指纹 */
function execKeyFromToolCall(call, sessionId) {
  var id = nonceFromToolCallId(call && call.id);
  var name = (call && (call.tool || (call.function && call.function.name))) || '';
  var args = call && (call.parameters || (call.function && call.function.arguments));
  var digest = '';
  try { digest = JSON.stringify(args == null ? {} : args); } catch (e) { digest = String(args); }
  return [String(sessionId || ''), id, String(name), digest].join('|');
}
var PRE_DISPATCH_HOOK_CONTRACT = Object.freeze({
  owner: 'A-7', names: ['register_pre_dispatch_hook','clear_pre_dispatch_hooks','_run_pre_dispatch_hooks'],
  signature: 'fn(history) -> None | list', status: 'declared-placeholder'
});
var PROTOCOL_RETIREMENT_CONTRACT = Object.freeze({
  owner: 'B-7', legacy: ['bridge-chat-call','bridge-chat-res'],
  direction: 'standard tool_calls / tool message as the only key', status: 'declared-placeholder'
});
function assertStandardToolCall(item) {
  if (!item || typeof item !== 'object') throw new Error('tool_call must be object');
  if (typeof item.id !== 'string' || !item.id) throw new Error('tool_call.id required');
  if (!item.function || typeof item.function.name !== 'string') throw new Error('function.name required');
  return true;
}
module.exports = { PREFIX: PREFIX, makeToolCallId: makeToolCallId, nonceFromToolCallId: nonceFromToolCallId,
  standardToolMessage: standardToolMessage, execKeyFromToolCall: execKeyFromToolCall,
  assertStandardToolCall: assertStandardToolCall, PRE_DISPATCH_HOOK_CONTRACT: PRE_DISPATCH_HOOK_CONTRACT,
  PROTOCOL_RETIREMENT_CONTRACT: PROTOCOL_RETIREMENT_CONTRACT };
