// 模块：extend/dialog/parts/00b_lifecycle.js
// 用途：卡片倒计时状态机与 mounted 生命周期。
//       从 00_data.js 抽出，使该文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;

  /**
   * 启动带倒计时的卡片状态机（工具卡片与外部卡片共用）。
   * @param {Object} ctx Vue 实例
   * @param {Object} card 目标卡片
   * @param {string} phase 'exec' 或 'send'
   * @param {Function} onDone 倒计时结束后的动作
   */
  D.startCountdown = function (ctx, card, phase, onDone) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    const secs = Math.max(1, Math.round((ctx.autoSendDelay || 3000) / 1000));
    card.phase = phase;
    card.countdown = secs;
    const tick = () => {
      card.countdown -= 1;
      if (card.countdown > 0) {
        card._cdTimer = setTimeout(tick, 1000);
        return;
      }
      card._cdTimer = null;
      card.countdown = 0;
      card.phase = '';
      onDone();
    };
    card._cdTimer = setTimeout(tick, 1000);
  };

  /** 取消卡片上正在进行的倒计时，并复位阶段与计数。 */
  D.cancelCountdown = function (card) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    card.countdown = 0;
    card.phase = '';
  };

  // mounted 生命周期
  D.mounted = function () {
    log('dialog mounted，准备就绪');
    this.ensureConv(this.activeConv);
    // 落盘队列：按会话 id 各自延迟排队
    this._persistTimers = {};
    this._persist = function (convId) {
      const id = convId || this.activeConv;
      // 该会话仍在从后端加载：此刻内存是空的，写回会用空数据覆盖后端存档。
      // 直接丢弃本次请求；加载完成后的正常流程自会重新触发写回。
      if (this._convLoading && this._convLoading[id]) {
        log('persist 跳过：会话 ' + id + ' 仍在加载');
        return;
      }
      const timers = this._persistTimers;
      if (timers[id]) clearTimeout(timers[id]);
      timers[id] = setTimeout(function () {
        delete timers[id];
        this.persistConv(id);
      }.bind(this), 500);
    };
    this.initBackend();
    window.addEventListener('message', this.onPageMessage);
    window.parent.postMessage({ type: 'request_page' }, '*');
    window.parent.postMessage({ type: 'request_panel_side' }, '*');
    window.parent.postMessage({ type: 'request_theme' }, '*');
    window.parent.postMessage({ type: 'request_panel_visible' }, '*');
    // 直读风控自动恢复开关：对话框本身就是扩展页面（chrome-extension:// 协议），
    // 可直接访问 chrome.storage，无需经内容脚本中转。
    // 直连避免了两类隐患：消息往返的时序竞争，以及监听器 this 绑定问题。
    try {
      chrome.storage.local.get(['aiMirrorRiskRecover'], function (res) {
        this.riskRecoverEnabled = !!(res && res.aiMirrorRiskRecover);
      }.bind(this));
    } catch (e) { /* 存储不可用时保持默认关闭 */ }
  };
})();
