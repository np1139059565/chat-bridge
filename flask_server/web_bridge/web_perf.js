/* ============================================================
 * 网页版机器人 —— 前端性能监控（长任务 / 定时器间隔）
 * 职责：捕获主线程被长时间占用的证据，供排查「页面卡住」。
 *
 * 解决什么问题：
 *   轮询 / 心跳日志在卡顿时会出现 15~30 秒空白，但空白有两种成因：
 *     - 主线程被某段同步 JS 卡住，本模块能抓到 longtask；
 *     - 浏览器 / 系统冻结了页面 JS，抓不到 longtask。
 *   二者日志分不开，本模块用长任务监控与定时器实时间隔来区分。
 *
 * 两项监控：
 *   1. longtask —— PerformanceObserver 监听超过阈值的任务，
 *      记录时长；有记录 = 是代码卡的，可据此定位。
 *   2. 定时器间隔 —— 每 1 秒打点，若两次打点实时间隔远超 1 秒，
 *      说明事件循环被卡住（定时器排队但执行不了）。
 *
 * 依赖：window.WebLog（web_clientlog.js）。未加载时静默跳过。
 * ============================================================ */
(function () {
  'use strict';

  // 长任务阈值（毫秒）：超过即记录。50ms 是业界「影响交互」的常用门槛。
  var LONGTASK_MS = 50;
  // 定时器打点间隔（毫秒）与告警阈值（毫秒）：
  // 正常每 TICK_MS 一次；若实时间隔超过 GAP_WARN_MS，说明事件循环被卡。
  var TICK_MS = 1000;
  var GAP_WARN_MS = 3000;

  function log(tag, msg) {
    try {
      if (window.WebLog && window.WebLog.clientLog) window.WebLog.clientLog(tag, msg);
    } catch (e) { /* 监控失败不影响主流程 */ }
  }

  /**
   * 启动长任务监控：记录任何超过 LONGTASK_MS 的主线程阻塞。
   * PerformanceObserver 在不支持 longtask 的浏览器上会抛错，此处吞掉。
   */
  function startLongTask() {
    try {
      if (typeof PerformanceObserver === 'undefined') return;
      var po = new PerformanceObserver(function (list) {
        var entries = list.getEntries() || [];
        for (var i = 0; i < entries.length; i++) {
          var d = Math.round(entries[i].duration || 0);
          if (d >= LONGTASK_MS) log('longtask', d + 'ms');
        }
      });
      po.observe({ entryTypes: ['longtask'] });
    } catch (e) { /* 浏览器不支持 longtask，忽略 */ }
  }

  /**
   * 启动定时器间隔监控：每 TICK_MS 打一次点，
   * 若与上次的实时间隔超过 GAP_WARN_MS，记录一条「事件循环被卡」。
   * 这条记录能直接印证「日志空白」是不是因为事件循环停摆。
   * 正常间隔不写日志（避免每秒一条淹没日志），且每条 tickgap 自带心跳语义——
   * 定时器仍在跑即证明页面 JS 未停，故无需再单独发心跳日志。
   */
  function startTickWatch() {
    var last = Date.now();
    setInterval(function () {
      var now = Date.now();
      var gap = now - last;
      last = now;
      if (gap >= GAP_WARN_MS) {
        log('tickgap', '间隔=' + gap + 'ms（事件循环被卡）');
      }
    }, TICK_MS);
  }

  /** 启动全部监控。 */
  function start() {
    startLongTask();
    startTickWatch();
  }

  window.WebPerf = { start: start };
})();
