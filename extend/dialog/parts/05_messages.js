// 模块：extend/dialog/parts/05_messages.js
// 用途：消息接收与消息树核心：工具列表拉取、网页消息接收与解析、
//       分支组装、自动执行候选收集、助手回复质量检测。
//       消息树写入口 upsertTree 在 05b_tree.js。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 数据模型：
//   会话 = {
//     title, page_url,
//     msgTree:     { '<父id>-<子id>': 节点 },   // 唯一存完整信息处；根用哨兵 0
//     visibleKeys: [ '<父id>-<子id>', ... ],     // 当前可见区切片（有序）
//     branchKeys:  [ '<父id>-<子id>', ... ],     // 组装出的分支（有序）
//     externalCards: [ ... ],                    // 外部卡片：不属于网页消息，单独存
//     orphanSlice: [ 消息对象, ... ],            // 与历史断裂的切片，仅用于展示
//     updatedAt
//   }
//   节点 = { role, name, blocks, deleted, cards }
//     - blocks：消息内容块；代码块自带 id
//     - deleted：删除标记（节点保留，树不断裂，列表不显示）
//     - cards：{ 代码块id: 卡片状态 }
//   顺序完全由 pid-id 结构决定。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /** 拉取后端工具目录；失败时回退内置列表。随后刷新技能数据与 System Prompt。 */
  M.fetchTools = async function () {
    try {
      const data = await D.apiFetch(this, '/tools', {
        headers: { 'Accept': 'application/json' }
      });
      this.tools = data.tools || data;
      this.flaskOk = true;
      log('工具目录已从后端加载：' + this.tools.length + ' 个');
    } catch (e) {
      this.tools = D.FALLBACK_TOOLS;
      this.flaskOk = false;
      this.flaskError = String(e);
      log('后端不可达，已回退内置工具目录：' + this.flaskError);
    }
    // 工具上下线会改变技能说明的生效集合，故一并刷新技能数据后再生 System Prompt
    await this.loadPromptSections();
  };

  /**
   * 应用宿主页面明暗主题。
   * @param {string} t 'light' | 'dark'
   */
  M.applyTheme = function (t) {
    const next = t === 'dark' ? 'dark' : 'light';
    this.theme = next;
    const root = document.documentElement;
    if (root) root.setAttribute('data-theme', next);
  };

  /** 接收来自内容脚本的窗口消息（会话切换、页面结构化内容等）。 */
  M.onPageMessage = function (e) {
    const d = e.data;
    if (!d || !d.type) return;
    if (d.type === 'panel_side') {
      this.panelSide = d.side === 'left' ? 'left' : 'right';
      return;
    }
    if (d.type === 'host_theme') {
      this.applyTheme(d.theme);
      return;
    }
    if (d.type === 'panel_visible') {
      log('收到面板可见性消息：' + (d.visible ? '打开' : '关闭'));
      this.setPanelVisible(d.visible);
      return;
    }
    if (d.type === 'auto_send_result') {
      return;
    }
    // 桥接相关消息（元素选择 / 点击 / 截屏结果）统一交给桥接模块处理，
    // 避免本文件过长，也让桥接的消息集中在一处
    if (this.handleBridgeMessage(d)) return;
    if (d.type === 'page_blocks') {
      // 先按站点切换（数据与设置都按站点隔离）
      if (d.profileId) this.profileId = d.profileId;
      this.applySite(d.siteKey);
      // 先取历史（读 storage），拿到后再用切片处理
      this.applyConversation(d.conversationId, d.conversationTitle, d.page_url, (ok) => {
        if (!ok) return;
        // atBottom：内容脚本算好的「视口是否在底部」，供滚动轮次自动执行复检
        this.ingestMessages(d.messages, d.reason, { atBottom: !!d.atBottom });
      });
    }
  };


  // ============================ 消息树 ============================

  /**
   * 新建节点。
   * @param {Object} msg 消息对象 { role, name, blocks }
   * @returns {Object} 节点
   */
  M.makeNode = function (msg) {
    return {
      role: msg.role || '',
      name: msg.name || '',
      blocks: msg.blocks || [],
      deleted: false,
      cards: {}
    };
  };

  /** 取某消息 id 在树中的 key（形如 '父id-子id'）；不存在返回空串。 */
  M.keyOfId = function (tree, id) {
    if (!tree || !id) return '';
    const keys = Object.keys(tree);
    for (let i = 0; i < keys.length; i++) {
      const cut = keys[i].indexOf('-');
      if (cut >= 0 && keys[i].slice(cut + 1) === id) return keys[i];
    }
    return '';
  };

  /** 取某消息 id 在树中的父 id；不存在返回空串。 */
  M.parentIdOf = function (tree, id) {
    const k = this.keyOfId(tree, id);
    return k ? k.slice(0, k.indexOf('-')) : '';
  };

  /**
   * 依据切片组装分支 key 列表。
   * 以切片末条为「最新」：沿消息树从它回溯到根，得到从根到它的路径。
   * @param {Object} conv 会话记录
   * @param {Array} slice 有序消息（当前切片）
   * @returns {Array<string>} 分支 key 列表（有序）
   */
  M.assembleBranchKeys = function (conv, slice) {
    const tree = conv.msgTree || {};
    const list = slice || [];
    if (!list.length) return [];
    const lastId = this.msgId(list[list.length - 1]);
    const path = [];
    const seen = {};
    let cur = lastId;
    while (cur && !seen[cur]) {
      seen[cur] = true;
      const k = this.keyOfId(tree, cur);
      if (!k) break;
      path.unshift(k);
      const pid = k.slice(0, k.indexOf('-'));
      if (pid === '0') break;
      cur = pid;
    }
    return path;
  };

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
   * 灌入一批网页消息。
   * 顺序：写消息树 → 记录可见区 key → 组装分支 → 为代码块建卡 → 自动执行 / 冲突回报 → 落盘。
   * @param {Array} messages 本次网页推送的消息（有序）
   * @param {string} [reason] 触发来源：'generate' / 'scroll' / 'switch' / 'manual'
   * @param {Object} [opts] 附加信息
   * @param {boolean} [opts.atBottom] 视口是否停在网页对话最新处（内容脚本算好传来）
   */
  M.ingestMessages = async function (messages, reason, opts) {
    const conv = this.curConv;
    const scrollOnly = reason === 'scroll';
    // 滚动轮次是否停在底部：自动执行复检的条件之一，其余来源不看它
    const atBottom = !!(opts && opts.atBottom);
    // 块列表归一化：非数组统一转成数组，避免后续遍历抛错
    (messages || []).forEach((m) => {
      if (!m) return;
      if (!Array.isArray(m.blocks)) {
        m.blocks = (m.blocks && typeof m.blocks === 'object') ? Object.values(m.blocks) : [];
      }
    });
    const incoming = (messages || []).filter((m) => m && m.blocks.length > 0);
    if (!incoming.length) {
      log('ingestMessages：切片为空，忽略');
      return;
    }
    // 记忆检查：出现「新的」真实用户发言则打开计数窗口（工具结果回传不算用户发言，
    // 同一用户发言重复出现不会重复开窗）。窗口内由 memoryIssueForRound 数 AI 发言轮次。
    this.noteUserTurn(incoming);
    // 打印过滤后各条指纹：与 sendPage 的 ids 同源，便于两边逐条比对。
    log('ingestMessages 收到 ' + incoming.length + ' 条（会话=' + this.activeConv
      + '，来源=' + (reason || 'generate')
      + '，ids=' + JSON.stringify(incoming.map((m) => this.msgId(m))) + '）');

    // 1) 写入消息树
    const up = this.upsertTree(conv, incoming, reason);

    // 不入树（断裂 / 碰撞 / 单节点 / 中间命中）：仍建卡供手动操作，但不自动执行。
    const notInTree = (up.mode === 'orphan' || up.mode === 'collision'
      || up.mode === 'single' || up.mode === 'middle');
    if (notInTree) log('本轮不入树（mode=' + up.mode + '）：建卡但跳过自动执行');

    // 2) 记录可见区切片的 key（有序）
    const visKeys = [];
    incoming.forEach((m) => {
      const k = this.keyOfId(conv.msgTree, this.msgId(m));
      if (k) visKeys.push(k);
    });
    conv.visibleKeys = visKeys;

    // 3) 组装分支：以切片末条为最新
    conv.branchKeys = this.assembleBranchKeys(conv, incoming);

    // 记忆检查：采样 memory 目录指纹并推进计数（细节见 05d_memory.js）。
    // 异步：需等后端指纹返回；带超时保护，后端不可达时不阻塞入库。
    const memoryIssue = await this.memoryIssueForRound(incoming, reason);

    // 4) 为代码块建卡并收集候选；随后处理重跑与自动执行（见两个辅助方法）
    const collected = this._buildCardsForIncoming(conv, incoming, reason, memoryIssue, scrollOnly);
    this._finalizeAutoExec(collected, notInTree, scrollOnly, atBottom);

    log('本轮处理完成：消息=' + incoming.length
      + '，可见=' + conv.visibleKeys.length
      + '，分支=' + conv.branchKeys.length
      + '，自动候选=' + collected.autoCandidates.length);
    if (this._persist) this._persist();
    // 上报给远程桥接层：仅 generate 来源（AI 刚说完新话）。
    // 走 WithMd 版本：先点复制按钮取带格式的 Markdown，再上报，
    // 这样推送到 QQ 的内容才保得住格式。
    this.reportToBridgeWithMd(reason);
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
      const key = this.keyOfId(conv.msgTree, this.msgId(m));
      const node = conv.msgTree[key];
      const holder = node || m;
      holder.cards = holder.cards || {};
      if (node) m.cards = holder.cards;
      const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
      const issue = this._messageIssue(m, mi, incoming.length, reason, memoryIssue, blocks);
      blocks.forEach((b) => {
        if (!b || b.type !== 'code' || !b.id) return;
        const exist = holder.cards[b.id];
        if (exist) {
          if (exist.isTool && issue && !exist.preIssue) exist.preIssue = issue;
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
        holder.cards[b.id] = this._makeCard(b, call, issue);
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
    if (toolCallCount > 1) {
      return {
        error: 'multiple_tool_calls',
        message: '本条回复包含多个工具调用代码块（共 ' + toolCallCount + ' 个）。'
          + '请一次只返回一个调用块，收到结果后再决定下一步。'
      };
    }
    if (m.role === 'assistant') {
      const issue = this.assistantQualityIssue(m);
      if (issue) return issue;
      // 记忆滞后提醒：仅贴在本轮最后一条助手输出上（更早的消息已无提醒意义）
      if (mi === total - 1 && memoryIssue) return memoryIssue;
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
   * 收尾：处理重复卡片重跑与「仅最新一张」的自动执行。
   * @param {Object} collected _buildCardsForIncoming 的返回
   * @param {boolean} notInTree 本轮是否不入树（不入树绝不自动执行）
   * @param {boolean} scrollOnly 是否滚动轮次
   * @param {boolean} atBottom 视口是否在底部
   */
  M._finalizeAutoExec = function (collected, notInTree, scrollOnly, atBottom) {
    const autoCandidates = collected.autoCandidates;
    // 4.5) 重复卡片重跑：严格受限的旁路，与常规自动执行互不重叠
    const rerunCard = collected.rerunCard;
    if (rerunCard && !notInTree && this.autoSendEnabled) {
      // 重置为待执行态：清掉已执行标记与上一轮结果，回到可被调度的初始状态
      rerunCard.executed = false;
      rerunCard.skipped = false;
      rerunCard.status = 'pending';
      rerunCard.error = null;
      rerunCard.phase = '';
      rerunCard.countdown = 0;
      if (rerunCard._cdTimer) { clearTimeout(rerunCard._cdTimer); rerunCard._cdTimer = null; }
      log('重复卡片重跑：来源=generate 且最新卡片已执行，重置后重新执行 '
        + (rerunCard.tool || rerunCard.id || ''));
      this.toast('检测到重复卡片，已重新执行最新卡片');
      this.scheduleExecute(rerunCard);
    }

    // 5) 自动执行：仅本轮最新的一张；不入树切片绝不自动执行。
    const runnable = autoCandidates.filter((c) => c && !c.skipped);
    if (!notInTree && this.autoSendEnabled) {
      if (!scrollOnly && runnable.length) {
        // 非滚动轮次：候选按本轮建卡顺序追加，末位即最新
        const newest = runnable[runnable.length - 1];
        if (newest && !newest.skipped) this.scheduleExecute(newest);
      } else if (scrollOnly) {
        this._maybeAutoExecOnScroll(collected.armedLast, atBottom);
      }
    }
    // 预备标记只生效一次
    autoCandidates.forEach((c) => { if (c) c.autoArmed = false; });
  };

  /**
   * 滚动轮次的自动执行复检：确认「视口就停在最新处」后才放行。
   * 需三道同时成立：自动开关已开、视口在底部、上膛的是最后一条消息上的卡片
   * 且仍是待执行态（未执行 / 未跳过 / 未在倒计时）。
   * @param {Object} armedLast 上膛的最新卡片
   * @param {boolean} atBottom 视口是否在底部
   */
  M._maybeAutoExecOnScroll = function (armedLast, atBottom) {
    const armedOk = !!(armedLast && armedLast.isTool && !armedLast.executed
      && !armedLast.skipped && !armedLast._cdTimer && armedLast.status === 'pending');
    const pass = atBottom && armedOk;
    console.log('[AI-Mirror][dialog][scroll复检] 自动=' + this.autoSendEnabled
      + '，在底部=' + atBottom + '，末尾卡片待执行=' + armedOk
      + ' → ' + (pass ? '放行自动执行' : '保持待执行'));
    if (pass) this.scheduleExecute(armedLast);
  };

  /** 保证卡片拥有唯一标记，供回传与复制共用同一份文本。 */
  M.ensureNonce = function (holder) {
    if (!holder.nonce) {
      holder.nonce = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
    }
    return holder.nonce;
  };

})();
