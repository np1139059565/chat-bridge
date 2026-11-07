// 模块：extend/dialog/parts/04_sessions.js
// 用途：多会话的状态管理：会话创建、切换、恢复、持久化与清空；
//       条目删除、栏宽调节、条目跳转与导出在 04b_sessions.js。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 数据模型（与会话相关）：
//   会话 = { title, page_url, msgTree, visibleKeys, branchKeys, externalCards, orphanSlice, updatedAt }
//   消息树节点 = { role, name, blocks, deleted, cards }
// 卡片状态只在节点内。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /** 确保某会话的记录对象存在，并补齐统一所需字段。 */
  M.ensureConv = function (id) {
    const key = id || '__default__';
    if (!this.conversations[key]) {
      this.conversations[key] = {
        title: '', page_url: '',
        msgTree: {}, visibleKeys: [], branchKeys: [], externalCards: [], orphanSlice: [],
        updatedAt: 0
      };
    }
    const conv = this.conversations[key];
    if (!conv.msgTree || typeof conv.msgTree !== 'object') conv.msgTree = {};
    if (!Array.isArray(conv.visibleKeys)) conv.visibleKeys = [];
    if (!Array.isArray(conv.branchKeys)) conv.branchKeys = [];
    if (!Array.isArray(conv.externalCards)) conv.externalCards = [];
    if (!Array.isArray(conv.orphanSlice)) conv.orphanSlice = [];
    return conv;
  };

  /**
   * 消息内容指纹：role + 名称 + 各块内容的稳定摘要。
   * 相同内容的两条消息指纹相同，因此不能当唯一序号键。
   */
  M.messageFingerprint = function (m) {
    return window.AIMirrorDomUtils.messageFingerprint(m);
  };

  // ---------- 卡片查找：卡片状态存在消息树节点内，这里提供统一入口 ----------

  /** 遍历当前会话消息树的所有卡片，回调 (card, node, blockId)。 */
  M.eachCard = function (conv, fn) {
    const tree = (conv && conv.msgTree) || {};
    Object.keys(tree).forEach((k) => {
      const node = tree[k];
      const cards = (node && node.cards) || {};
      Object.keys(cards).forEach((bid) => { fn(cards[bid], node, bid); });
    });
  };

  /** 按代码块 id 查找卡片；返回卡片对象或 null。 */
  M.findCard = function (id) {
    if (!id) return null;
    let found = null;
    this.eachCard(this.curConv, (c, node, bid) => {
      if (!found && bid === id) found = c;
    });
    return found;
  };

  /** 汇总当前会话全部卡片为 { 代码块id: 卡片 }。 */
  M.allCards = function () {
    const out = {};
    this.eachCard(this.curConv, (c, node, bid) => { out[bid] = c; });
    return out;
  };

  // ---------- 会话切换 / 恢复 ----------

  /**
   * 网页端切换会话时调用。
   * 正常流程：先从 URL 得到会话 id（由内容脚本透传）；
   *   · 无 id → 什么都不做；
   *   · 有 id → 从 storage 读该会话历史，读完后回调，再由调用方按切片处理。
   * @param {string} convId 会话 id（无则为空）
   * @param {string} title 会话标题
   * @param {string} page_url 页面地址
   * @param {Function} [done] 历史就绪后的回调，入参 true 表示可以继续处理切片
   */
  M.applyConversation = function (convId, title, page_url, done) {
    const id = convId || '';
    const cb = typeof done === 'function' ? done : function () {};
    // 无 id：什么都不做，保留当前状态，等带 id 的推送再来
    if (!id) {
      log('applyConversation：未取得会话 id，跳过本次处理');
      cb(false);
      return;
    }
    if (id === this.activeConv && this._convReady && this._convReady[id]) {
      // 已在本会话且历史已就绪：仅更新标题，直接处理切片
      const conv = this.ensureConv(id);
      if (title) conv.title = title;
      if (page_url) conv.page_url = page_url;
      cb(true);
      return;
    }
    // 切会话必须清掉跨轮暂存的待执行卡片：它属于上一个会话，
    // 若留在状态里，下一个会话的推送会把它当成候选尝试执行，造成跨会话误执行。
    this._pendingAutoExec = null;
    // 切换到新会话：先关掉自动开关，再建立会话对象、读历史。
    // 为什么必须关：自动开关开着时，新会话里一旦出现待执行卡片，
    // 会被自动倒计时执行并回传——用户此刻只是切了会话，并非要执行它，
    // 属于误执行。关开关同时会清掉已排的倒计时（见 setAutoSendEnabled）。
    // 仅在「从某个已就绪会话切到另一个会话」时触发，避免首次加载误报 toast。
    if (this.autoSendEnabled && this.activeConv && this.activeConv !== id) {
      this.setAutoSendEnabled(false);
    }
    this.activeConv = id;
    const conv = this.ensureConv(id);
    if (title) conv.title = title;
    if (page_url) conv.page_url = page_url;
    this.loadConversation(id, cb);
  };

  /**
   * 从本地存储恢复会话历史（消息树 + 外部卡片 + 执行状态）。
   * 恢复完成后调用 done(true)，由调用方按切片继续处理。
   * @param {string} convId 会话 id
   * @param {Function} done 完成回调
   */
  /**
   * 安排一次会话加载失败后的重试。
   *
   * 网络失败不能当成「后端没有这个会话」：此时内存里的签名库还是空的，
   * 一旦解除写回禁令，就会用空库覆盖后端存档，刷新一次毁一次。
   * 故本方法只负责排期重取，不解锁、不置就绪，由重新进入 loadConversation
   * 成功分支时统一解锁。
   *
   * @param {string} convId 会话 id
   * @param {string} err 失败原因（仅用于日志）
   * @param {Function} cb 完成回调，先以 false 通知调用方本次未就绪
   */
  M._scheduleConvRetry = function (convId, err, cb) {
    const self = this;
    // 每会话独立计数，用于算指数退避的等待时长
    self._convRetry = self._convRetry || {};
    const n = (self._convRetry[convId] || 0) + 1;
    self._convRetry[convId] = n;
    // 3s、6s、12s、24s，之后固定 30s 封顶
    const wait = Math.min(3000 * Math.pow(2, n - 1), 30000);
    log('loadConversation 网络失败：' + err
      + '，第 ' + n + ' 次重试将在 ' + (wait / 1000) + ' 秒后');
    // 先告知调用方本次未就绪
    cb(false);
    setTimeout(function () {
      // 用户已切走则放弃重试；切回时会重新触发加载
      if (self.activeConv === convId && self._convLoading && self._convLoading[convId]) {
        log('loadConversation 重试加载：' + convId);
        self.loadConversation(convId, cb);
      }
    }, wait);
  };

  /**
   * 把后端取回的会话存档并入内存里的会话对象。
   *
   * 合并口径是「后端为准、只增不减」：
   *   - 消息树按节点覆盖，保留节点自带卡片状态；
   *   - 外部卡片按 id 去重追加；
   *   - 执行签名库只把为真的条目并入，不清掉内存里已有的记录；
   *   - 可见键、分支键、孤立切片按数组整体替换。
   *
   * @param {Object} conv    内存中的会话对象（就地修改）
   * @param {Object} saved   后端返回的存档
   * @param {string} convId  会话 id（仅用于诊断日志）
   */
  M._mergeSavedConv = function (conv, saved, convId) {
    // 消息树：并入内存树（后端为准），保留节点自带卡片状态
    if (saved.msgTree && typeof saved.msgTree === 'object') {
      Object.keys(saved.msgTree).forEach((k) => {
        const node = saved.msgTree[k];
        // 空节点跳过，避免把内存里已有的节点抹成空
        if (!node) return;
        conv.msgTree[k] = node;
      });
    }
    // 标题与页面地址只补空，不覆盖内存里已有的值
    if (saved.title) conv.title = conv.title || saved.title;
    if (saved.page_url) conv.page_url = conv.page_url || saved.page_url;
    // 外部卡片：按 id 去重追加，不重复登记同一张卡
    if (Array.isArray(saved.externalCards)) {
      const known = new Set((conv.externalCards || []).map((c) => c && c.id));
      saved.externalCards.forEach((c) => {
        if (c && c.id && !known.has(c.id)) conv.externalCards.push(c);
      });
    }
    // 恢复执行签名库：与消息树一并并入内存，供建卡时判定「这条调用做过没有」。
    // 只增不减地合并，避免本次存档缺字段时清掉内存里已有的记录。
    if (saved.executedSigs && typeof saved.executedSigs === 'object') {
      conv.executedSigs = conv.executedSigs || {};
      Object.keys(saved.executedSigs).forEach((sig) => {
        if (saved.executedSigs[sig]) conv.executedSigs[sig] = true;
      });
    }
    // 诊断：后端取回多少条签名，以及恢复后内存里共多少条
    log('loadConversation 签名恢复：会话=' + convId
      + ' 后端=' + Object.keys(saved.executedSigs || {}).length
      + ' 内存=' + Object.keys(conv.executedSigs || {}).length);
    // 可见键：后端给了就用后端的，否则保留内存原值
    conv.visibleKeys = Array.isArray(saved.visibleKeys) ? saved.visibleKeys : (conv.visibleKeys || []);
    // 分支键与孤立切片：后端给了就整体替换
    if (Array.isArray(saved.branchKeys)) conv.branchKeys = saved.branchKeys;
    if (Array.isArray(saved.orphanSlice)) conv.orphanSlice = saved.orphanSlice;
  };

  M.loadConversation = function (convId, done) {
    const cb = typeof done === 'function' ? done : function () {};
    const self = this;
    // 加载期标记：从发起请求到合并完成之间，禁止写回后端。
    // 否则内存里还是空的签名库，500ms 防抖一到就把后端已有的签名整表覆盖掉，
    // 刷新后卡片会全部退回待执行。
    this._convLoading = this._convLoading || {};
    this._convLoading[convId] = true;
    // 后端唯一权威：历史从后端取；后端无此会话时，memFetchConv 内部会
    // 尝试迁移补丁从本地读一次（临时代码，迁移完成后可删）。
    this.memFetchConv(convId).then(function (saved) {
      // 期间可能又切换了会话：不再处理，避免把旧会话历史写进新会话
      if (self.activeConv !== convId) { cb(false); return; }
      const conv = self.ensureConv(convId);
      // 网络失败：不能当成「后端没有这个会话」。
      // 若当成空会话，会立即解除写回禁令，随后用内存里的空签名库覆盖后端存档，
      // 刷新一次毁一次。此处保持锁定并稍后重试，直到真正取到数据。
      if (saved && saved.ok === false) {
        // 不解锁、不置就绪：此时内存是空的，任何写回都会覆盖后端存档。
        // 退避重试的排期细节见 _scheduleConvRetry。
        self._scheduleConvRetry(convId, saved.error, cb);
        return;
      }
      // 加载成功：清掉该会话的重试计数
      if (self._convRetry) delete self._convRetry[convId];
      if (!saved) {
        log('loadConversation：后端与本地均无会话 ' + convId);
        self._convReady = self._convReady || {};
        self._convReady[convId] = true;
        // 后端无此会话也属「加载结束」：必须解禁，否则该会话此后永远无法写回。
        if (self._convLoading) delete self._convLoading[convId];
        cb(true);
        return;
      }
      // 把后端存档并入内存会话（消息树、外部卡片、签名库、可见键等）
      self._mergeSavedConv(conv, saved, convId);
      self._convReady = self._convReady || {};
      self._convReady[convId] = true;
      // 合并完毕，解除写回禁令：此后内存里的签名库已与后端一致，写回是安全的。
      // 这一步必须无条件执行：若被下方重判逻辑的异常打断，_convLoading 会永久为真，
      // 此后该会话的所有落盘都被跳过，签名再也存不回后端，刷新后卡片必然退回待执行。
      if (self._convLoading) delete self._convLoading[convId];
      // 签名库已合并进内存，回头把消息树里那些「建卡时签名库还是空的」卡片重判一次。
      // 卡片可能早于存档加载就已建好，那时查签名必然落空，卡片被建成待执行态。
      // 包裹 try：重判只是状态修正，失败不应影响会话就绪与后续落盘。
      try {
        if (self._restoreExecutedCards) self._restoreExecutedCards.call(self, conv, convId);
      } catch (e) {
        log('重判已执行卡片失败（不影响加载）：' + e);
      }
      log('loadConversation：会话 ' + convId + ' 就绪（后端），节点=' + Object.keys(conv.msgTree).length);
      cb(true);
    });
  };

  /**
   * 组装当前会话的存档载荷。
   * @param {Object} conv 会话记录
   * @returns {Object} 可直接写入 storage 的普通对象
   */
  M.buildConvPayload = function (conv) {
    return {
      title: conv.title,
      page_url: conv.page_url,
      msgTree: conv.msgTree || {},           // 唯一存完整信息处
      visibleKeys: conv.visibleKeys || [],   // 可见区切片（只存 key）
      branchKeys: conv.branchKeys || [],     // 组装分支（只存 key）
      externalCards: conv.externalCards || [],
      orphanSlice: conv.orphanSlice || [],
      // executedSigs：已执行调用的签名库。
      // 必须随存档一起落盘：重启后内存清空，若不恢复，签名库为空，
      // _executedSig 永远命中不了，卡片会退回待执行并被自动流程再跑一遍。
      executedSigs: conv.executedSigs || {},
      updatedAt: Date.now()
    };
  };

  /**
   * 把指定会话写入本地存储（含写入失败检查）。
   * 必须显式接收会话 id：落盘是延迟执行的，延迟期间可能切换会话。
   * @param {string} [convId] 目标会话 id；缺省为当前活动会话
   */
  M.persistConv = function (convId) {
    const id = convId || this.activeConv;
    const conv = this.conversations[id];
    if (!conv) return;
    const payload = this.buildConvPayload(conv);
    log('persistConv 写入后端：会话=' + id + '，节点=' + Object.keys(payload.msgTree || {}).length
      + '，外部卡片=' + (payload.externalCards || []).length
      + '，签名=' + Object.keys(payload.executedSigs || {}).length);
    // 后端唯一权威：消息树只写后端，不再写 chrome.storage.local。
    // 写入是异步的，失败由 memSaveConv 内部提示，不阻塞调用方。
    if (this.memSaveConv) this.memSaveConv(id, payload);
  };

  /**
   * 扫描本地存储里的全部会话存档，把标题等摘要填入 convScanned。
   * 只读标题 / 页面地址 / 更新时间等轻量字段。
   */
  M.scanConversations = function () {
    const self = this;
    // 后端唯一权威：会话列表从后端拉取
    this.memListConvs().then(function (list) {
      const out = {};
      (list || []).forEach(function (c) {
        if (!c || !c.conv_id) return;
        out[c.conv_id] = {
          title: c.title || '',
          pageUrl: c.page_url || '',
          updatedAt: (c.updated_at || 0) * 1000,
          msgCount: 0  // 后端列表不返回节点数，切会话后由消息树统计
        };
      });
      self.convScanned = out;
      log('会话列表已从后端加载：' + Object.keys(out).length + ' 个会话');
    });
  };

  /**
   * 在会话列表中切换到某个会话。
   * 读取历史后不做切片处理，仅展示已存历史。
   * @param {string} id 目标会话 id
   */
  M.selectConversation = function (id) {
    if (!id || id === this.activeConv) return;
    this.applyConversation(id, '', '', null);
    log('会话列表切换：' + id);
  };

  /**
   * 清空全部会话：逐个删除内存与本地存储里的会话存档。
   * @param {boolean} [skipConfirm] 跳过确认弹窗。远程指令（QQ 发来）无法弹窗，
   *   由调用方传 true；界面按钮不传，照常确认。
   */
  M.clearAllConversations = function (skipConfirm) {
    if (!skipConfirm && !confirm('确认清空全部会话？所有会话的聊天记录与卡片都会被删除，此操作不可撤销。')) return;
    const self = this;
    const memIds = Object.keys(this.conversations || {});
    memIds.forEach((id) => {
      const c = self.conversations[id];
      if (!c) return;
      self.eachCard(c, (card) => {
        if (card && card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
      });
      (c.externalCards || []).forEach((ec) => {
        if (ec && ec._cdTimer) { clearTimeout(ec._cdTimer); ec._cdTimer = null; }
      });
    });
    // 后端唯一权威：逐个删后端会话，删完收尾
    const dels = memIds.map(function (id) {
      return D.apiFetch(self, '/memory/conversation/delete', {
        method: 'POST',
        body: { conv_id: id, site_key: self.siteKey || '' },
      }).catch(function () { return null; });
    });
    Promise.all(dels).then(function () {
      self.conversations = {};
      self._afterClearAll();
    });
  };

  /** 清空全部会话后的收尾：重建一个空的活动会话并复位相关状态。 */
  M._afterClearAll = function () {
    this.convScanned = {};
    this.activeConv = '__default__';
    this._convReady = {};
    this.ensureConv(this.activeConv);
    Object.keys(this.entryChecked).forEach((k) => { delete this.entryChecked[k]; });
    Object.keys(this.entryOpen).forEach((k) => { delete this.entryOpen[k]; });
    this.sessionSearch = '';
    if (this._persist) this._persist(this.activeConv);
    log('已清空全部会话');
    this.toast('已清空全部会话');
  };
})();
