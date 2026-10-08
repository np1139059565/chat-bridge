/* ============================================================
 * 网页版机器人 —— 前端日志上报
 * 职责：把前端关键事件上报到后端落盘，供排查「页面卡住 / 轮询空档 / 断连」。
 *
 * 为什么要打到后端：网页版跑在手机浏览器上，用户看不到控制台、无法复制日志。
 * 故前端在关键点调 WebLog（本模块），日志经 /api/web/client_log 落到后端
 * client-YYYY-MM-DD.log。
 *
 * 关键价值：若前端主线程被卡住，连这条上报都发不出去 —— 后端日志会出现
 * 整齐空档，那空档本身就是「主线程被卡住」的证据。
 * 从 web_page.js 抽出，使主脚本保持在仓库行数上限内。
 * ============================================================ */
(function () {
  'use strict';

  /**
   * 上报一条前端日志。
   * 优先用 sendBeacon（不占主线程、页面跳走也能发出），不支持时退回
   * fetch(keepalive)。任何失败都静默——日志不能影响主流程。
   * @param {string} tag 分类标签（如 poll / render / page）
   * @param {string} msg 正文
   */
  function clientLog(tag, msg) {
    try {
      var payload = JSON.stringify({ tag: tag, msg: msg });
      if (navigator.sendBeacon) {
        // sendBeacon 用 Blob 指定 JSON 类型；后端 get_json 能解析
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

  window.WebLog = { clientLog: clientLog };
})();
