/* ============================================================
 * 网页版机器人 —— 前端日志上报（缓冲 + 批量发送 + 失败重试）
 * 职责：把前端关键事件上报到后端落盘，供排查「页面卡住 / 轮询空档 / 断连」。
 *
 * 为什么要打到后端：网页版跑在手机浏览器上，用户看不到控制台、无法复制日志。
 * 故前端在关键点调 WebLog（本模块），日志经 /api/web/client_log 落到后端
 * client-YYYY-MM-DD.log。
 *
 * 为何批量发送：轮询高峰期每秒可能产生十几条日志，每条一请求会形成
 * 「请求风暴」，把 Flask 的请求线程占满、正常接口排不上队。故改为：
 * 日志先进内存缓冲，定时（默认 1 秒）合并成一批一次性发送。
 *
 * 失败重试（关键）：sendBeacon 返回 false、或 fetch 失败时，
 * **不丢弃该批日志**，而是留在缓冲里等下次重试（有上限，防无限增长）。
 * 这样「请求发不出去」的那段时间，日志不会凭空消失，恢复后能补报，
 * 从而区分「前端没运行」与「前端在运行但发不出去」。
 *
 * 发送结果自记：发送成功 / 失败都会记一条带 pending 数的日志，
 * 便于从后端日志看出「哪一段时间在重试、积压了多少」。
 *
 * 心跳：页面可定时调 heartbeat()，正常时后端会持续收到心跳；
 * 一旦中断，结合客户端时刻即可判断「前端还在跑但请求出不去」。
 * ============================================================ */
(function () {
  'use strict';

  // 待发送日志缓冲：每项 { tag, msg, t, seq }。
  var _buf = [];
  // 定时器句柄：非空表示已安排了一次冲刷。
  var _timer = null;
  // 冲刷间隔（毫秒）：攒够这段时间的日志一次性发送。
  var FLUSH_MS = 1000;
  // 单批上限：防止极端堆积时单次请求体过大。
  var MAX_BATCH = 100;
  // 缓冲硬上限：失败重试时缓冲会增长，超过此值丢弃最旧的，防内存无界。
  var MAX_BUFFER = 1000;
  // 全局自增序号：每条日志一个，后端据此可发现「丢号」（缺口即丢失窗口）。
  var _seq = 0;

  /**
   * 取当前时刻字符串 HH:MM:SS.mmm（前端本地时间，非服务端收到时刻）。
   * @returns {string} 形如 15:32:53.494
   */
  function nowStr() {
    var t = new Date();
    var hh = ('0' + t.getHours()).slice(-2);
    var mm = ('0' + t.getMinutes()).slice(-2);
    var ss = ('0' + t.getSeconds()).slice(-2);
    var ms = ('00' + t.getMilliseconds()).slice(-3);
    return hh + ':' + mm + ':' + ss + '.' + ms;
  }

  /**
   * 把一批日志通过 sendBeacon / fetch 发出，返回是否「已受理」。
   * sendBeacon 返回 true 表示浏览器已受理（不代表服务端已收到）；
   * 返回 false 或抛异常时，调用方应保留数据、下次重试。
   * @param {string} payload JSON 字符串
   * @returns {boolean} 是否受理成功
   */
  function _send(payload) {
    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([payload], { type: 'application/json' });
        return navigator.sendBeacon('/api/web/client_log', blob) === true;
      }
      // 无 sendBeacon：退回 fetch(keepalive)，失败时留待重试
      fetch('/api/web/client_log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true
      }).catch(function () {});
      return true;
    } catch (e) {
      return false;
    }
  }

  /**
   * 冲刷缓冲。发送失败时把该批放回缓冲头部，等下次重试。
   * 每次冲刷都记一条自带的结果日志（成败 + 积压数）。
   */
  function flush() {
    _timer = null;
    if (!_buf.length) return;
    var batch = _buf;
    var payload;
    try {
      payload = JSON.stringify(batch);
    } catch (e) {
      _buf = [];   // 序列化失败无法重试，丢弃（极端情况）
      return;
    }
    var ok = _send(payload);
    if (ok) {
      _buf = [];
    } else {
      // 失败：保留该批，下次重试。为防无限增长，超硬上限时丢最旧的。
      if (batch.length > MAX_BUFFER) {
        batch = batch.slice(batch.length - MAX_BUFFER);
      }
      _buf = batch;
      // 失败后尽快重试：安排一次稍长的重试
      if (_timer === null) {
        _timer = setTimeout(flush, FLUSH_MS * 2);
      }
    }
  }

  /**
   * 上报一条前端日志：入缓冲，定时统一发送。
   * @param {string} tag 分类标签（如 poll / render / page）
   * @param {string} msg 正文
   */
  function clientLog(tag, msg) {
    try {
      _seq += 1;
      _buf.push({ tag: tag, msg: msg, t: nowStr(), seq: _seq });
      if (_buf.length >= MAX_BATCH) { flush(); return; }
      if (_timer === null) {
        _timer = setTimeout(flush, FLUSH_MS);
      }
    } catch (e) { /* 上报失败不影响主流程 */ }
  }

  /**
   * 心跳：页面定时调用，正常时后端会持续收到「hb」日志。
   * 心跳中断 + 客户端时刻连续，即可判定「前端在跑但请求出不去」。
   * @param {string} note 附加说明（可选）
   */
  function heartbeat(note) {
    clientLog('hb', note || 'alive');
  }

  // 页面隐藏时立即冲刷：切后台后定时器可能被浏览器降频，先把手头的发出去。
  // 可见性事件本身由 web_page.js 打点，此处只负责冲刷，避免重复记录。
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) flush();
    });
  }

  window.WebLog = { clientLog: clientLog, heartbeat: heartbeat, flush: flush };
})();
