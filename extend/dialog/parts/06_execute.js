// 模块：extend/dialog/parts/06_execute.js
// 用途：工具卡片的执行与自动回传：手动执行、全局自动开关、
//       执行 / 回传倒计时、跳过卡片。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 执行一张工具卡片：调用后端 /tool，记录结果或失败诊断信息。
   * 失败时保留完整堆栈与错误分类，供 AI 区分参数问题与工具代码缺陷。
   */
  M.executeCard = async function (card) {
    card.status = 'running';
    card.error = null;
    card.result = null;
    // 清空上一轮的失败诊断信息
    card.stack = null;
    card.errorType = '';
    card.origin = '';
    card.location = null;
    card.hint = '';
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const resp = await fetch(base + '/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: card.tool, parameters: card.parameters })
      });
      const data = await resp.json();
      card.status = data.success ? 'done' : 'error';
      card.result = data.success ? data.result : data;
      card.error = data.success ? null : (data.error || '未知错误');
      if (!data.success) {
        // 关键：完整堆栈与错误分类必须留存。否则 AI 无法区分「参数写错」与
        // 「本地工具代码有 bug」，会陷入反复改参却始终失败的死循环。
        card.stack = data.traceback || null;
        card.errorType = data.errorType || '';
        card.origin = data.origin || '';
        card.location = data.location || null;
        card.hint = data.hint || '';
      }
    } catch (e) {
      card.status = 'error';
      card.error = String(e);
    }
    // 无论成功失败都记为「已执行过」，切换会话 / 刷新后可据此恢复
    card.executed = true;
    if (this._persist) this._persist();
    // silent 工具为一次性副作用，不把结果回传网页 AI（避免多一轮 AI 请求）
    if (card.silent) return;
    // 开了自动回传：执行完倒计时后再把结果写回网页 AI 输入框并触发发送
    if (this.autoSendEnabled) this.scheduleAutoSend(card);
  };

  /**
   * 全局「自动」开关：开启时未执行的工具卡片自动倒计时触发；关闭时取消所有倒计时。
   * 外部卡片与工具卡片共用该开关与延迟，不做特殊化。
   */
  M.setAutoSendEnabled = function (on) {
    this.autoSendEnabled = on;
    const cardMap = (this.curConv && this.curConv.cardMap) || {};
    if (on) {
      Object.keys(cardMap).forEach((id) => {
        const c = cardMap[id];
        if (c && c.isTool && !c.executed && !c.skipped && !c._cdTimer) this.scheduleExecute(c);
      });
      // 未发送的外部卡片一并进入倒计时
      this.externalCards.forEach((c) => {
        if (c && c.status === 'pending' && !c._cdTimer) this.scheduleExternalSend(c);
      });
    } else {
      Object.keys(cardMap).forEach((id) => {
        const c = cardMap[id];
        if (!c) return;
        if (c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; }
        c.countdown = 0;
        c.phase = '';
      });
      this.externalCards.forEach((c) => {
        if (c && c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; }
        if (c) { c.countdown = 0; c.phase = ''; }
      });
      this.toast('已关闭自动回传');
    }
  };

  /** 点击执行：跳过倒计时立即执行。 */
  M.onExecuteClick = function (card) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    card.countdown = 0;
    card.phase = '';
    this.executeCard(card);
  };

  /** 执行按钮文案：自动倒计时中显示剩余秒数，否则按是否执行过显示。 */
  M.execButtonLabel = function (card) {
    if (this.autoSendEnabled && card.phase === 'exec' && card.countdown > 0) return '执行 ' + card.countdown + 's';
    return card.executed ? '重新执行' : '执行';
  };

  /** 跳过卡片：取消其倒计时与自动回传，标记为已跳过，不再自动执行。 */
  M.skipCard = function (card) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    card.countdown = 0;
    card.phase = '';
    card.skipped = true;
    if (this._persist) this._persist();
    this.toast('已跳过该卡片');
  };

  /** 倒计时后自动执行（与自动发送共享 autoSendDelay）。 */
  M.scheduleExecute = function (card) {
    // 倒计时状态机由 D.startCountdown 统一提供（工具卡片与外部卡片共用）
    D.startCountdown(this, card, 'exec', () => this.executeCard(card));
  };

  /** 倒计时后把结果写回网页 AI 输入框并触发发送。 */
  M.scheduleAutoSend = function (card) {
    D.startCountdown(this, card, 'send', () => {
      window.parent.postMessage({ type: 'auto_send', text: this.resultText(card) }, '*');
      this.toast('已回传结果到网页 AI');
    });
  };
})();
