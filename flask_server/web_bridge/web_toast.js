/* ============================================================
 * 网页版机器人 —— 非阻塞提示条
 * 职责：以页面内浮层替代 alert()，告知失败与状态变化。
 *
 * 为什么必须替换 alert：
 *   alert() 是同步阻塞 API。弹出期间主线程完全冻结——
 *   定时器不走、渲染停摆、轮询发不出去，直到用户点「确定」。
 *   在手机上该框常被忽略或挂在后台，一挂就是几分钟，
 *   用户感知即「页面卡死」。日志实证：每条大卡顿前 1~3 秒
 *   都有一次发送失败，正是走到 alert 的时刻。
 *
 * 设计要点：
 *   - 浮层固定底部，不拦截页面交互；
 *   - 同一时刻只显示一条，新提示覆盖旧提示（避免堆叠）；
 *   - 自动消失（默认 4 秒），也可手动点掉；
 *   - 不依赖任何第三方库，纯 DOM 操作。
 * ============================================================ */
(function () {
  'use strict';

  // 自动消失时长（毫秒）：足够读完一句话，又不至于长期占屏
  var HIDE_MS = 4000;
  // 当前浮层元素与计时器：重复调用时复用同一个节点
  var _el = null;
  var _timer = null;

  /**
   * 创建浮层节点（首次调用时）并挂到 body。
   * 样式内联：本模块要能独立工作，不依赖样式表是否加载。
   * @returns {HTMLElement} 浮层节点
   */
  function ensureEl() {
    if (_el) return _el;
    _el = document.createElement('div');
    _el.id = 'toast';
    // 固定定位 + 高层级：保证在任何布局下都可见、不被遮挡
    _el.style.cssText = [
      'position:fixed', 'left:50%', 'bottom:80px',
      'transform:translateX(-50%)',
      'max-width:86%', 'padding:10px 14px',
      'background:rgba(40,40,40,0.94)', 'color:#fff',
      'font-size:13px', 'line-height:1.5',
      'border-radius:8px', 'box-shadow:0 4px 16px rgba(0,0,0,0.28)',
      'z-index:99999', 'display:none',
      'word-break:break-word', 'text-align:center'
    ].join(';');
    // 点一下即可关闭：长提示不至于挡住操作
    _el.addEventListener('click', function () { hide(); });
    document.body.appendChild(_el);
    return _el;
  }

  /** 立即隐藏提示。 */
  function hide() {
    if (_timer) { clearTimeout(_timer); _timer = null; }
    if (_el) _el.style.display = 'none';
  }

  /**
   * 显示一条提示。
   * @param {string} msg 提示正文
   * @param {number} [ms] 自动消失时长；传 0 表示常驻直到被点掉
   */
  function show(msg, ms) {
    try {
      var el = ensureEl();
      // 同一时刻只显示一条：新提示直接覆盖旧内容，避免堆叠
      el.textContent = String(msg || '');
      el.style.display = 'block';
      if (_timer) { clearTimeout(_timer); _timer = null; }
      var wait = (typeof ms === 'number') ? ms : HIDE_MS;
      if (wait > 0) _timer = setTimeout(hide, wait);
    } catch (e) { /* 提示失败不能影响主流程 */ }
  }

  // 暴露给页面脚本：WebToast.show('...') / WebToast.hide()
  window.WebToast = { show: show, hide: hide };
})();
