// 模块：extend/dialog/parts/00c_log_mirror.js
// 用途：抽屉侧调试日志 D.log —— 控制台输出 + 后端文件镜像。
//
// 为什么需要镜像：抽屉里卡片建卡、自动执行决策、倒计时、执行结果全走 D.log，
// 只打控制台的话关掉页面即失。排查「卡片双执行」时后端日志里找不到任何抽屉侧记录，
// 无从判断同一张卡是否被排了两次倒计时，故把这份日志同步落进后端日志文件。
//
// 为什么批量：D.log 调用频繁，逐条发请求会变成洪水式请求拖垮后端，
// 故攒 500ms 或满 500 条再一次性发出。
// 为什么用 _postClientLog：它已处理「抽屉未探测到后端地址」的暂存与补发，
// 且抽屉是扩展页面，不受网页源的混合内容策略限制。
// 依赖：00_data.js（本文件挂到已存在的 window.AIMirrorDialog）
(function () {
  'use strict';
  // 本文件必须早于 00_data.js 加载：00_data.js 首行就 const log = D.log，
  // 各分片同样在加载时捕获 log 引用。故这里自行创建命名空间，
  // 00_data.js 随后以 window.AIMirrorDialog || {} 复用同一对象。
  const D = window.AIMirrorDialog = window.AIMirrorDialog || {};
  D.methods = D.methods || {};

  // 待上报缓冲；_logTimer 为空表示当前没有待触发的批量发送。
  const _logBuf = [];
  let _logTimer = null;

  /** 把攒下的日志交给 _postClientLog 发出去；实例或通道不可用时静默丢弃。 */
  const _flushLogBuf = function () {
    _logTimer = null;
    if (!_logBuf.length) return;
    const inst = D.instance;
    const items = _logBuf.splice(0, _logBuf.length);
    if (!inst || !D.methods || typeof D.methods._postClientLog !== 'function') return;
    try { D.methods._postClientLog.call(inst, items); } catch (e) { /* 日志失败不影响主流程 */ }
  };

  /**
   * 抽屉调试日志：写控制台，同时排入缓冲等待批量上报后端。
   * 与内容脚本同前缀，便于在网页控制台用 [AI-Mirror] 过滤。
   */
  D.log = function () {
    const args = Array.prototype.slice.call(arguments);
    console.log.apply(console, ['[AI-Mirror][dialog]'].concat(args));
    _logBuf.push({ tag: 'ext-dialog', msg: args.join(' ') });
    // 上限保护：后端长期不可达时缓冲不会无限增长，只保留最近 500 条。
    if (_logBuf.length > 500) _logBuf.splice(0, _logBuf.length - 500);
    if (!_logTimer) _logTimer = setTimeout(_flushLogBuf, 500);
  };
})();
