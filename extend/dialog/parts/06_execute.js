// 模块：extend/dialog/parts/06_execute.js
// 用途：工具卡片的执行与自动回传：手动执行、全局自动开关、
//       执行 / 回传倒计时、跳过卡片。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /**
   * 校验卡片是否仍存在于「网页对话镜像」中（即 conv.messages 里确实有对应的代码块）。
   * 幽灵卡片的成因：卡片挂在消息树节点上（cardMap 由各节点卡片聚合而来），而镜像区
   * 只渲染 visibleKeys 对应的可见切片。当某张卡片所在的消息不在可见切片里时，
   * 它会照常进入自动候选并执行，界面上却既看不到卡片、也搜不到它的 id。
   * 这里以「镜像可见切片里确实存在该代码块」为执行前提，把它拦下。
   * @param {Object} card 待校验的工具卡片
   * @returns {boolean} 是否允许执行
   */
  M.cardInMirror = function (card) {
    if (!card || !card.id) return false;
    const messages = this.messages || [];
    for (let i = 0; i < messages.length; i++) {
      const blocks = window.AIMirrorDomUtils.toArray(messages[i] && messages[i].blocks);
      for (let j = 0; j < blocks.length; j++) {
        const b = blocks[j];
        if (b && b.type === 'code' && b.id === card.id) return true;
      }
    }
    return false;
  };

  /**
   * 执行一张工具卡片：调用后端 /tool，记录结果或失败诊断信息。
   * 失败时保留完整堆栈与错误分类，供 AI 区分参数问题与工具代码缺陷。
   */
  M.executeCard = async function (card, isAuto) {
    log('执行工具卡片', card.tool || '(非工具)', '方式=' + (isAuto ? '自动' : '手动'));
    // 建卡阶段已检测出问题（多调用冲突 / 回复质量）：直接作为本卡片的结果，
    // 不去调用本地工具，随后照常回传。
    if (card.preIssue) {
      // 回复质量问题（多调用冲突 / 思考非中文等）不是工具执行失败，
      // 而是一条正常的反馈：作为结果返回，卡片显示为完成态，不标红报错。
      // 问题详情放进 result，随结果一并回传给网页 AI。
      card.status = 'done';
      card.result = {
        issue: card.preIssue.error,
        message: card.preIssue.message
      };
      card.error = null;
      card.errorType = '';
      card.executed = true;
      if (this._persist) this._persist();
      if (isAuto && this.autoSendEnabled && !card.noReply) this.scheduleAutoSend(card);
      return;
    }
    // 执行前校验：卡片必须仍存在于「网页对话镜像」中。
    // 镜像里已不存在的卡片视为幽灵卡片，一律不执行，避免在界面上
    // 看不到、会话记录里也搜不到的情况下被自动触发。
    if (!this.cardInMirror(card)) {
      log('已拦截不在镜像中的卡片', card.tool || card.id || '');
      card.status = 'pending';
      if (!isAuto) this.toast('该卡片已不在当前镜像中，已取消执行');
      return;
    }
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
      // page_url：本抽屉挂在哪个网页上。随调用一起发给后端，
      // 外部工具（推消息 / 查样式 / 抓页面）据此把命令定向回本页面，
      // 避免同时开着多个页面时命令被别的页面抢去执行。
      const pageUrl = this.page_url || '';
      // 关键探针：确认命令确实带上了本页面的地址。
      // 若此值为空，后端无法把命令定向回本页面，双开时就会串到别的页面。
      log('提交工具调用：', card.tool, '目标页面=', pageUrl || '(空，将作为公开命令)');
      const resp = await fetch(base + '/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool: card.tool, parameters: card.parameters, page_url: pageUrl })
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
    // 结果概览：只记一行，避免把大段 result 打进控制台
    log('工具执行结束', card.tool || '(非工具)', '状态=' + card.status,
      card.error ? ('错误=' + card.error) : '');
    // 无论成功失败都记为「已执行过」，切换会话 / 刷新后可据此恢复
    card.executed = true;
    if (this._persist) this._persist();
    // 自动回传仅在「自动流程」触发时进行：用户手动点击执行 / 重新执行时，
    // 只执行、不回传，避免误把结果写回网页 AI 并触发发送。
    // noReply：调用方声明不需要结果回传，执行完即结束，不再唤醒网页 AI。
    if (isAuto && this.autoSendEnabled && !card.noReply) this.scheduleAutoSend(card);
  };

  /**
   * 全局「自动」开关：开启时未执行的工具卡片自动倒计时触发；关闭时取消所有倒计时。
   * 外部卡片与工具卡片共用该开关与延迟，不做特殊化。
   */
  M.setAutoSendEnabled = function (on) {
    log('自动回传开关：' + (on ? '开启' : '关闭'));
    this.autoSendEnabled = on;
    // 卡片状态存在消息树节点内：这里汇总当前会话全部卡片
    const cardMap = this.allCards();
    if (on) {
      // 保护：开启自动时只自动执行「最新的一张」待执行卡片。
      // 会话记录被清理或长时间未执行时可能积压大量旧卡片，全部自动执行会造成
      // 误操作与结果刷屏。旧卡片保留待执行态，由用户手动点击执行。
      // 按入列顺序取最新：工具卡片取卡片表里的末位，外部卡片取列表末位；
      // 外部卡片入列更晚，故两者都在时优先外部卡片。
      let newest = null;
      Object.keys(cardMap).forEach((id) => {
        const c = cardMap[id];
        if (!c || !c.isTool || c.executed || c.skipped || c._cdTimer) return;
        // 只自动执行仍存在于网页对话镜像中的卡片（拦截幽灵卡片）
        if (!this.cardInMirror(c)) return;
        newest = { card: c, ext: false };
      });
      // 未发送且未跳过的外部卡片一并参与「最新一张」比较
      this.externalCards.forEach((c) => {
        if (!c || c.status !== 'pending' || c.executed || c.skipped || c._cdTimer) return;
        newest = { card: c, ext: true };
      });
      if (newest) {
        if (newest.ext) this.scheduleExternalSend(newest.card);
        else this.scheduleExecute(newest.card);
      }
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

  /**
   * 点击「复制结果」按钮：
   *  · 正处于回传倒计时 → 跳过等待，立即把结果回传到网页 AI；
   *  · 否则 → 照常复制结果文本到剪贴板。
   * @param {Object} card 工具卡片
   */
  M.onResultClick = function (card) {
    if (card.phase === 'send' && card.countdown > 0) {
      // 跳过倒计时立即回传：先清掉计时器，再手动触发一次回传
      if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
      card.countdown = 0;
      card.phase = '';
      window.parent.postMessage({ type: 'auto_send', text: this.resultText(card) }, '*');
      this.toast('已回传结果到网页 AI');
      return;
    }
    this.copy(this.resultText(card));
  };

  /** 执行按钮文案：自动倒计时中显示剩余秒数，否则按是否执行过显示。 */
  M.execButtonLabel = function (card) {
    if (this.autoSendEnabled && card.phase === 'exec' && card.countdown > 0) return '执行 ' + card.countdown + 's';
    return card.executed ? '重新执行' : '执行';
  };

  /** 跳过卡片：取消其倒计时与自动回传，标记为已跳过，不再自动执行。 */
  M.skipCard = function (card) {
    log('跳过卡片', card.tool || card.id || '');
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
    // 自动流程：isAuto=true，执行完会按开关回传结果
    D.startCountdown(this, card, 'exec', () => this.executeCard(card, true));
  };

  /** 倒计时后把结果写回网页 AI 输入框并触发发送。 */
  M.scheduleAutoSend = function (card) {
    log('安排自动回传', card.tool || card.id || '');
    D.startCountdown(this, card, 'send', () => {
      log('执行自动回传', card.tool || card.id || '');
      window.parent.postMessage({ type: 'auto_send', text: this.resultText(card) }, '*');
      this.toast('已回传结果到网页 AI');
    });
  };
})();
