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

  var api = {
    classifyFailKind: classifyFailKind,
    offlineSuffix: offlineSuffix,
    shouldShowDisconnected: shouldShowDisconnected,
    isSlowPoll: isSlowPoll,
  };

  // 浏览器：挂到 window；node：导出为模块
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.WebLogic = api;
  }
})(typeof window !== 'undefined' ? window : this);
