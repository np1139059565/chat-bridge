/* ============================================================
 * 网页版机器人 —— 时间格式化
 *
 * 职责：把毫秒时间戳格式化为 HH:MM，供消息头显示。
 *
 * 独立成文件的原因：这是与业务流程无关的纯函数，主模块（web_page.js）
 * 接近行数阈值，把它抽出来既便于单测，也能给主文件腾出空间。
 * ============================================================ */
(function () {
  'use strict';

  /**
   * 把时间戳格式化为 HH:MM（24 小时制，补零）。
   *
   * 传入空值或非法值时取当前时刻，避免消息头出现 Invalid Date。
   * @param {number} ts 毫秒时间戳
   * @returns {string} 形如 "09:05" 的字符串
   */
  function fmtTime(ts) {
    var d = new Date(ts || Date.now());
    var hh = ('0' + d.getHours()).slice(-2);
    var mm = ('0' + d.getMinutes()).slice(-2);
    return hh + ':' + mm;
  }

  // 浏览器通过 window.WebTime 使用
  window.WebTime = { fmtTime: fmtTime };
})();
