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
    // 切换到新会话：先建立会话对象，再从 storage 读历史
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
  M.loadConversation = function (convId, done) {
    const cb = typeof done === 'function' ? done : function () {};
    const key = this.convKey(convId);
    const self = this;
    chrome.storage.local.get(key, (res) => {
      // 期间可能又切换了会话：不再处理，避免把旧会话历史写进新会话
      if (self.activeConv !== convId) { cb(false); return; }
      const saved = res && res[key];
      const conv = self.ensureConv(convId);
      if (!saved) {
        log('loadConversation：会话无存档 ' + convId);
        self._convReady = self._convReady || {};
        self._convReady[convId] = true;
        cb(true);
        return;
      }
      // 消息树：把存档节点并入内存树（存档为准），保留节点自带卡片状态
      if (saved.msgTree && typeof saved.msgTree === 'object') {
        Object.keys(saved.msgTree).forEach((k) => {
          const node = saved.msgTree[k];
          if (!node) return;
          conv.msgTree[k] = node;
        });
      }
      if (saved.title) conv.title = conv.title || saved.title;
      if (saved.page_url) conv.page_url = conv.page_url || saved.page_url;
      // 外部卡片：补齐本地没有的
      if (Array.isArray(saved.externalCards)) {
        const known = new Set((conv.externalCards || []).map((c) => c && c.id));
        saved.externalCards.forEach((c) => {
          if (c && c.id && !known.has(c.id)) conv.externalCards.push(c);
        });
      }
      // 可见区 key 与分支 key：优先用存档
      conv.visibleKeys = Array.isArray(saved.visibleKeys) ? saved.visibleKeys : (conv.visibleKeys || []);
      if (Array.isArray(saved.branchKeys)) conv.branchKeys = saved.branchKeys;
      if (Array.isArray(saved.orphanSlice)) conv.orphanSlice = saved.orphanSlice;
      self._convReady = self._convReady || {};
      self._convReady[convId] = true;
      log('loadConversation：会话 ' + convId + ' 历史就绪，节点=' + Object.keys(conv.msgTree).length);
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
    const self = this;
    const payload = self.buildConvPayload(conv);
    log('persistConv 写入：会话=' + id + '，节点=' + Object.keys(payload.msgTree || {}).length
      + '，外部卡片=' + (payload.externalCards || []).length);
    chrome.storage.local.set({ [self.convKey(id)]: payload }, function () {
      const err = chrome.runtime.lastError;
      if (err) {
        log('persistConv 写入失败：' + (err.message || err));
        self.toast('会话存档失败：存储空间不足');
      }
    });
  };

  /**
   * 扫描本地存储里的全部会话存档，把标题等摘要填入 convScanned。
   * 只读标题 / 页面地址 / 更新时间等轻量字段。
   */
  M.scanConversations = function () {
    const self = this;
    const prefix = 'aiMirrorConv_' + this.siteKey + '__';
    chrome.storage.local.get(null, function (all) {
      const out = {};
      Object.keys(all || {}).forEach(function (k) {
        if (k.indexOf(prefix) !== 0) return;
        const id = k.slice(prefix.length) || '__default__';
        const saved = all[k] || {};
        // 消息条数：统计整棵消息树的节点数（不做分支筛选），
        // 这样不切会话也能一眼看出该会话累积了多少条消息。
        const tree = saved.msgTree || {};
        let msgCount = 0;
        Object.keys(tree).forEach(function (key) {
          if (tree[key]) msgCount += 1;
        });
        out[id] = {
          title: saved.title || '',
          pageUrl: saved.page_url || '',
          updatedAt: saved.updatedAt || 0,
          msgCount: msgCount
        };
      });
      self.convScanned = out;
      log('会话列表已扫描存储：' + Object.keys(out).length + ' 个会话');
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
   */
  M.clearAllConversations = function () {
    if (!confirm('确认清空全部会话？所有会话的聊天记录与卡片都会被删除，此操作不可撤销。')) return;
    const self = this;
    const memIds = Object.keys(this.conversations || {});
    const keys = memIds.map((id) => this.convKey(id));
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
    this.conversations = {};
    chrome.storage.local.remove(keys, function () {
      chrome.storage.local.get(null, function (all) {
        const prefix = 'aiMirrorConv_' + self.siteKey + '__';
        const remain = Object.keys(all || {}).filter((k) => k.indexOf(prefix) === 0);
        if (remain.length) {
          chrome.storage.local.remove(remain, function () { self._afterClearAll(); });
        } else {
          self._afterClearAll();
        }
      });
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
