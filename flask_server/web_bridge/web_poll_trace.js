/* ============================================================
 * 网页版机器人 —— 临时诊断：轮询分段计时
 *
 * 状态：**临时诊断代码，问题定位后整个文件删除**。
 *
 * 为什么需要：卡顿时客户端表现是「请求要好几秒才回来」，
 * 但服务端日志显示处理只要 0.3ms。仅凭总耗时分不清慢在哪一环，
 * 故把一次轮询拆成四段分别计时：
 *   段 1 请求发出 → 收到响应头（网络 + 服务端处理）
 *   段 2 响应头   → 响应体读完（传输大小）
 *   段 3 文本     → JSON 解析完成（解析开销）
 *   段 4 解析完成 → 业务处理完（渲染开销）
 *
 * 用 performance.now() 而非 Date.now()：前者亚毫秒精度，且不受系统校时跳变影响。
 * 后者在手机上可能被 NTP 拨动，导致出现负耗时或虚高。
 *
 * 清理方式：删除本文件，移除 web_page.html 的引用，
 * 并把 web_page.js 里 fetch 那段还原成直接 r.json() 的写法。
 * ============================================================ */
(function () {
  'use strict';

  // 日志上报函数（init 时注入）
  var log = function () {};

  /**
   * 初始化：注入日志函数。
   *
   * @param {Function} logFn (tag, msg) => void
   */
  function init(logFn) {
    log = logFn || log;
  }

  /**
   * 高精度取时；环境不支持时退回 Date.now。
   * @returns {number} 毫秒
   */
  function now() {
    return (window.performance && performance.now) ? performance.now() : Date.now();
  }

  /**
   * 解析响应并分段计时。
   *
   * 调用方传 fetch 返回的 Response，以及起点时刻与「是否历史加载」。
   * 历史加载不记日志：一次铺十条，记四段会瞬间刷屏。
   *
   * @param {Response} resp      fetch 的响应对象
   * @param {number}   p0        请求发出时刻（now() 的返回值）
   * @param {boolean}  history   是否首次铺历史
   * @returns {Promise<Object>}  解析后的数据；解析失败返回 null
   */
  function traceResponse(resp, p0, history) {
    var p1 = now();
    if (!history) {
      // tick：距页面加载的毫秒数，用于与心跳日志对齐时间轴
      log('poll', 'phase1 响应头 +' + Math.round(p1 - p0) + 'ms tick=' + Math.round(p0));
    }
    return resp.text().then(function (txt) {
      var p2 = now();
      if (!history) {
        log('poll', 'phase2 体读完 +' + Math.round(p2 - p1) + 'ms len=' + (txt ? txt.length : 0));
      }
      var data = null;
      try { data = JSON.parse(txt); } catch (e) { data = null; }
      var p3 = now();
      if (!history) {
        log('poll', 'phase3 解析完 +' + Math.round(p3 - p2) + 'ms');
      }
      return data;
    });
  }

  /**
   * 记录业务处理耗时（段 4）。
   *
   * @param {number}  p0      请求发出时刻
   * @param {number}  p4      业务处理开始时刻
   * @param {boolean} history 是否首次铺历史
   */
  function traceBusiness(p0, p4, history) {
    if (history) return;
    var p5 = now();
    log('poll', 'phase4 业务处理 +' + Math.round(p5 - p4) + 'ms 总=' + Math.round(p5 - p0) + 'ms');
  }

  window.WebPollTrace = { init: init, now: now, traceResponse: traceResponse, traceBusiness: traceBusiness };
})();
