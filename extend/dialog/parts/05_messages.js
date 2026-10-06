// 模块：extend/dialog/parts/05_messages.js
// 用途：消息接收与消息树核心：工具列表拉取、网页消息接收与解析、
//       分支组装、灌入切片的编排、自动执行收尾。
//       消息树写入口 upsertTree 在 05b_tree.js；
//       建卡与质量检测在 05g_cards.js。
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
      // source：来源标记（user / assistant / tool），建节点时算一次并存储，
      // 之后所有判定读它，不再各自扫字符串反推（见 05f_parse.js 的 msgSource）。
      source: this.msgSource(msg),
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
   * 把「服务端图片名」挂到对应消息节点上（方案 2 的核心）。
   *
   * 背景：网页页面里用户发的图常常不是 <img> 元素，content 脚本提取不到，
   * 抽屉两处因此没图。改法：图片卡片贴图时记下「文字 → 图片名」关联
   * （见 01e_bridge_actions.sendQqImageCard），本函数在该用户消息入树后，
   * 按文字匹配把 image 块补进消息的 blocks，渲染时即按名从后端取图。
   * 不依赖网页 DOM，网页改版也不受影响。
   * @param {Object} conv 会话对象（含 pendingImages 关联表）
   * @param {Array} incoming 本轮入树的消息
   */
  M._attachPendingImages = function (conv, incoming) {
    const pend = (conv && conv.pendingImages) || [];
    if (!pend.length) return;
    // 图片地址用「相对路径」：浏览器按当前访问的主机自动解析，
    // 手机 / 别的电脑访问也能取到图。此前拼 config.flaskUrl（多为 127.0.0.1），
    // 跨设备时该地址指向设备自身，图片必然加载失败。
    const used = [];
    (incoming || []).forEach((m) => {
      if (!m || m.role !== 'user') return;
      // 取该消息的文字：用户消息多为 paragraph 块
      const text = (m.blocks || []).filter(function (b) { return b && b.type === 'paragraph'; })
        .map(function (b) { return b.text || ''; }).join(' ').trim();
      if (!text) return;
      for (let i = 0; i < pend.length; i++) {
        if (used.indexOf(i) >= 0) continue;
        const p = pend[i];
        // 按文字包含匹配：网页回显的文字与卡片文字一致即可命中
        if (p.text && text.indexOf(p.text) >= 0) {
          used.push(i);
          const imgBlocks = (p.names || []).slice().reverse().map(function (n) {
            return { type: 'image', src: '/api/web/image-file/' + encodeURIComponent(n), alt: '图片' };
          });
          // 双写之一：改本轮 incoming 的消息对象
          imgBlocks.slice().reverse().forEach(function (b) { m.blocks.unshift(b); });
          // 双写之二：同步到「已在树中」的同一条消息节点。
          // 必要性：消息可能先于图片卡片入树，而 upsertTree 对「整片已存在」
          // 的分支直接返回、不更新节点 blocks，只改 incoming 不会反映到镜像区。
          try {
            const tk = this.keyOfId(conv.msgTree, this.msgId(m));
            const tn = tk && conv.msgTree[tk];
            if (tn && tn !== m && Array.isArray(tn.blocks)) {
              imgBlocks.slice().reverse().forEach(function (b) {
                tn.blocks.unshift({ type: b.type, src: b.src, alt: b.alt });
              });
            }
          } catch (e) { log('图片同步到树失败：' + e); }
          break;
        }
      }
    });
    // 命中的关联移除，避免同一张图被重复挂到后续消息上
    if (used.length) {
      conv.pendingImages = pend.filter(function (_, i) { return used.indexOf(i) < 0; });
    }
  };

  M.assembleBranchKeys = function (conv, slice) {
    const tree = conv.msgTree || {};
    const list = slice || [];
    if (!list.length) return [];
    const ids = list.map((m) => this.msgId(m));
    // 切片内「当前 id → 前一条 id」映射：回溯时优先走本轮真实边。
    const prevInSlice = {};
    for (let i = 1; i < ids.length; i++) prevInSlice[ids[i]] = ids[i - 1];
    const path = [];
    const seen = {};
    let cur = ids[ids.length - 1];
    while (cur && !seen[cur]) {
      seen[cur] = true;
      let key = '';
      // 优先用切片内相邻边；碰撞时 keyOfId 会返回旧 key 致回溯变浅。
      const prev = prevInSlice[cur];
      if (prev && tree[prev + '-' + cur]) key = prev + '-' + cur;
      if (!key) key = this.keyOfId(tree, cur);
      if (!key) break;
      path.unshift(key);
      const pid = key.slice(0, key.indexOf('-'));
      if (pid === '0') break;
      cur = pid;
    }
    return path;
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
    // 同一用户发言重复出现不会重复开窗）。窗口内由 memoryIssueForRound 数 AI 生成轮次。
    this.noteUserTurn(incoming);
    // 打印过滤后各条指纹：与 sendPage 的 ids 同源，便于两边逐条比对。
    log('ingestMessages 收到 ' + incoming.length + ' 条（会话=' + this.activeConv
      + '，来源=' + (reason || 'generate')
      + '，ids=' + JSON.stringify(incoming.map((m) => this.msgId(m))) + '）');

    // 1) 写入消息树
    //    atBottom 一并传入：末路兜底需要它判断「用户是否正看着最新处」，
    //    只有 generate 且在底部时，才允许把找不到锚点的整片接到分支末端。
    //    beforeNodes 用于判断本轮是否真的有新节点入库（供上报解耦用，见末尾）。
    // 方案 2：把服务端图片按「文字关联」挂到对应用户消息的块上，
    // 必须放在入树之前——入树后消息块已被引用，再改可能来不及参与本轮渲染。
    try { this._attachPendingImages(conv, incoming); } catch (e) { log('挂载图片失败：' + e); }
    const beforeNodes = Object.keys(conv.msgTree).length;
    const up = this.upsertTree(conv, incoming, reason, atBottom);
    const addedNodes = Object.keys(conv.msgTree).length > beforeNodes;

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

    // 「本轮是否属 AI 新鲜回复」——检测与上报共用同一判定。
    // 原漏告警根因：检测只看 reason（非 generate 直接跳过），上报却强制 generate，
    // 轮询错过「生成中→空闲」跳变、消息以 scroll 采集时，两者分叉：
    // 网页看得到这条消息，语音缺失却不告警。此处统一判定，两条路同进同出。
    const lastIsAssistant = incoming.length
      && incoming[incoming.length - 1].role === 'assistant';
    const isFreshReply = (reason === 'generate') || (addedNodes && lastIsAssistant);

    // 3.5) 记忆确认提醒：数 AI 生成轮次，达到阈值则产出提醒（细节见 05d_memory.js）。
    // 纯轮次计数，不做异步指纹采样，故不再需要在入库前 await。
    const memoryIssue = this.memoryIssueForRound(incoming, isFreshReply);

    // 4) 为代码块建卡并收集候选；随后处理重跑与自动执行（见 05g_cards.js 与下方收尾）
    const collected = this._buildCardsForIncoming(conv, incoming, reason, memoryIssue, scrollOnly, isFreshReply);
    this._finalizeAutoExec(collected, notInTree, scrollOnly, atBottom);

    log('本轮处理完成：消息=' + incoming.length
      + '，可见=' + conv.visibleKeys.length
      + '，分支=' + conv.branchKeys.length
      + '，自动候选=' + collected.autoCandidates.length);
    if (this._persist) this._persist();
    // 上报给远程桥接层（条件与去重细节见 _reportFreshReply）
    this._reportFreshReply(isFreshReply);
  };

  /**
   * 本轮若属 AI 新鲜回复，则上报给远程桥接层。
   * 抽成子函数以控制 ingestMessages 行数；判定与质量检测共用同一 isFreshReply。
   * 原实现只在 generate 来源上报，轮询错过「生成中→空闲」跳变、消息以 scroll
   * 采集时会漏报；解耦为「本轮确属 AI 新增内容即上报」，后端按消息 id 去重。
   * @param {boolean} isFreshReply 本轮是否属 AI 新鲜回复
   */
  M._reportFreshReply = function (isFreshReply) {
    if (isFreshReply) this.reportToBridgeWithMd('generate');
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
    // 自动执行决策留痕：这是排查「自动流程停止」的核心断点，逐条件说明为何执行/不执行。
    if (notInTree) {
      log('自动执行决策：本轮不入树，跳过（候选=' + runnable.length + '）');
    } else if (!this.autoSendEnabled) {
      log('自动执行决策：自动开关关，跳过（候选=' + runnable.length + '）');
    } else if (!scrollOnly && runnable.length) {
      // 非滚动轮次：候选按本轮建卡顺序追加，末位即最新
      const newest = runnable[runnable.length - 1];
      log('自动执行决策：执行最新卡片 id=' + (newest.id || '(无)')
        + ' 工具=' + (newest.tool || '(非工具)') + '（候选=' + runnable.length + '）');
      if (newest && !newest.skipped) this.scheduleExecute(newest);
    } else if (scrollOnly) {
      this._maybeAutoExecOnScroll(collected.armedLast, atBottom);
    } else {
      log('自动执行决策：无候选，不执行');
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
    // 自动流程是否放行的关键判定：记录三个条件与结论，便于排查「自动流程停止」。
    log('自动执行复检（滚动）：自动开关=' + this.autoSendEnabled
      + '，在底部=' + atBottom + '，末尾卡片待执行=' + armedOk
      + ' → ' + (pass ? '放行执行' : '不执行'));
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
