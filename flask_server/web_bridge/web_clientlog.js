/* ============================================================
 * 网页版机器人 —— 前端日志上报（缓冲 + 批量发送）
 * 职责：把前端关键事件上报到后端落盘，供排查「页面卡住 / 轮询空档 / 断连」。
 *
 * 为什么要打到后端：网页版跑在手机浏览器上，用户看不到控制台、无法复制日志。
 * 故前端在关键点调 WebLog（本模块），日志经 /api/web/client_log 落到后端
 * client-YYYY-MM-DD.log。
 *
 * 为何批量发送（关键）：
 *   轮询高峰期每秒可能产生十几条日志（poll start/ok、render、client_log 等）。
 *   若每条日志都单独发一次请求，会形成「请求风暴」——把 Flask 的请求线程占满，
 *   正常接口（拉消息等）排不上队，客户端 6 秒超时后误报「断开」。
 *   故本模块改为：日志先进内存缓冲，定时（默认 1 秒）合并成一批一次性 POST。
 *   这样请求数从「每条一请求」降到「每秒最多一请求」，从源头消除风暴。
 *
 * 关键价值：若前端主线程被卡住，连这批上报都发不出去 —— 后端日志会出现
 * 整齐空档，那空档本身就是「主线程被卡住」的证据。
 * 从 web_page.js 抽出，使主脚本保持在仓库行数上限内。
 * ============================================================ */
(function () {
  'use strict';

  // 待发送日志缓冲：每项 { tag, msg }。
  var _buf = [];
  // 定时器句柄：非空表示已安排了一次冲刷。
  var _timer = null;
  // 冲刷间隔（毫秒）：攒够这段时间的日志一次性发送。
  var FLUSH_MS = 1000;
  // 单批上限：防止极端堆积时单次请求体过大。
  var MAX_BATCH = 100;

  /**
   * 真正发送一批日志。发送后清空缓冲。
   * 优先 sendBeacon（不占主线程、页面跳走也能发出），不支持时退回 fetch(keepalive)。
   * 任何失败都静默——日志不能影响主流程。
   */
  function flush() {
    _timer = null;
    if (!_buf.length) return;
    var batch = _buf;
    _buf = [];
    var payload;
    try {
      // 统一按「数组」上报；后端兼容单条与数组两种形态。
      payload = JSON.stringify(batch);
    } catch (e) {
      return; // 序列化失败：丢弃该批，不影响主流程
    }
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([payload], { type: 'application/json' });
        navigator.sendBeacon('/api/web/client_log', blob);
      } else {
        fetch('/api/web/client_log', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload,
          keepalive: true
        }).catch(function () {});
      }
    } catch (e) { /* 上报失败不影响主流程 */ }
  }

  /**
   * 上报一条前端日志：仅入缓冲，定时统一发送。
   * @param {string} tag 分类标签（如 poll / render / page）
   * @param {string} msg 正文
   */
  function clientLog(tag, msg) {
    try {
      // 带上「前端记录时刻」：后端落盘的时间是「服务端收到」的时刻，
      // 二者不是一回事——日志经缓冲批量发送，若前端主线程冻结或网络受阻，
      // 一批日志会在恢复瞬间集中到达，服务端时间戳会挤在同一秒，
      // 无法区分「没发生」与「发了但迟到」。带上前端时刻即可还原真实时间线。
      var t = new Date();
      var hh = ('0' + t.getHours()).slice(-2);
      var mm = ('0' + t.getMinutes()).slice(-2);
      var ss = ('0' + t.getSeconds()).slice(-2);
      var ms = ('00' + t.getMilliseconds()).slice(-3);
      _buf.push({ tag: tag, msg: msg, t: hh + ':' + mm + ':' + ss + '.' + ms });
      // 缓冲超上限：立即冲刷，避免无限增长
      if (_buf.length >= MAX_BATCH) { flush(); return; }
      // 已有定时器则等它；否则安排一次冲刷
      if (_timer === null) {
        _timer = setTimeout(flush, FLUSH_MS);
      }
    } catch (e) { /* 上报失败不影响主流程 */ }
  }

  // 页面隐藏时立即冲刷：切后台后定时器可能被浏览器降频，先把手头的发出去。
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) flush();
    });
  }

  window.WebLog = { clientLog: clientLog };
})();
