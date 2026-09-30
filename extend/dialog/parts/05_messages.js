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

  /** 判断某工具是否为 silent（仅不在抽屉生成工具卡片；结果照常回传）。 */
  M.toolSilent = function (name) {
    const t = (this.tools || []).find((x) => x.name === name);
    return !!(t && t.silent);
  };

  /**
   * 判断代码块是否为一次工具调用：内容是 { tool, parameters } 且带 bridge-chat-call 即算。
   * 安全性由调用方保证：只有「助手消息」里的代码块才会被判为工具调用。
   */
  M.parseToolCall = function (block) {
    if (!block || block.type !== 'code') return null;
    const src = String(block.code || '').trim();
    if (!src || src.charAt(0) !== '{') return null; // 快速排除非 JSON
    try {
      const obj = JSON.parse(src);
      if (obj && typeof obj === 'object' && obj.tool && obj.type === 'bridge-chat-call') {
        return { tool: String(obj.tool), parameters: obj.parameters || {} };
      }
    } catch (e) { /* 不是工具调用，按普通代码块渲染 */ }
    return null;
  };

  /**
   * 判断一条消息是否为外部调用信封（external-call）。
   * 外部卡片发送到网页后，会以一条 user 消息落在对话里；这条消息即卡片的
   * 本体，用于在镜像区还原为卡片、在列表里做颜色标记。
   * 信封可能被解析成 code 或 text 两种块形态，两者都识别。
   * @param {Object} m 消息对象
   * @returns {Object|null} { nonce, request }；非外部调用返回 null
   */
  M.parseExternalCall = function (m) {
    if (!m || m.role !== 'user') return null;
    const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (!b) continue;
      const src = String(b.code || b.text || '').trim();
      if (!src || src.charAt(0) !== '{') continue;
      try {
        const obj = JSON.parse(src);
        if (obj && typeof obj === 'object' && obj.type === 'external-call') {
          return {
            nonce: obj.nonce || '',
            request: obj.request || ''
          };
        }
      } catch (e) { /* 非信封内容，继续找下一个块 */ }
    }
    return null;
  };

  /** 消息 id：直接复用内容指纹。指纹以 'm' 开头、不含分隔符 '-'。 */
  M.msgId = function (m) {
    return this.messageFingerprint(m);
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
  M.ingestMessages = function (messages, reason, opts) {
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
    // 记忆检查：检测到用户真实发言即启动（工具结果回传、外部卡片信封不算用户发言）
    if (incoming.some((m) => this.isRealUserMessage(m))) this.armMemoryCheck();
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

    // 记忆检查：仅在本轮为 generate 且存在可回传工具卡片时判定（细节见 05d_memory.js）
    const memoryIssue = this.memoryIssueForRound(incoming, reason);

    // 4) 为代码块建卡，并收集自动执行候选。
    //   入树的消息：卡片写在节点上，并与切片消息共享同一份卡片表；
    //   不入树的消息：卡片直接写在切片消息上（供手动操作）。
    //   检测出的问题（多调用冲突 / 回复质量 / 记忆滞后）不另立流程，直接作为该条卡片的结果。
    const autoCandidates = [];
    // 滚动轮次里被「上膛」的那张最新卡片（仅最后一条消息上的），供底部复检使用
    let armedLast = null;
    incoming.forEach((m, mi) => {
      const key = this.keyOfId(conv.msgTree, this.msgId(m));
      const node = conv.msgTree[key];
      const holder = node || m;
      holder.cards = holder.cards || {};
      if (node) m.cards = holder.cards;
      const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
      // 统计本条助手消息内的工具调用块数量：一次回复出现多个调用块属非法用法。
      let toolCallCount = 0;
      if (m.role === 'assistant') {
        blocks.forEach((b) => {
          if (b && b.type === 'code' && b.id && this.parseToolCall(b)) toolCallCount += 1;
        });
      }
      // 本条消息的问题：多调用冲突优先，其次回复质量。二者都作为卡片的结果。
      // 只在 AI 生产结束场景检测：其它场景要么是回看历史，要么是切换 / 手动解析，
      // 都不该给已有卡片贴问题标签。
      let issue = null;
      if (reason === 'generate') {
        if (toolCallCount > 1) {
          issue = {
            error: 'multiple_tool_calls',
            message: '本条回复包含多个工具调用代码块（共 ' + toolCallCount + ' 个）。'
              + '请一次只返回一个调用块，收到结果后再决定下一步。'
          };
        } else if (m.role === 'assistant') {
          issue = this.assistantQualityIssue(m);
        }
        // 记忆滞后提醒：仅贴在本轮最后一条助手输出上（更早的消息已无提醒意义）
        if (!issue && m.role === 'assistant' && mi === incoming.length - 1 && memoryIssue) {
          issue = memoryIssue;
        }
      }
      blocks.forEach((b) => {
        if (!b || b.type !== 'code' || !b.id) return;
        const exist = holder.cards[b.id];
        if (exist) {
          // 已有卡片：补记问题、按需纳入自动候选
          if (exist.isTool && issue && !exist.preIssue) exist.preIssue = issue;
          if (exist.autoArmed) this.collectAutoCandidate(autoCandidates, exist);
          return;
        }
        // 只把「助手回答」里的代码块当成可执行的工具调用（用户消息里的示例块不建卡）
        const call = m.role === 'assistant' ? this.parseToolCall(b) : null;
        const silent = !!(call && this.toolSilent(call.tool));
        const card = {
          id: b.id,
          lang: b.lang || '',
          phase: '',
          code: b.code || '',
          isTool: !!call,
          silent: silent,
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
          // hostPageUrl：承载本对话的顶层页面地址（chat-bridge 所在页，如 chat.deepseek.com/xxx）。
          // 命令在目标页超时逸散时，后端据此优先回投本页面；
          // 缺这个字段时，后端只能随机投给其他页面，出现「发给 B 却落到 C」。
          hostPageUrl: this.page_url || ''
        };
        holder.cards[b.id] = card;
        if (call) {
          if (scrollOnly) {
            // 滚动轮次里，只有「最后一条消息」上的新卡片才预备自动执行。
            // 记下这张卡片的响应式代理：复检通过后要执行的是界面真正监听的那份。
            if (mi === incoming.length - 1) {
              card.autoArmed = true;
              armedLast = holder.cards[b.id];
            }
          } else {
            // 从响应式容器回读卡片再入候选：holder.cards[b.id] 是 Vue 代理，
            // 后续倒计时改的是界面真正监听的那份；直接用局部 card 会改到原始对象，
            // 导致倒计时数字不刷新而执行仍照常发生。
            this.collectAutoCandidate(autoCandidates, holder.cards[b.id]);
          }
        }
      });
    });

    // 5) 自动执行：仅本轮最新的一张；不入树切片绝不自动执行。
    const runnable = autoCandidates.filter((c) => c && !c.skipped);
    if (!notInTree && this.autoSendEnabled) {
      if (!scrollOnly && runnable.length) {
        // 非滚动轮次：候选按本轮建卡顺序追加，末位即最新
        const newest = runnable[runnable.length - 1];
        if (newest && !newest.skipped) this.scheduleExecute(newest);
      } else if (scrollOnly) {
        // 滚动轮次：原本一律不自动执行，以免回滚历史时把旧卡片误当最新触发。
        // 这里补三道复检，确认「视口就停在最新处」后才放行——回滚误触发的前提即不成立：
        //   1) 自动开关已打开；
        //   2) 视口在底部（内容脚本按「滚动到底部按钮」是否存在判定，随推送传来）；
        //   3) 上膛的是最后一条消息上的卡片，且仍是待执行态（未执行 / 未跳过 / 未在倒计时）。
        const armedOk = !!(armedLast && armedLast.isTool && !armedLast.executed
          && !armedLast.skipped && !armedLast._cdTimer && armedLast.status === 'pending');
        const pass = atBottom && armedOk;
        // 进入该分支即打印一行，便于核对判定过程（后续可在此补充更多诊断）
        console.log('[AI-Mirror][dialog][scroll复检] 自动=' + this.autoSendEnabled
          + '，在底部=' + atBottom + '，末尾卡片待执行=' + armedOk
          + ' → ' + (pass ? '放行自动执行' : '保持待执行'));
        if (pass) this.scheduleExecute(armedLast);
      }
    }
    // 预备标记只生效一次
    autoCandidates.forEach((c) => { if (c) c.autoArmed = false; });

    log('本轮处理完成：消息=' + incoming.length
      + '，可见=' + conv.visibleKeys.length
      + '，分支=' + conv.branchKeys.length
      + '，自动候选=' + autoCandidates.length);
    if (this._persist) this._persist();
    // 上报给远程桥接层：仅 generate 来源（AI 刚说完新话）。
    // 走 WithMd 版本：先点复制按钮取带格式的 Markdown，再上报，
    // 这样推送到 QQ 的内容才保得住格式。
    this.reportToBridgeWithMd(reason);
  };

  /** 保证卡片拥有唯一标记，供回传与复制共用同一份文本。 */
  M.ensureNonce = function (holder) {
    if (!holder.nonce) {
      holder.nonce = Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
    }
    return holder.nonce;
  };

})();
