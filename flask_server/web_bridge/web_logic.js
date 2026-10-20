/* ============================================================
 * 网页版机器人 —— 前端纯逻辑（无 DOM / 无副作用）
 * 职责：把可独立验证的纯计算集中于此，供页面调用，也供测试直接验证。
 *
 * 为什么要抽出来：
 *   页面脚本（web_page.js）与 DOM、定时器、fetch 强耦合，无法脱离浏览器测试。
 *   把「失败分类」这类纯计算抽到本模块后，可用 node 测试运行器直接断言，
 *   无需浏览器——补上前端逻辑的回归安全网。
 *
 * 兼容性：本文件用 ES5 语法（var / function），不依赖任何新语法，
 * 以便在浏览器与测试环境（含旧解析器）中一致运行。
 *
 * 依赖：无。浏览器通过 window.WebLogic 使用；node 通过 module.exports 使用。
 * ============================================================ */
(function (root) {
  'use strict';

  /**
   * 把请求失败归类为可读的 kind 字符串。
   *
   * 分类依据（决定「请求发不出去」还是「发出去了没回应」）：
   *   - AbortError：被超时主动中断 —— 请求已进入网络、但迟迟无响应；
   *   - TypeError ：网络层直接失败（断网 / 连接失败）—— 根本没送出去；
   *   - 其它      ：取错误信息前 40 字，便于观察未预期错误。
   * @param {string} errName 错误的 name（如 'AbortError'）
   * @param {string} errMsg  错误的 message
   * @returns {string} 分类标签
   */
  function classifyFailKind(errName, errMsg) {
    if (errName === 'AbortError') return 'timeout(已发出,无响应)';
    if (errName === 'TypeError') return 'neterr(未发出/断连)';
    if (errMsg) return String(errMsg).slice(0, 40);
    return 'unknown';
  }

  /**
   * 生成离线标记后缀：浏览器认为断网时返回 ' OFFLINE'，否则空串。
   * @param {boolean} online navigator.onLine 的值
   * @returns {string}
   */
  function offlineSuffix(online) {
    return online === false ? ' OFFLINE' : '';
  }

  /**
   * 判断连续失败次数是否达到「显示断开」的容差。
   * @param {number} failCount    当前连续失败次数
   * @param {number} tolerance    容差阈值
   * @returns {boolean} 是否应显示为断开
   */
  function shouldShowDisconnected(failCount, tolerance) {
    return failCount >= tolerance;
  }

  /**
   * 判断轮询响应是否算「慢」，需要记录日志。
   * @param {number} ms        本次响应毫秒数
   * @param {number} threshold 慢阈值（毫秒）
   * @returns {boolean}
   */
  function isSlowPoll(ms, threshold) {
    return ms >= threshold;
  }

  /**
   * 判断本轮轮询是否应被跳过（上一轮尚未结束）。
   *
   * 轮询每 2.5 秒一次，单轮最长 6 秒：网络慢时必然出现「上一轮还没回来、
   * 下一轮又到了」。此时跳过而非并发堆积，否则请求越积越多、界面越卡。
   * @param {boolean} pollBusy 上一轮是否仍在进行
   * @returns {boolean} 应跳过返回 true
   */
  function shouldSkipPoll(pollBusy) {
    return pollBusy === true;
  }

  /**
   * 判断一次轮询失败是否属于「主动中止」，不应计入断连。
   *
   * 切后台与回前台补拉前都会主动掐断在途请求，这是预期行为；
   * 若把它算作失败，会误报「连接断开」，也会污染连续失败计数。
   * @param {string} errName 错误的 name
   * @returns {boolean} 属于主动中止返回 true
   */
  function isAbortError(errName) {
    return errName === 'AbortError';
  }

  /**
   * 判断页面从后台回到前台后是否需要整页重载。
   *
   * 手机浏览器在后台会冻结页面、按内存压力回收标签页；停留过久后
   * 事件循环积压、DOM 陈旧，继续复用旧页面容易长时间无响应。
   * 超过阈值就重载，换取一份干净状态。
   * @param {number} awayMs   后台停留毫秒数
   * @param {number} threshold 重载阈值（毫秒）
   * @returns {boolean} 需要重载返回 true
   */
  function shouldReloadAfterHidden(awayMs, threshold) {
    // 未记录过切后台时刻（awayMs 为 0 或非法）时不重载
    if (!awayMs || awayMs < 0) return false;
    return awayMs > threshold;
  }

  var api = {
    classifyFailKind: classifyFailKind,
    offlineSuffix: offlineSuffix,
    shouldShowDisconnected: shouldShowDisconnected,
    isSlowPoll: isSlowPoll,
    shouldSkipPoll: shouldSkipPoll,
    isAbortError: isAbortError,
    shouldReloadAfterHidden: shouldReloadAfterHidden,
  };

  // 浏览器：挂到 window；node：导出为模块
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.WebLogic = api;
  }
})(typeof window !== 'undefined' ? window : this);
