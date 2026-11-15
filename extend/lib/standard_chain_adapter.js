/*
 * C-7 适配层（S2 装配面九步第 5 步：execute 段实装，运行时执行权迁移）。
 * 以标准 tool_call.id 与 tool 消息为唯一键。六段中 execute 已转实装：持执行
 * 编排骨架（running 置位 / 诊断复位 / 委托注入的执行函数 / 异常兜底 / 状态影子
 * 返回），其余五段保持 declared-placeholder 声明。执行函数（deps.callTool，
 * 含 fetch 后端等环境细节）由装配侧注入，本文件不 require 他笔文件、不新建
 * 切换开关、不探测运行环境、不切活链。
 * UMD 同源：浏览器分支挂 window.AIMirrorStandardChainAdapter，node 分支
 * module.exports 导出（既有契约夹具走 node 分支，回显语义不变）。
 */
'use strict';
var STATUS = 'declared-placeholder';
var EXECUTE_STATUS = 'implemented-S2-step5';
var KEY = 'tool_call.id';
function parse(block) { return { by: KEY, block: block || null, status: STATUS }; }
function buildCard(call) { return { by: KEY, id: (call && call.id) || null, status: STATUS }; }
// execute(card)：无 deps 或 deps.callTool 非函数时保持声明回显（C-9 边界不变）。
// execute(card, deps)：deps = { callTool: asyncFunction(card) }。骨架顺序：
//   1) 复位诊断字段（error/result/stack/errorType/origin/location/hint）；
//   2) card.status = 'running'；
//   3) await deps.callTool(card)（执行函数负责调后端并写回 status/result/error）；
//   4) 异常兜底：callTool 抛出时写 card.status='error'、card.error=String(e)，
//      不向调用方抛出（对齐旧链 catch 语义：异常不落盘、无残留副作用）；
//   5) resolve 状态影子 { by, card, status: EXECUTE_STATUS, executed, phase }。
function execute(card, deps) {
  if (!card || !deps || typeof deps.callTool !== 'function') {
    return { by: KEY, card: card || null, status: STATUS };
  }
  card.error = null;
  card.result = null;
  card.stack = null;
  card.errorType = '';
  card.origin = '';
  card.location = null;
  card.hint = '';
  card.status = 'running';
  return Promise.resolve().then(function () {
    return deps.callTool(card);
  }).then(function () {
    return {
      by: KEY,
      card: card,
      status: EXECUTE_STATUS,
      executed: true,
      phase: 'execute-done'
    };
  }).catch(function (e) {
    card.status = 'error';
    card.error = String(e);
    return {
      by: KEY,
      card: card,
      status: EXECUTE_STATUS,
      executed: true,
      phase: 'execute-caught'
    };
  });
}
function reply(msg) { return { by: KEY, role: 'tool', tool_call_id: (msg && msg.tool_call_id) || null, status: STATUS }; }
function dedupe(a, b) { return { by: KEY, a: a || null, b: b || null, status: STATUS }; }
function restore(sessionId, call) {
  return { by: KEY, sessionId: String(sessionId || ''), id: (call && call.id) || null,
    noMessageFingerprint: true, status: STATUS };
}
var adapter = {
  STATUS: STATUS,
  EXECUTE_STATUS: EXECUTE_STATUS,
  KEY: KEY,
  parse: parse,
  buildCard: buildCard,
  execute: execute,
  reply: reply,
  dedupe: dedupe,
  restore: restore
};
if (typeof module !== 'undefined' && module.exports) {
  module.exports = adapter;
} else {
  window.AIMirrorStandardChainAdapter = adapter;
}
