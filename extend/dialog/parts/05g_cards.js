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
  M._buildCardsForIncoming = function (conv, incoming, reason, memoryIssue, scrollOnly, isFreshReply) {
    const autoCandidates = [];
    // 状态集中到一个对象，便于把「单条消息建卡」抽成子函数，控制主函数行数。
    const state = {
      armedLast: null,        // 滚动轮次里被「上膛」的最新卡片（仅最后一条消息上的）
      rerunCard: null,        // 重复卡片重跑候选（严格受限旁路，见下方判定）
      // 告警按消息归属收集：每条消息的检查结论只登记在自己名下，
      // 由落点决策按消息逐条分发，不存在跨消息共用的暂存槽。
      msgIssues: [],
      firstToolCard: null,    // 本轮第一张工具卡片（供重跑等旁路使用）
      // isFreshReply：本轮是否属 AI 新鲜回复（与上报同一判定）。
      // 检测/回传用它取代「reason==='generate'」，避免采集来源漂移时漏检测。
      isFreshReply: !!isFreshReply,
      // lastAssistantIdx：本轮切片里最后一条助手消息的下标。
      // 为什么不用 incoming.length - 1：工具调用块之后常跟着语音块、
      // bridge_copy_md、click 等消息，它们到达后会把 AI 回复挤出末位，
      // 若只认末条，卡片就再也不被收集，表现为「没有执行按钮、也不自动执行」。
      // 用「最后一条助手消息」既覆盖上述情况，又不会把更早的历史消息纳入。
      lastAssistantIdx: (function () {
        for (let i = incoming.length - 1; i >= 0; i--) {
          if (incoming[i] && incoming[i].role === 'assistant') return i;
        }
        return -1;
      })()
    };
    incoming.forEach((m, mi) => {
      this._buildCardsForOne(conv, m, mi, incoming, reason, memoryIssue, scrollOnly, autoCandidates, state);
    });
    this._decideIssueTarget(autoCandidates, state, reason, isFreshReply);
    return { autoCandidates: autoCandidates, armedLast: state.armedLast, rerunCard: state.rerunCard };
  };

  /**
   * 处理单条消息的建卡：定位节点、检测告警、为代码块建卡并收集候选。
   * 状态经 state 对象回写，供主函数汇总与落点决策。
   */
  M._buildCardsForOne = function (conv, m, mi, incoming, reason, memoryIssue, scrollOnly, autoCandidates, state) {
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
    const issue = this._messageIssue(m, mi, incoming.length, reason, memoryIssue, blocks, state.isFreshReply);
    // 告警是「这条消息」的检查结论，只登记在这条消息名下。
    // 致命类（fatal，如多个调用块）当场作为卡片 preIssue：它依赖本条的工具调用块，
    // 天然属于本条消息；补充类（advisory）建卡后由 _decideIssueTarget 按消息分发给它自己的卡片。
    // msg_id：把归属消息的指纹写进告警本身，卡片路径与独立回传路径
    // 都用「会话 + msg_id + 问题码」作为去重键，保证同一消息的同一问题只回传一次。
    if (issue) issue.msg_id = this.msgId(m);
    if (issue && issue.severity !== 'fatal') {
      state.msgIssues.push({ holder: holder, issue: issue });
    }
    const blockIssue = (issue && issue.severity === 'fatal') ? issue : null;
    blocks.forEach((b) => {
      this._buildCardForBlock(holder, m, b, mi, incoming, reason, scrollOnly, blockIssue, autoCandidates, state);
    });
  };

  /**
   * 为单个代码块建卡（或复用已存在卡片），并维护候选、上膛、重跑与首发工具卡片状态。
   */
  M._buildCardForBlock = function (holder, m, b, mi, incoming, reason, scrollOnly, blockIssue, autoCandidates, state) {
    if (!b || b.type !== 'code' || !b.id) return;
    const exist = holder.cards[b.id];
    if (exist) {
      if (exist.isTool && blockIssue && !exist.preIssue) exist.preIssue = blockIssue;
      if (exist.isTool && !state.firstToolCard) state.firstToolCard = exist;
      // 上膛标记只在「本轮最后一条消息」上才转为自动候选：
      // 旧卡片残留的 autoArmed 不得让历史消息里的卡片重新获得执行权。
      // 同下方的放宽理由：用「最后一条助手消息」而非切片末条，
      // 否则后续到达的语音块 / 指令回执会把卡片挤出末位，标记形同虚设。
      if (exist.autoArmed && mi === state.lastAssistantIdx) {
        this.collectAutoCandidate(autoCandidates, exist);
      }
      // 已执行卡片：只登记以便留痕，不重置、不重跑。
      // 执行权只属于最后一条消息里的卡片；已完成的调用沿用原结果，
      // 避免刷新重新采集历史消息时把已执行卡片拉回待执行态再跑一遍。
      // 同上：用「最后一条助手消息」而非切片末条，避免被后续消息挤出后漏登记。
      if (state.isFreshReply && mi === state.lastAssistantIdx
          && exist.isTool && exist.executed) {
        state.rerunCard = exist;
      }
      return;
    }
    // 只把「助手回答」里的代码块当成可执行工具调用（用户消息里的示例块不建卡）
    const call = m.role === 'assistant' ? this.parseToolCall(b) : null;
    holder.cards[b.id] = this._makeCard(b, call, blockIssue);
    if (!call) return;
    // 记录归属消息指纹：刷新后代码块 id 会变，但消息指纹相对稳定，
    // 用它拼「执行签名」判定这次调用是否已执行过（见 executeCard）。
    holder.cards[b.id].msgId = this.msgId(m);
    // 签名命中说明这条调用此前执行过：直接恢复为已执行态，
    // 否则刷新后卡片会退回待执行、甚至被自动流程再跑一遍。
    const doneSig = this._executedSig(this.msgId(m), call);
    if (doneSig) {
      holder.cards[b.id].executed = true;
      holder.cards[b.id].status = 'done';
      holder.cards[b.id].restoredFromSig = true;
    }
    if (!state.firstToolCard) state.firstToolCard = holder.cards[b.id];
    if (scrollOnly) {
      // 滚动轮次里，只有「真正的新回复」上的新卡片才预备自动执行。
      // 同样不能用切片末位单独判定：向上滚动加载历史时，末位未必是新消息。
      if (mi === state.lastAssistantIdx && state.isFreshReply) {
        holder.cards[b.id].autoArmed = true;
        state.armedLast = holder.cards[b.id];
      }
    } else {
      // 非滚动轮次：只有「真正的新回复」里的卡片才有自动执行权。
      // 判据不能只看 mi === incoming.length - 1：那只是「本次切片末位」。
      // 刷新（/rall）时切片可能被截断，末位其实是早已存在的历史消息，
      // 它上面的卡片会被误当成新卡片执行。
      // state.isFreshReply 要求末条是助手消息且此前不在树中，才是真正的新消息。
      // 从响应式容器回读卡片再入候选：holder.cards[b.id] 是 Vue 代理，
      // 后续倒计时改的是界面真正监听的那份；直接用局部 card 会改到原始对象。
      // 判据：本消息是本轮「最后一条助手消息」，且本轮属新鲜回复。
      // 不用 incoming.length - 1：工具调用块之后常跟着语音块、bridge_copy_md、
      // click 等消息，它们到达后把 AI 回复挤出末位，卡片就再也不被收集，
      // 表现为「卡片没有执行按钮、也不自动执行」。
      // 也不用「任意助手消息」：那会把切片里更早的历史消息纳入，
      // 若其卡片从未执行过，会被误执行。取「最后一条助手消息」两者兼顾。
      if (mi === state.lastAssistantIdx && state.isFreshReply) {
        this.collectAutoCandidate(autoCandidates, holder.cards[b.id]);
      }
    }
  };

  /**
   * 告警落点决策：每条告警只归属产生它的那条消息。
   *
   * 两条路径，都由消息自身决定，不做跨消息搬运：
   *   1) 该消息自己有工具卡片 → 挂到该消息自己的一张卡片上作为 preIssue，
   *      执行时被拦下、直接把告警当结果回传；
   *   2) 该消息自己没有卡片（纯文字回复）→ 独立回传，报文里带这条消息的 id。
   * 两条路径都先按「会话 + 消息 id + 问题码」去重，同一条消息的同一问题只回传一次。
   */
  M._decideIssueTarget = function (autoCandidates, state, reason, isFreshReply) {
    const list = state.msgIssues || [];
    for (let i = 0; i < list.length; i++) {
      const holder = list[i].holder;
      const issue = list[i].issue;
      const target = this._pickOwnToolCard(holder, autoCandidates);
      if (target) {
        // 质量门禁：挂在本消息自己卡片上，执行时直接以告警作结果、不调用工具。
        if (!target.preIssue) target.preIssue = issue;
      } else {
        // 本消息没有可承载的卡片：独立回传，报文携带这条消息的 id 表明归属。
        this._scheduleMessageIssue(holder, issue, isFreshReply);
      }
    }
  };

  /**
   * 从某条消息自己的卡片里挑一张承载告警：优先本轮自动候选、其次未执行的在册卡片。
   * 只在该消息的 cards 表里找，绝不跨消息借用。
   * @param {Object} holder 消息承载对象
   * @param {Array} autoCandidates 本轮自动执行候选
   * @returns {Object|null} 卡片；无则 null
   */
  M._pickOwnToolCard = function (holder, autoCandidates) {
    const cards = (holder && holder.cards) || {};
    const ids = Object.keys(cards);
    const own = [];
    for (let i = 0; i < ids.length; i++) {
      const c = cards[ids[i]];
      if (c && c.isTool) own.push(c);
    }
    if (!own.length) return null;
    // 优先本轮会被自动执行的那张（候选末位），它就是本消息最新卡片。
    for (let i = autoCandidates.length - 1; i >= 0; i--) {
      if (own.indexOf(autoCandidates[i]) >= 0) return autoCandidates[i];
    }
    // 否则取本消息最后一张尚未执行的工具卡片。
    for (let i = own.length - 1; i >= 0; i--) {
      if (!own[i].executed) return own[i];
    }
    return own[own.length - 1];
  };

  /**
   * 计算某条消息在建卡阶段要贴的问题：多调用冲突优先，其次回复质量与记忆滞后。
   * 只在 AI 生产结束（generate）场景检测，其它场景不该给已有卡片贴问题标签。
   * @returns {Object|null} { error, message } 或 null
   */
  M._messageIssue = function (m, mi, total, reason, memoryIssue, blocks, isFreshReply) {
    // 判定改为「本轮是否属 AI 新鲜回复」（与上报同一条件），而非看采集来源。
    // 采集来源会因轮询错过跳变而漂移成 scroll，原判定会整体跳过检测、导致漏告警。
    if (!isFreshReply) return null;
    let toolCallCount = 0;
    if (m.role === 'assistant') {
      blocks.forEach((b) => {
        if (b && b.type === 'code' && b.id && this.parseToolCall(b)) toolCallCount += 1;
      });
    }
    // 保守判定：仅当开关明确为 true 才检测（理由同 05e_quality 的检测）
    if (toolCallCount > 1 && (this.bridgePush || {}).check_multi_call === true) {
      return {
        error: 'multiple_tool_calls',
        // 天生依赖代码块（工具调用块），留在卡片级回传。
        scope: 'block',
        // 致命类：一次多个调用块，无法判断执行哪个，接管卡片、不执行工具。
        severity: 'fatal',
        message: '本条回复包含多个工具调用代码块（共 ' + toolCallCount + ' 个）。'
          + '请一次只返回一个调用块，收到结果后再决定下一步。'
      };
    }
    if (m.role === 'assistant') {
      const issue = this.assistantQualityIssue(m);
      if (issue) return issue;
      // 记忆确认提醒：仅贴在本轮最后一条助手输出上（更早的消息已无提醒意义）
      // 与代码块无关：记忆确认是整条回复的属性，走消息级回传。
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
  /**
   * 计算一次工具调用的执行签名，用于跨刷新恢复「已执行」状态。
   *
   * 为什么需要它：代码块 id 是内容指纹，网页重新渲染后同一段调用会得到不同 id，
   * 只靠卡片自身状态无法跨刷新保留，刷新后卡片会退回待执行。
   * 签名改用「消息指纹 + 工具名 + 参数」，这三者在刷新后保持稳定。
   * @param {string} msgId 归属消息指纹
   * @param {Object} call 解析出的工具调用 {tool, parameters}
   * @returns {string} 命中返回签名，未命中返回空串
   */
  M._executedSig = function (msgId, call) {
    if (!msgId || !call || !call.tool) return '';
    const conv = this.ensureConv(this.activeConv);
    const store = (conv && conv.executedSigs) || {};
    // 签名键带上会话 id：消息指纹是内容摘要，相同内容的消息在不同会话里指纹相同，
    // 只用「消息指纹 + 工具 + 参数」会在跨会话时撞键，把别处执行过的调用误判成本次已执行。
    const sig = this.activeConv + '|' + msgId + '|' + call.tool + '|' + JSON.stringify(call.parameters || {});
    return store[sig] ? sig : '';
  };

  /**
   * 登记一次工具调用为「已执行」，供刷新后恢复状态。
   *
   * 代码块 id 会随网页重新渲染变化，只靠卡片自身状态无法跨刷新保留，
   * 故用「消息指纹 + 工具名 + 参数」这组稳定信息作为键。
   * @param {Object} card 刚执行完的卡片
   */
  M._markExecutedSig = function (card) {
    if (!this.activeConv || !card || !card.msgId || !card.tool) return;
    const conv = this.ensureConv(this.activeConv);
    if (!conv.executedSigs) conv.executedSigs = {};
    // 与 _executedSig 保持同一键格式（含会话 id），否则登记与查询对不上。
    const sig = this.activeConv + '|' + card.msgId + '|' + card.tool + '|' + JSON.stringify(card.parameters || {});
    conv.executedSigs[sig] = true;
  };

  /**
   * 按「执行签名」判断镜像里是否还存在这张卡对应的调用。
   *
   * 为什么需要它：代码块 id 是内容指纹，AI 回复追加内容后网页重渲染，
   * 同一张卡片的 id 会变；此时按旧 id 查必然落空，卡片被误判为幽灵卡。
   * 签名由「消息指纹 + 工具名 + 参数」组成，这些在内容追加时保持不变。
   * @param {Object} card 工具卡片
   * @returns {boolean} 镜像里能找到同一调用返回 true
   */
  M.cardMatchesBySig = function (card) {
    if (!card || !card.tool) return false;
    const messages = this.messages || [];
    const want = JSON.stringify(card.parameters || {});
    // 只按「工具名 + 参数」匹配，不掺消息指纹。
    // 消息指纹由全部块内容算出，AI 追加内容时必然改变，掺进去就等于让判据失效。
    // 参数通常含路径 / 命令等具体内容，重复概率低；即便误判为「存在」，
    // 后果也只是这张待执行卡片被执行——本就是要执行的动作，
    // 远好过误判为「不存在」导致卡片永远无法执行。
    for (let i = 0; i < messages.length; i++) {
      const blocks = window.AIMirrorDomUtils.toArray(messages[i] && messages[i].blocks);
      for (let j = 0; j < blocks.length; j++) {
        const b = blocks[j];
        if (!b || b.type !== 'code') continue;
        const call = this.parseToolCall(b);
        if (!call || call.tool !== card.tool) continue;
        if (JSON.stringify(call.parameters || {}) === want) return true;
      }
    }
    return false;
  };

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
      // origParameters：AI 最初传的参数，副本单独保存。
      // 用户可编辑 parameters（执行与重跑都用改后的值），
      // 「一键还原」据此恢复，避免只能靠记忆手打回去。
      origParameters: call ? JSON.parse(JSON.stringify(call.parameters || {})) : {},
      // paramsText：参数编辑框的文本。与 parameters 分开存：
      // 用户输入过程中可能是非法 JSON，不能直接污染真正用于执行的参数。
      paramsText: call ? JSON.stringify(call.parameters || {}, null, 2) : '',
      // paramsError：编辑框内容不是合法 JSON 时的提示，非空即不生效。
      paramsError: '',
      status: 'pending',
      result: null,
      error: null,
      executed: false,
      // finishedAt：执行完成时刻（毫秒）。执行结束（成功或失败）时写入，
      // 在消息列表中显示，便于分析卡片的时序问题。
      finishedAt: null,
      // preIssue：致命告警（如多个调用块）。执行时直接作为结果，不去调工具。
      preIssue: (call && issue) ? issue : null,
      // advisory：补充告警（如语音缺失 / 思考非中文）。不阻止执行，结果回传时附带。
      advisory: null,
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
   * 独立回传一条消息级质量告警。
   * 仅在「本轮没有任何工具卡片可搭」时被调用（纯文字回复场景，见建卡末尾的落点决策）。
   * 回传经统一发送队列，与其它回传串行，避免抢跑、互相顶掉。
   * 去重键为「会话 + 消息指纹 + 问题代码」：同一问题只回传一次，避免滚动 / 切换重复触发。
   * @param {Object} holder 承载该消息的对象（消息树节点或切片消息）
   * @param {Object} issue 问题描述 { error, message, scope }
   * @param {string} reason 触发来源
   */
  M._scheduleMessageIssue = function (holder, issue, isFreshReply) {
    // 只在「AI 刚说完新话」时回传：与上报同一判定，避免采集来源漂移时漏回传
    if (!isFreshReply) return;
    // 与工具卡片的自动回传保持一致：自动开关关闭时不回传，避免打扰
    if (!this.autoSendEnabled) return;
    const mid = window.AIMirrorDomUtils.messageFingerprint(holder);
    // 归属消息 id 缺省时补上：本条告警就是这条消息的检查结论。
    if (!issue.msg_id) issue.msg_id = mid;
    // 去重：与卡片回传路径共用同一个键（会话 + 归属消息 + 问题码），
    // 同一消息的同一问题只回传一次，刷新后重新提醒。
    if (!this._markIssueSent(issue)) {
      log('消息级质量回传跳过（已回传过）：' + issue.error);
      return;
    }
    // 以工具结果（bridge-chat-res）格式回传，而非纯文本。
    // 关键：镜像靠「内容含 bridge-chat-res」判定工具结果（见 05f_parse.msgSource），
    // 故这条落地即被判为 tool 来源：不冒用「用户」前缀、不算真实用户发言
    // （不误触记忆窗口），且作为一条消息进消息树。
    // 经统一发送队列回传：与本轮其它回传串行，避免抢跑、互相顶掉。
    // 注意：此函数只在本轮「无工具卡片可搭」时才会被调用（见建卡末尾的落点决策）。
    const payload = {
      tool: 'quality_report',
      type: 'bridge-chat-res',
      nonce: 'qr-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8),
      success: true,
      // msg_id：这条告警归属的消息指纹，供回传端与日志核对「告警来自哪条回复」。
      result: { issue: issue.error, message: issue.message, msg_id: mid }
    };
    D.enqueueSend({ type: 'auto_send', text: JSON.stringify(payload, null, 2) });
    log('消息级质量回传（无卡片，独立入队）：' + issue.error);
  };

})();
