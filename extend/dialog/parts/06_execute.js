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
  M.executeCard = async function (card, isAuto, fromCommand) {
    const cid = card.id || '(无 id)';
    // 【隔离铁律】标记本次执行是否由指令触发：指令触发的执行结果不回传 AI。
    // 非指令触发（用户手动点击、卡片自然到达）显式清除标记，避免旧标记残留误拦。
    card._cmdTriggered = !!fromCommand;
    log('卡片执行开始：id=' + cid + ' 工具=' + (card.tool || '(非工具)')
      + ' 方式=' + (isAuto ? '自动' : '手动') + (fromCommand ? '（指令触发）' : ''));
    // 建卡阶段已检测出致命告警：直接作为结果，不调用本地工具
    if (card.preIssue) {
      log('卡片执行跳过：id=' + cid + ' 原因=致命告警接管（' + card.preIssue.error + '），不调用工具');
      this._applyPreIssue(card, isAuto);
      return;
    }
    // 执行前校验：卡片必须仍存在于镜像中（幽灵卡片一律不执行）
    if (!this.cardInMirror(card)) {
      log('卡片执行拦截：id=' + cid + ' 原因=不在镜像中（幽灵卡片）');
      card.status = 'pending';
      if (!isAuto) this.toast('该卡片已不在当前镜像中，已取消执行');
      return;
    }
    card.status = 'running';
    this._resetCardDiagnostics(card);
    await this._callTool(card);
    // 结果概览：只记一行，避免把大段 result 打进控制台
    log('卡片执行结束：id=' + cid + ' 工具=' + (card.tool || '(非工具)')
      + ' 状态=' + card.status + (card.error ? (' 错误=' + card.error) : ''));
    // 无论成功失败都记为「已执行过」，切换会话 / 刷新后可据此恢复
    card.executed = true;
    card.finishedAt = Date.now();
    if (this._persist) this._persist();
    // 上报一次：工具结果此时才产生，不上报的话 QQ 端只看得到工具调用、
    // 看不到结果。以 'tool' 来源上报，后端据此放行（不按普通回看丢弃）。
    if (this.reportToBridge) this.reportToBridge('tool');
    // 自动回传仅在「自动流程」触发时进行；noReply 只豁免成功结果：
    // 执行失败必须回传，让 AI 知道工具没跑成，否则卡片标红、AI 收不到反馈。
    const mustReply = !card.noReply || card.status === 'error';
    if (isAuto && this.autoSendEnabled && mustReply) {
      this.scheduleAutoSend(card);
    } else {
      // 不回传必须留痕：排查「自动流程停止」时，这是最关键的断点。
      log('卡片不回传：id=' + cid + ' 原因='
        + (isAuto ? (this.autoSendEnabled ? 'noReply' : '自动开关关') : '非自动流程'));
    }
  };

  /**
   * 处理建卡阶段已检测出的问题（多调用冲突 / 回复质量）：作为结果直接返回。
   * 这类问题不是工具执行失败，而是给 AI 的正常反馈，卡片显示为完成态。
   * @param {Object} card 工具卡片
   * @param {boolean} isAuto 是否自动流程（自动时才调度回传）
   */
  M._applyPreIssue = function (card, isAuto) {
    card.status = 'done';
    card.result = { issue: card.preIssue.error, message: card.preIssue.message };
    card.error = null;
    card.errorType = '';
    card.executed = true;
    card.finishedAt = Date.now();
    if (this._persist) this._persist();
    // 质量问题回传不受 noReply 约束：noReply 的本意是「成功结果不必回传」，
    // 而质量不合格必须让 AI 知道并修正，否则卡片看似完成、AI 却收不到反馈。
    if (isAuto && this.autoSendEnabled) this.scheduleAutoSend(card);
  };

  /**
   * 复位卡片的运行状态与失败诊断字段，准备新一轮执行。
   * @param {Object} card 工具卡片
   */
  M._resetCardDiagnostics = function (card) {
    card.error = null;
    card.result = null;
    card.stack = null;
    card.errorType = '';
    card.origin = '';
    card.location = null;
    card.hint = '';
  };

  /**
   * 调用后端 /tool 执行工具，并把结果 / 错误写入卡片。
   * 失败时留存完整堆栈与错误分类，供 AI 区分「参数写错」与「工具代码缺陷」。
   * @param {Object} card 工具卡片
   */
  M._callTool = async function (card) {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      // 目标页：AI 指定的页面；为空表示直接进入逸散
      const targetUrl = (card.parameters && card.parameters.page_url) || '';
      // 本页面：承载本对话的顶层页面地址；逸散阶段后端优先回投它
      const hostUrl = card.hostPageUrl || this.page_url || '';
      log('提交工具调用：', card.tool, '目标页=', targetUrl || '(无，直接逸散)',
        '本页面=', hostUrl || '(空)');
      const resp = await fetch(base + '/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool: card.tool,
          parameters: card.parameters,
          page_url: targetUrl,
          host_page_url: hostUrl
        })
      });
      const data = await resp.json();
      card.status = data.success ? 'done' : 'error';
      card.result = data.success ? data.result : data;
      card.error = data.success ? null : (data.error || '未知错误');
      if (!data.success) this._recordFailure(card, data);
    } catch (e) {
      card.status = 'error';
      card.error = String(e);
    }
  };

  /**
   * 记录工具失败时的诊断信息。
   * 完整堆栈与错误分类必须留存，否则 AI 无法区分「参数写错」与「工具代码有 bug」，
   * 会陷入反复改参却始终失败的死循环。
   * @param {Object} card 工具卡片
   * @param {Object} data 后端返回的失败对象
   */
  M._recordFailure = function (card, data) {
    card.stack = data.traceback || null;
    card.errorType = data.errorType || '';
    card.origin = data.origin || '';
    card.location = data.location || null;
    card.hint = data.hint || '';
  };

  /**
   * 全局「自动」开关：开启时未执行的工具卡片自动倒计时触发；关闭时取消所有倒计时。
   * 外部卡片与工具卡片共用该开关与延迟，不做特殊化。
   */
  M.setAutoSendEnabled = function (on, fromCommand) {
    log('自动回传开关：' + (on ? '开启' : '关闭') + (fromCommand ? '（指令触发）' : ''));
    this.autoSendEnabled = on;
    // 卡片状态存在消息树节点内：这里汇总当前会话全部卡片
    const cardMap = this.allCards();
    if (on) {
      // 保护：开启自动时只自动执行「最新的一张」待执行卡片。
      // 会话记录被清理或长时间未执行时可能积压大量旧卡片，全部自动执行会造成
      // 误操作与结果刷屏。旧卡片保留待执行态，由用户手动点击执行。
      // 按入列顺序取最新：工具卡片取卡片表里的末位，外部卡片取列表末位。
      //
      // 【隔离铁律】执行本身是正常流程，不禁止；但若本次开启由指令触发
      // （/sa on），被它带起来的卡片要打上「指令触发」标记，
      // 其执行结果【不回传 AI】——触发源是用户指令，指令的产物不得流向 AI。
      let newest = null;
      Object.keys(cardMap).forEach((id) => {
        const c = cardMap[id];
        if (!c || !c.isTool || c.executed || c.skipped || c._cdTimer) return;
        if (!this.cardInMirror(c)) return;
        newest = { card: c, ext: false };
      });
      this.externalCards.forEach((c) => {
        if (!c || c.status !== 'pending' || c.executed || c.skipped || c._cdTimer) return;
        newest = { card: c, ext: true };
      });
      if (newest) {
        // 工具卡片：把「指令触发」一路传到执行环节（否则 executeCard 会清掉标记）
        if (newest.ext) this.scheduleExternalSend(newest.card);
        else this.scheduleExecute(newest.card, fromCommand);
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
      this.postCardResult(card);
      this.toast('已回传结果到网页 AI');
      return;
    }
    // 结果是截图时复制图片；否则照常复制结果文本。
    const shot = D.extractScreenshot(card.result);
    if (shot) {
      this.copyImage(shot);
      return;
    }
    this.copy(this.resultText(card));
  };

  /**
   * 把卡片结果回传到网页 AI：结果是截图时发图片，否则发文本。
   * 统一入口，供「复制结果」跳过倒计时、自动回传两处共用。
   *
   * 【隔离铁律】本函数只处理【AI 主动调用的工具卡片】的结果。
   * 指令（用户在 QQ / 网页发的 /xxx）是另一条链路，其执行端是 command_actions，
   * 其回执走 /api/bridge/result → QQ / 网页收件箱，【绝不】进入本函数、
   * 【绝不】流向 AI。详见 docs/command-tool-isolation.md。
   * 若新增逻辑让指令结果走到这里，即为严重泄露缺陷。
   * @param {Object} card 工具卡片
   */
  M.postCardResult = function (card) {
    // 【隔离铁律】指令触发的执行，其结果【不回传 AI】。
    // 触发源是用户指令（/sa on 带起、/cp、/rr 等），指令的产物不得流向 AI。
    // 只回传 AI 主动调用工具产生的结果；指令来源一律跳过（结果仍留在卡片上）。
    // 详见 docs/command-tool-isolation.md。
    if (card && card._cmdTriggered) {
      log('指令触发的执行：结果不回传 AI', card.tool || card.id || '');
      return;
    }
    const shot = D.extractScreenshot(card.result);
    if (shot) {
      // 图片：交给内容脚本写进输入框并发送。统一经发送队列，避免与告警抢跑。
      D.enqueueSend({ type: 'auto_send_image', dataUrl: shot });
      return;
    }
    // 文本结果同样经队列，保证一次只回传一条、与其它回传串行。
    D.enqueueSend({ type: 'auto_send', text: this.resultText(card) });
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

  /**
   * 中止当前会话里所有「进行中」的工具卡片（倒计时中或正在执行）。
   *
   * 触发场景：外部用户消息（QQ 用户消息 / 指令 / 图片）到达时调用——
   * 若此刻还有工具卡在倒计时或执行，其回传结果会与用户新消息交错，
   * 造成「结果与问题对不上」的错乱。故立即跳过这些卡片，取消回传。
   * @param {string} [reason] 触发来源（仅用于日志）
   * @returns {number} 被中止的卡片数
   */
  M.abortActiveCards = function (reason) {
    const cardMap = this.allCards();
    let n = 0;
    Object.keys(cardMap).forEach((id) => {
      const c = cardMap[id];
      if (!c || !c.isTool) return;
      const active = c.status === 'running' || (c._cdTimer && c.countdown > 0);
      if (!active) return;
      if (c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; }
      c.countdown = 0;
      c.phase = '';
      c.skipped = true;
      n += 1;
    });
    if (n) {
      log('中止进行中卡片：' + n + ' 张（' + (reason || '') + '）');
      if (this._persist) this._persist();
      this.toast('用户消息到达，已跳过 ' + n + ' 张进行中卡片');
    }
    return n;
  };

  /** 倒计时后自动执行（与自动发送共享 autoSendDelay）。
   * @param {boolean} [fromCommand] 本次执行是否由指令触发（结果不回传 AI）
   */
  M.scheduleExecute = function (card, fromCommand) {
    // 倒计时状态机由 D.startCountdown 统一提供（工具卡片与外部卡片共用）
    // 自动流程：isAuto=true，执行完会按开关回传结果；
    // fromCommand 一路透传到 executeCard，确保「指令触发」标记不被冲掉。
    D.startCountdown(this, card, 'exec', () => this.executeCard(card, true, fromCommand));
  };

  /** 倒计时后把结果写回网页 AI 输入框并触发发送。 */
  M.scheduleAutoSend = function (card) {
    log('安排自动回传', card.tool || card.id || '');
    D.startCountdown(this, card, 'send', () => {
      log('执行自动回传', card.tool || card.id || '');
      this.postCardResult(card);
      this.toast('已回传结果到网页 AI');
    });
  };
})();
