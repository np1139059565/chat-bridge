/*
 * C-7 适配层骨架：解析 / 建卡 / 执行 / 回执 / 去重 / 恢复六段占位接口，
 * 均以标准 tool_call.id 与 tool 消息为唯一键。纯声明，不装配运行时、不 require 他笔文件、
 * 不新建切换开关、不新增探测他笔是否存在的运行期分支、不切活链。
 */
'use strict';
var STATUS = 'declared-placeholder';
var KEY = 'tool_call.id';
function parse(block) { return { by: KEY, block: block || null, status: STATUS }; }
function buildCard(call) { return { by: KEY, id: (call && call.id) || null, status: STATUS }; }
function execute(card) { return { by: KEY, card: card || null, status: STATUS }; }
function reply(msg) { return { by: KEY, role: 'tool', tool_call_id: (msg && msg.tool_call_id) || null, status: STATUS }; }
function dedupe(a, b) { return { by: KEY, a: a || null, b: b || null, status: STATUS }; }
function restore(sessionId, call) {
  return { by: KEY, sessionId: String(sessionId || ''), id: (call && call.id) || null,
    noMessageFingerprint: true, status: STATUS };
}
module.exports = { STATUS: STATUS, KEY: KEY, parse: parse, buildCard: buildCard, execute: execute,
  reply: reply, dedupe: dedupe, restore: restore };
