/* ============================================================
 * 网页版机器人 —— 轮询看门狗（自愈）
 *
 * 解决什么问题：
 *   轮询一旦停下，能把它们重新拉起来的只有两条路径——
 *   轮询失败时的「立即重连」、以及页面切回前台的事件。
 *   任何一个环节失效，页面就永久停在「未连接」，只能刷新恢复。
 *   实际发生过：发送失败后一直显示未连接，必须刷新。
 *
 * 做法：不依赖任何事件，定时自检三件事，命中即强制复活轮询：
 *   1. 定时器丢了（pollOn 为假）——浏览器在后台可能丢弃定时器；
 *   2. 长时间没有一次成功轮询——网络恢复后本该自动重连；
 *   3. 在途标记卡死（busy 长期为真）——某次请求的收尾没执行到，
 *      后续所有轮询都在入口被跳过。
 *
 * 为什么必须独立成模块：主文件已顶到行数上限，
 * 且这是与页面业务无关的兜底逻辑，独立后便于单独测试与停用。
 * ============================================================ */
(function () {
  'use strict';

  // 自检间隔（毫秒）：1 秒一次。轮询本身 2.5 秒一轮，
  // 自检必须比它密，才能在断连后一轮之内发现并复活，
  // 而不是等用户察觉「怎么一直转圈」再修。
  var CHECK_MS = 1000;
  // 多久没有成功轮询即判定为卡死（毫秒）。
  // 取 8 秒：约等于连丢三轮，既不会把偶发慢响应误判，又能快速自愈。
  var STALE_OK_MS = 8000;
  // 在途标记持续多久即判定为泄漏（毫秒）。
  // 单次请求 6 秒必超时，超过 10 秒仍为忙，说明收尾没执行到。
  var BUSY_STALE_MS = 10000;

  var timer = null;        // 自检定时器
  var hooks = null;        // 注入的页面钩子
  var busySince = 0;       // 在途标记变为真的时刻
  var lastReviveAt = 0;    // 上次复活时刻，用于防抖

  var api = {};

  /**
   * 执行一次自检。页面在后台时直接跳过：
   * 后台定时器本就被浏览器节流，此时判「卡死」会误复活。
   */
  function check() {
    // document 在 node 测试环境不存在：取不到就当作「页面可见」，
    // 让纯逻辑可以被单测直接驱动。
    var hidden = (typeof document !== 'undefined') && document.hidden;
    if (!hooks || hidden) return;
    var s;
    try { s = hooks.state() || {}; } catch (e) { return; }
    var now = Date.now();

    // 在途标记：记下它变真的时刻，用于判断是否泄漏
    if (s.busy) {
      if (!busySince) busySince = now;
    } else {
      busySince = 0;
    }

    var noTimer = !s.pollOn;                                   // 定时器丢了
    var busyStuck = !!(busySince && (now - busySince > BUSY_STALE_MS));  // 在途泄漏
    var stale = !!(s.lastPollOkAt && (now - s.lastPollOkAt > STALE_OK_MS)); // 久未成功
    if (!noTimer && !busyStuck && !stale) return;

    // 防抖：两次复活至少间隔一个自检周期，避免连续触发
    if (now - lastReviveAt < CHECK_MS) return;
    lastReviveAt = now;
    busySince = 0;

    try {
      hooks.revive();
    } catch (e) {
      return;   // 复活失败不抛出：下一个周期会再试
    }
    // 记一条诊断：能看到是哪种情况触发的复活
    try {
      if (window.WebLog) {
        window.WebLog.clientLog('watchdog',
          '复活轮询 noTimer=' + noTimer + ' busyStuck=' + busyStuck + ' stale=' + stale);
      }
    } catch (e) { /* 日志失败不影响复活 */ }
  }

  /**
   * 注入页面钩子。
   * @param {Object} h { state: 返回 {pollOn, busy, lastPollOkAt}, revive: 重建轮询并立即拉一次 }
   * @returns {Object} 自身，便于链式调用
   */
  api.init = function (h) {
    hooks = h || null;
    // 重新注入即视为重新开始：清掉内部计时状态。
    // 否则上一次的「在途起始时刻」与「上次复活时刻」会残留，
    // 使新会话首个周期被误判为泄漏或直接触发防抖跳过。
    busySince = 0;
    lastReviveAt = 0;
    return api;
  };

  /**
   * 启动自检。重复调用先停旧的，避免叠加定时器。
   * @returns {Object} 自身
   */
  api.start = function () {
    api.stop();
    timer = setInterval(check, CHECK_MS);
    // 网络恢复的瞬间立即自检一次，不等下一个周期：
    // 断网期间轮询必然全部失败，恢复后用户最希望「马上好」，
    // 等满 1 秒虽然短，但叠加请求往返仍可能让人再点一次刷新。
    if (typeof window !== 'undefined' && window.addEventListener) {
      window.addEventListener('online', check);
    }
    return api;
  };

  /** 停止自检。 */
  api.stop = function () {
    if (timer) { clearInterval(timer); timer = null; }
    // 一并解绑：否则重复 start 会叠加多个监听，网络恢复时触发多次复活
    if (typeof window !== 'undefined' && window.removeEventListener) {
      window.removeEventListener('online', check);
    }
  };

  // 对外暴露；check 一并暴露便于单测直接驱动一次自检
  api.check = check;
  // 浏览器挂全局；node 导出为模块，供纯逻辑单测直接驱动
  if (typeof window !== 'undefined') window.WebWatchdog = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
