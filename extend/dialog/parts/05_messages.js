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
    // 另取一份「全部工具（含已下线）」供设置页管理。
    // /tools 是给 AI 看的目录，会滤掉下线工具；设置页若也用它，
    // 工具一旦下线就从界面消失、再也无法重新上线（历史缺陷）。
    await this.fetchAllTools();
  };

  /**
   * 拉取全部内置工具（含已下线），供设置页管理开关。
   *
   * 失败时保持上一次的结果，不清空——否则后端短暂不可达会让设置页的工具列表闪空。
   */
  M.fetchAllTools = async function () {
    try {
      const data = await D.apiFetch(this, '/tools/all', {
        headers: { 'Accept': 'application/json' }
      });
      const list = (data && data.tools) || [];
      if (list.length) this.allTools = list;
      log('管理视图工具数：' + (this.allTools || []).length);
    } catch (e) {
      log('拉取全部工具失败（保持原值）：' + e);
    }
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
      cards: {},
      // files：本条消息附带的文件描述（read_file 的产物）。
      // 块类型里没有「文件」这一种，故单列字段承载；渲染时据此给出「重新粘贴」按钮。
      // 只存文件名 / 路径 / 来源类型，不含文件内容，体积可忽略。
      files: Array.isArray(msg.files) ? msg.files : [],
    };
  };

  // 树查询函数（keyOfId / parentIdOf / isTreeTail / assembleBranchKeys）
  // 已迁至 05h_tree_query.js，挂在 D.methods 上，调用方式不变。

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
      // 取该消息的文字：用户消息多为 paragraph 块；工具截图回传的是
      // bridge-chat-res JSON 文本，渲染后可能落在 code 块，故一并采集。
      const text = (m.blocks || []).filter(function (b) {
        return b && (b.type === 'paragraph' || b.type === 'code');
      }).map(function (b) { return b.text || b.code || ''; }).join(' ').trim();
      if (!text) return;
      for (let i = 0; i < pend.length; i++) {
        if (used.indexOf(i) >= 0) continue;
        const p = pend[i];
        // 按文字包含匹配：网页回显的文字与卡片文字一致即可命中
        if (p.text && text.indexOf(p.text) >= 0) {
          used.push(i);
          // 按登记的目录类型选取图路由：工具截图存 screenshots 目录，
          // 走 screenshot-file；网页图片走 image-file。两者的图片文件名不通用。
          const base = (p.dir === 'screenshot')
            ? '/api/web/screenshot-file/'
            : '/api/web/image-file/';
          const imgBlocks = (p.names || []).slice().reverse().map(function (n) {
            return { type: 'image', src: base + encodeURIComponent(n), alt: '图片' };
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
    (messages || []).forEach((m) => {
      if (m && !Array.isArray(m.blocks)) m.blocks = (m.blocks && typeof m.blocks === 'object') ? Object.values(m.blocks) : [];
    });
    const incoming = (messages || []).filter((m) => m && m.blocks.length > 0);
    if (!incoming.length) { log('ingestMessages：切片为空，忽略'); return; }
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
    // 挂载待处理资产（图片 / 文件描述），必须在入树之前
    try { this._attachPendingImages(conv, incoming); } catch (e) { log('挂载图片失败：' + e); }
    try { this._attachPendingFiles(conv, incoming); } catch (e) { log('挂载文件失败：' + e); }
    const beforeNodes = Object.keys(conv.msgTree).length;
    const isInitialLoad = beforeNodes === 0;
    // 入树前查「末条消息」是否已在树中。不能用整批查重：切片含历史消息，
    // 用 some() 会恒为 true，把真正的新回复也挡掉（曾致 QQ 收不到消息）。
    const tailMsg = incoming[incoming.length - 1];
    const tailInTree = !!(tailMsg && this.keyOfId(conv.msgTree, this.msgId(tailMsg)));
    const up = this.upsertTree(conv, incoming, reason, atBottom);
    const addedNodes = Object.keys(conv.msgTree).length > beforeNodes;

    // 不入树（断裂 / 碰撞 / 单节点重复 / 中间命中）：仍建卡供手动操作，但不自动执行。
    // 注意单节点有三种结果：single_new / single_collision 均已入树，只有 single_dup 未入树。
    const notInTree = (up.mode === 'orphan' || up.mode === 'collision'
      || up.mode === 'single_dup' || up.mode === 'middle');
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
    // 新鲜回复判定：只认「末条 AI 消息此前不在树中」。
    // scrollOnly 排除：向上滚动加载的更早历史，末条同样不在树里，
    // 若放行会导致回看历史却重新复制并上报。
    const isFreshReply = !isInitialLoad && !scrollOnly && addedNodes
      && lastIsAssistant && !tailInTree;
    this._logQualityDiagnosis(reason, addedNodes, lastIsAssistant, isFreshReply, incoming);

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
   * 诊断日志：记录新鲜回复判定要素与末条消息的块类型。
   * 用途——排查「AI 回复只含代码块却不告警」：质量检测入口首行为
   * if (!isFreshReply) return null，本判定为 false 时全部检测被跳过。
   * 消息滚动快、来不及抓现场，故把关键取值落进日志，事后可查。
   * @param {string} reason 采集来源
   * @param {boolean} addedNodes 本轮是否有新增节点
   * @param {boolean} lastIsAssistant 末条是否为助手消息
   * @param {boolean} isFreshReply 新鲜回复判定结果
   * @param {Array} incoming 本轮消息切片
   */
  M._logQualityDiagnosis = function (reason, addedNodes, lastIsAssistant, isFreshReply, incoming) {
    try {
      const tail = incoming.length ? incoming[incoming.length - 1] : null;
      const tailTypes = tail ? window.AIMirrorDomUtils.toArray(tail.blocks).map((b) => (b && b.type) || '?').join(',') : '';
      log('质量诊断：reason=' + reason + ' addedNodes=' + addedNodes + ' lastIsAssistant=' + lastIsAssistant
        + ' isFreshReply=' + isFreshReply + ' 末条role=' + (tail && tail.role) + ' 块类型=[' + tailTypes + ']');
    } catch (e) { /* 诊断日志失败不影响主流程 */ }
  };

  /** 本轮若属 AI 新鲜回复，则上报给远程桥接层。@param {boolean} isFreshReply */
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
    // 4.5) 已执行卡片的处置：保持已执行态，不退回待执行。
    // 执行权只属于「本轮最后一条消息里的卡片」；一张卡片执行完成后，
    // 其执行结果就是对这次调用的最终答复，重新采集到同一代码块时沿用该结果。
    // 否则 /rall 这类刷新会重新采集历史消息，把已执行卡片重置成待执行并再跑一遍。
    const rerunCard = collected.rerunCard;
    if (rerunCard && !notInTree) {
      log('已执行卡片保持完成态：'
        + (rerunCard.tool || rerunCard.id || ''));
    }

    // 5) 自动执行：仅本轮最新的一张；不入树切片绝不自动执行。
    // 已执行过的卡片不再进候选：自动执行只针对「尚未执行」的新卡片。
    // 缺这一条时，刷新后重建的卡片若签名命中失败就会把历史卡片重跑一遍。
    const runnable = autoCandidates.filter((c) => c && !c.skipped && !c.executed);
    // 自动执行决策留痕：这是排查「自动流程停止」的核心断点，逐条件说明为何执行/不执行。
    if (this._convLoading && this._convLoading[this.activeConv]) {
      // 会话仍在加载：签名库尚未恢复，此时判不出「哪些已执行」，
      // 一律不自动执行，避免把历史卡片当成新卡片重跑。
      log('自动执行决策：会话仍在加载，跳过（候选=' + runnable.length + '）');
    } else if (notInTree) {
      log('自动执行决策：本轮不入树，跳过（候选=' + runnable.length + '）');
    } else if (!this.autoSendEnabled) {
      log('自动执行决策：自动开关关，跳过（候选=' + runnable.length + '）');
    } else if (!scrollOnly && runnable.length) {
      // 非滚动轮次：候选按本轮建卡顺序追加，末位即最新
      const newest = runnable[runnable.length - 1];
      // 硬门槛：卡片必须属于「会话树末条」消息。
      // 切片末条不等于会话末条——刷新后切片可能被截断或混入历史消息，
      // 末位看似最新、实则是旧消息，此时执行等于让历史卡片重跑。
      const conv = this.ensureConv(this.activeConv);
      const isTail = newest && this.isTreeTail(conv, newest.msgId);
      if (!isTail) {
        // 不 return：后面还要清 autoArmed 残留标记，中途退出会让标记留到下一轮。
        log('自动执行决策：卡片不属于会话末条，拒绝执行 id=' + (newest && newest.id)
          + ' 工具=' + (newest && newest.tool) + ' msgId=' + (newest && newest.msgId));
      } else {
        log('自动执行决策：执行最新卡片 id=' + (newest.id || '(无)')
          + ' 工具=' + (newest.tool || '(非工具)') + '（候选=' + runnable.length + '）');
        if (newest && !newest.skipped) this.scheduleExecute(newest);
      }
    } else if (scrollOnly) {
      this._maybeAutoExecOnScroll(collected.armedLast, atBottom);
    } else {
      log('自动执行决策：无候选，不执行');
    }
    // 预备标记只生效一次。
    // 除了候选池里的，还要清掉本轮建卡时被上膛、但未进池的卡片（如滚动轮次视口不在底部），
    // 否则标记残留到下一轮，历史卡片可能在后续采集里被重新认领执行。
    autoCandidates.forEach((c) => { if (c) c.autoArmed = false; });
    if (collected.armedLast) collected.armedLast.autoArmed = false;
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
    // 硬门槛：上膛卡片必须属于会话树末条，否则任何滚动场景都不放行。
    // 与「切片末条」无关——切片末位在向上滚动加载历史时可能是旧消息。
    const conv = this.ensureConv(this.activeConv);
    const tailOk = !!(armedLast && this.isTreeTail(conv, armedLast.msgId));
    if (armedLast && !tailOk) {
      log('自动执行复检（滚动）：卡片不属于会话末条，拒绝 msgId=' + (armedLast.msgId || '(空)'));
    }
    // 自动开关必须纳入判定：原实现只在日志里打印了它，没参与运算，
    // 导致开关关闭时滚动路径照样执行卡片——日志写着「自动开关=false → 放行执行」，自相矛盾。
    const pass = this.autoSendEnabled && atBottom && armedOk && tailOk;
    // 自动流程是否放行的关键判定：记录四个条件与结论，便于排查「自动流程停止」。
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
