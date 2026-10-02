// 模块：extend/dialog/parts/05g_cards.js
// 用途：消息建卡与质量检测：为切片代码块建卡、收集自动执行候选、
//       计算消息质量问题（代码块级 / 消息级分流）、消息级问题后台回传。
//       从 05_messages.js 抽出，使该文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /**
   * 把一张工具卡片纳入「本轮可自动执行」候选池。
   * 只收集未执行、未跳过、未在倒计时中的卡片；镜像里没有对应代码块的（幽灵卡片）不进入。
   * @param {Array} pool 候选池（就地追加）
   * @param {Object} card 工具卡片
   */
  M.collectAutoCandidate = function (pool, card) {
    if (!card || !card.isTool) return;
    if (card.executed || card.skipped || card._cdTimer) return;
    if (!this.cardInMirror(card)) return;
    if (pool.indexOf(card) >= 0) return;
    pool.push(card);
  };

  /**
   * 为切片的代码块建卡，并收集自动执行候选与重跑候选。
   * 入树的消息：卡片写在节点上，与切片消息共享同一份卡片表；
   * 不入树的消息：卡片直接写在切片消息上（供手动操作）。
   * @returns {Object} { autoCandidates, armedLast, rerunCard }
   */
  M._buildCardsForIncoming = function (conv, incoming, reason, memoryIssue, scrollOnly) {
    const autoCandidates = [];
    let armedLast = null;   // 滚动轮次里被「上膛」的最新卡片（仅最后一条消息上的）
    let rerunCard = null;   // 重复卡片重跑候选（严格受限旁路，见下方判定）
    incoming.forEach((m, mi) => {
      // 定位本条在本轮切片中的真实 key：优先用切片内相邻边 '上一条-本条'。
      // 为什么不用 keyOfId：内容指纹碰撞时，keyOfId 返回「第一个右段匹配」的
      // 更早旧 key，会把新消息指向旧节点——旧节点上已有同 id 卡片且可能已执行，
      // 导致新卡片不建、自动候选=0、分支回溯串到浅处。改用本轮真实边可避免。
      let key = '';
      if (mi > 0) {
        const edge = this.msgId(incoming[mi - 1]) + '-' + this.msgId(m);
        if (conv.msgTree[edge]) key = edge;
      }
      if (!key) key = this.keyOfId(conv.msgTree, this.msgId(m));
      const node = conv.msgTree[key];
      const holder = node || m;
      holder.cards = holder.cards || {};
      if (node) m.cards = holder.cards;
      const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
      const issue = this._messageIssue(m, mi, incoming.length, reason, memoryIssue, blocks);
      // 消息级问题（与代码块无关：语音缺失 / 思考非中文 / 记忆滞后）：
      // 改走独立的消息级后台回传，界面不显示，也不挂到任何代码块卡片上。
      if (issue && issue.scope === 'message') {
        this._scheduleMessageIssue(holder, issue, reason);
      }
      // 只有代码块级问题才随卡片回传；消息级问题已由上面单独处理，避免重复回传。
      const blockIssue = (issue && issue.scope !== 'message') ? issue : null;
      blocks.forEach((b) => {
        if (!b || b.type !== 'code' || !b.id) return;
        const exist = holder.cards[b.id];
        if (exist) {
          if (exist.isTool && blockIssue && !exist.preIssue) exist.preIssue = blockIssue;
          if (exist.autoArmed) this.collectAutoCandidate(autoCandidates, exist);
          // 重复卡片重跑：来源=generate、卡片在本轮最新消息上、且此前已执行过，三者缺一不可
          if (reason === 'generate' && mi === incoming.length - 1
              && exist.isTool && exist.executed) {
            rerunCard = exist;
          }
          return;
        }
        // 只把「助手回答」里的代码块当成可执行工具调用（用户消息里的示例块不建卡）
        const call = m.role === 'assistant' ? this.parseToolCall(b) : null;
        holder.cards[b.id] = this._makeCard(b, call, blockIssue);
        if (!call) return;
        if (scrollOnly) {
          // 滚动轮次里，只有「最后一条消息」上的新卡片才预备自动执行
          if (mi === incoming.length - 1) {
            holder.cards[b.id].autoArmed = true;
            armedLast = holder.cards[b.id];
          }
        } else {
          // 从响应式容器回读卡片再入候选：holder.cards[b.id] 是 Vue 代理，
          // 后续倒计时改的是界面真正监听的那份；直接用局部 card 会改到原始对象。
          this.collectAutoCandidate(autoCandidates, holder.cards[b.id]);
        }
      });
    });
    return { autoCandidates: autoCandidates, armedLast: armedLast, rerunCard: rerunCard };
  };

  /**
   * 计算某条消息在建卡阶段要贴的问题：多调用冲突优先，其次回复质量与记忆滞后。
   * 只在 AI 生产结束（generate）场景检测，其它场景不该给已有卡片贴问题标签。
   * @returns {Object|null} { error, message } 或 null
   */
  M._messageIssue = function (m, mi, total, reason, memoryIssue, blocks) {
    if (reason !== 'generate') return null;
    let toolCallCount = 0;
    if (m.role === 'assistant') {
      blocks.forEach((b) => {
        if (b && b.type === 'code' && b.id && this.parseToolCall(b)) toolCallCount += 1;
      });
    }
    if (toolCallCount > 1 && (this.bridgePush || {}).check_multi_call !== false) {
      return {
        error: 'multiple_tool_calls',
        // 天生依赖代码块（工具调用块），留在卡片级回传。
        scope: 'block',
        message: '本条回复包含多个工具调用代码块（共 ' + toolCallCount + ' 个）。'
          + '请一次只返回一个调用块，收到结果后再决定下一步。'
      };
    }
    if (m.role === 'assistant') {
      const issue = this.assistantQualityIssue(m);
      if (issue) return issue;
      // 记忆滞后提醒：仅贴在本轮最后一条助手输出上（更早的消息已无提醒意义）
      // 与代码块无关：记忆滞后是整条回复的属性，走消息级回传。
      if (mi === total - 1 && memoryIssue) {
        if (!memoryIssue.scope) memoryIssue.scope = 'message';
        return memoryIssue;
      }
    }
    return null;
  };

  /**
   * 构造一张代码块卡片的状态对象。
   * @param {Object} b 代码块
   * @param {Object|null} call 解析出的工具调用（非工具块为 null）
   * @param {Object|null} issue 建卡阶段检测出的问题
   * @returns {Object} 卡片对象
   */
  M._makeCard = function (b, call, issue) {
    return {
      id: b.id,
      lang: b.lang || '',
      phase: '',
      code: b.code || '',
      isTool: !!call,
      silent: !!(call && this.toolSilent(call.tool)),
      // noReply：调用方显式声明「不需要结果回传」。
      noReply: !!(call && call.parameters && call.parameters.no_reply === true),
      tool: call ? call.tool : '',
      parameters: call ? call.parameters : {},
      status: 'pending',
      result: null,
      error: null,
      executed: false,
      // finishedAt：执行完成时刻（毫秒）。执行结束（成功或失败）时写入，
      // 在消息列表中显示，便于分析卡片的时序问题。
      finishedAt: null,
      // preIssue：建卡阶段检测出的问题。执行时直接作为结果，不去调工具。
      preIssue: (call && issue) ? issue : null,
      autoArmed: false,
      stack: null,
      errorType: '',
      origin: '',
      location: null,
      hint: '',
      nonce: '',
      // hostPageUrl：承载本对话的顶层页面地址；命令超时逸散时后端据此优先回投本页面。
      // 缺这个字段时，后端只能随机投给其他页面，出现「发给 B 却落到 C」。
      hostPageUrl: this.page_url || ''
    };
  };

  /**
   * 处理消息级质量问题：与代码块无关的检测结果（语音缺失 / 思考非中文 / 记忆滞后）。
   * 方案2：后台自动回传，界面不显示、不占用任何卡片，直接走 auto_send 通道。
   * 去重键为「会话 + 消息指纹 + 问题代码」：同一问题只回传一次，避免滚动 / 切换重复触发。
   * @param {Object} holder 承载该消息的对象（消息树节点或切片消息）
   * @param {Object} issue 问题描述 { error, message, scope }
   * @param {string} reason 触发来源
   */
  M._scheduleMessageIssue = function (holder, issue, reason) {
    // 只在「AI 刚说完新话」时回传：滚动、切换等来源不重复提醒
    if (reason !== 'generate') return;
    // 与工具卡片的自动回传保持一致：自动开关关闭时不回传，避免打扰
    if (!this.autoSendEnabled) return;
    const mid = window.AIMirrorDomUtils.messageFingerprint(holder);
    // 去重：同一会话内「同一消息 + 同一问题」只回传一次；刷新后重新提醒。
    // 存在实例字段上，不写进共享的 EMPTY_CONV，避免污染空会话常量。
    const store = this._msgIssueSent || (this._msgIssueSent = {});
    const key = this.activeConv + '|' + mid + '|' + issue.error;
    if (store[key]) return;
    store[key] = true;
    // 延迟与卡片自动回传一致（autoSendDelay），避免与文本上报抢跑
    const delay = this.autoSendDelay || 3000;
    setTimeout(() => {
      // 以工具结果（bridge-chat-res）格式回传，而非纯文本。
      // 关键：镜像靠「内容含 bridge-chat-res」判定工具结果（见 05f_parse.msgSource），
      // 故这条落地即被判为 tool 来源：不冒用「用户」前缀、不算真实用户发言
      // （不误触记忆窗口），且作为一条消息进消息树。
      const payload = {
        tool: 'quality_report',
        type: 'bridge-chat-res',
        nonce: 'qr-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8),
        success: true,
        result: { issue: issue.error, message: issue.message }
      };
      window.parent.postMessage({ type: 'auto_send', text: JSON.stringify(payload, null, 2) }, '*');
      log('消息级质量回传：' + issue.error);
    }, delay);
  };

})();
