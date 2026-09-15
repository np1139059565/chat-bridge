// 模块：extend/dialog/parts/04_sessions.js
// 用途：多会话的状态管理：会话创建、切换、恢复、持久化，以及历史卡片删除。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const hashStr = D.hashStr;
  const M = D.methods;

  /** 确保某会话的记录对象存在，并补齐统一时序所需字段（兼容旧存档）。 */
  M.ensureConv = function (id) {
    const key = id || '__default__';
    if (!this.conversations[key]) {
      this.conversations[key] = {
        title: '', pageUrl: '', messages: [], cardMap: {}, externalCards: [],
        msgTs: {}, _lastTs: 0, updatedAt: 0
      };
    }
    const conv = this.conversations[key];
    // 兼容旧存档：补齐统一时序所需字段
    if (!Array.isArray(conv.externalCards)) conv.externalCards = [];
    if (!conv.msgTs || typeof conv.msgTs !== 'object') conv.msgTs = {};
    if (typeof conv._lastTs !== 'number') conv._lastTs = 0;
    return conv;
  };

  /**
   * 消息内容指纹：role + 名称 + 各块内容的稳定摘要。
   * 注意：它只代表「内容」，相同内容的两条消息指纹相同，
   * 因此不能直接当序号键，必须叠加「第几次出现」才是唯一键。
   */
  M.messageFingerprint = function (m) {
    if (!m) return 'm';
    const parts = [m.role || '', m.name || ''];
    (m.blocks || []).forEach((b) => {
      if (!b) return;
      if (b.type === 'code') parts.push('c:' + (b.lang || '') + ':' + String(b.code || '').slice(0, 200));
      else if (b.type === 'list') parts.push('l:' + (b.items || []).join('|').slice(0, 200));
      else if (b.type === 'table') parts.push('t:' + JSON.stringify(b.rows || []).slice(0, 200));
      else parts.push('x:' + String(b.text || '').slice(0, 200));
    });
    return 'm' + hashStr(parts.join('\u0001'));
  };

  /**
   * 单调时间戳：与外部卡片的 createdAt 同源（Date.now()，毫秒）。
   * 保证严格递增，避免同一毫秒内多条条目时间戳相同导致顺序抖动。
   */
  M.monotonicTs = function (conv) {
    if (!conv) return Date.now();
    const now = Date.now();
    const last = conv._lastTs || 0;
    const ts = now > last ? now : last + 1;
    conv._lastTs = ts;
    return ts;
  };

  /**
   * 为一批消息打时间戳：按顺序遍历，同一内容第 n 次出现用「指纹#n」作键，
   * 首次出现时打一个时间戳并记住，之后沿用（网页重绘不打乱顺序）。
   * 时间戳与外部卡片同源同量纲，二者渲染时统一排序。
   */
  M.assignMsgTs = function (conv) {
    if (!conv) return;
    if (!conv.msgTs || typeof conv.msgTs !== 'object') conv.msgTs = {};
    if (typeof conv._lastTs !== 'number') conv._lastTs = 0;
    const seen = {};
    (conv.messages || []).forEach((m) => {
      const fp = this.messageFingerprint(m);
      seen[fp] = (seen[fp] || 0) + 1;
      const k = fp + '#' + seen[fp];
      if (conv.msgTs[k] == null) conv.msgTs[k] = this.monotonicTs(conv);
      m._ts = conv.msgTs[k];
    });
  };

  /** 网页端切换会话时调用：切换活动记录并恢复该会话已保存的卡片状态。 */
  M.applyConversation = function (convId, title, url) {
    const id = convId || '__default__';
    if (id !== this.activeConv) {
      log('会话切换：', this.activeConv, '→', id, title ? '（' + title + '）' : '');
      this.activeConv = id;
      this.loadConversation(id);
    }
    const conv = this.ensureConv(id);
    if (title) conv.title = title;
    if (url) conv.pageUrl = url;
  };

  /** 从本地存储恢复会话（含卡片「是否已执行过」的状态）。 */
  M.loadConversation = function (convId) {
    const key = this.convKey(convId);
    this._restoring = (this._restoring || 0) + 1;
    chrome.storage.local.get(key, (res) => {
      this._restoring = (this._restoring || 0) - 1;
      const saved = res && res[key];
      if (!saved || this.activeConv !== convId) return;
      const conv = this.ensureConv(convId);
      // 统一时序：序号随会话恢复。必须在恢复消息之前合入，
      // 否则恢复出的消息会被重新分配新序号、顺序错乱。
      if (saved.msgTs && typeof saved.msgTs === 'object') {
        Object.keys(saved.msgTs).forEach((k) => {
          if (conv.msgTs[k] == null) conv.msgTs[k] = saved.msgTs[k];
        });
      }
      if (typeof saved._lastTs === 'number' && saved._lastTs > (conv._lastTs || 0)) {
        conv._lastTs = saved._lastTs;
      }
      // 消息：仅在本地尚无内容时用快照恢复，避免旧快照覆盖刚从网页抓到的新内容
      if (!conv.messages.length && (saved.messages || []).length) {
        conv.messages = saved.messages;
        conv.title = saved.title || conv.title;
        conv.pageUrl = saved.pageUrl || conv.pageUrl;
        // 恢复出的消息若已有历史时间戳则沿用；缺失的按当前顺序补时间戳
        this.assignMsgTs(conv);
        log('已恢复会话消息', convId, '消息数=' + conv.messages.length);
      }
      // 外部卡片：随会话快照恢复。存档优先（含执行态），本地已有则不覆盖，
      // 与 cardMap 的恢复策略保持一致（异步回调晚于同步灌入，故按存档补齐）。
      const savedExt = saved.externalCards;
      if (Array.isArray(savedExt) && savedExt.length) {
        const known = new Set((conv.externalCards || []).map((c) => c.id));
        savedExt.forEach((c) => {
          if (c && c.id && !known.has(c.id)) (conv.externalCards || (conv.externalCards = [])).push(c);
        });
      }
      // 卡片执行状态：必须无条件合并，绝不能也加「消息为空」的条件。
      // 因为 chrome.storage 是异步的，而 ingestMessages 是同步执行的：
      // 本回调触发时页面内容早已灌入（conv.messages 非空），
      // 一旦加了那道门，卡片状态就永远恢复不了 —— 刷新后一律变回待执行。
      this.mergeCardMap(convId, saved.cardMap);
    });
  };

  /** 把持久化的卡片执行状态合并回当前会话。 */
  M.mergeCardMap = function (convId, savedCardMap) {
    const conv = this.conversations[convId];
    if (!conv || !savedCardMap) return;
    let n = 0;
    Object.keys(savedCardMap).forEach((id) => {
      const saved = savedCardMap[id];
      if (!saved) return;
      const cur = conv.cardMap[id];
      if (cur) {
        // 已跳过状态优先恢复：跳过的卡片不应因页面重绘而变回可自动执行
        if (saved.skipped) {
          cur.skipped = true;
          cur.countdown = 0;
          cur.phase = '';
        }
        // 页面重绘只会重建出 pending 卡片，把已执行的结果回填
        if (saved.executed && !cur.executed) {
          cur.status = saved.status || cur.status;
          cur.result = saved.result;
          cur.error = saved.error;
          cur.stack = saved.stack || null;
          cur.errorType = saved.errorType || '';
          cur.origin = saved.origin || '';
          cur.location = saved.location || null;
          cur.hint = saved.hint || '';
          cur.executed = true;
          n++;
        }
      } else {
        // 页面上已不存在的代码块：仍恢复，切回来时执行记录不丢
        conv.cardMap[id] = saved;
        n++;
      }
    });
    if (n) log('已恢复卡片执行状态', convId, '卡片数=' + n);
    // 无论是否恢复出内容都要落盘，确保合并后的状态被保存
    if (this._persist) this._persist();
  };

  /** 把当前会话写入本地存储。 */
  M.persistConv = function () {
    const convId = this.activeConv;
    const conv = this.conversations[convId];
    if (!conv) return;
    const payload = {
      title: conv.title,
      pageUrl: conv.pageUrl,
      messages: conv.messages,
      cardMap: conv.cardMap,
      externalCards: conv.externalCards || [],   // 外部卡片随会话持久化
      msgTs: conv.msgTs || {},                   // 统一时序：消息指纹 → 时间戳
      _lastTs: conv._lastTs || 0,                // 统一时序：当前最大时间戳
      updatedAt: Date.now()
    };
    chrome.storage.local.set({ [this.convKey(convId)]: payload });
  };

  /** 删除单个历史卡片（若在自动倒计时中一并取消）。 */
  M.removeCard = function (id) {
    const card = this.cardMap[id];
    if (card && card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    delete this.cardMap[id];
    if (this._persist) this._persist();
    this.toast('已删除卡片');
  };

  /** 删除外部卡片：取消其倒计时并从外部卡片列表中移除，并落盘。 */
  M.removeExternalCard = function (id) {
    const idx = (this.externalCards || []).findIndex((c) => c.id === id);
    if (idx < 0) return;
    const card = this.externalCards[idx];
    if (card && card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    this.externalCards.splice(idx, 1);
    if (this._persist) this._persist();
    this.toast('已删除外部卡片');
  };

  /** 历史卡片管理列表中的删除入口：按来源分派到对应的删除方法。 */
  M.removeHistoryCard = function (card) {
    if (!card) return;
    if (card._kind === 'external') this.removeExternalCard(card.id);
    else this.removeCard(card.id);
  };

  /** 清空当前会话全部历史卡片（工具/代码卡片与外部卡片一并清空）。 */
  M.clearAllCards = function () {
    if (!confirm('确认清空当前会话全部历史卡片？此操作不可撤销。')) return;
    Object.keys(this.cardMap).forEach((id) => {
      const card = this.cardMap[id];
      if (card && card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
      delete this.cardMap[id];
    });
    const ext = this.curConv.externalCards || [];
    ext.forEach((c) => {
      if (c && c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; }
    });
    // 就地清空当前会话的外部卡片数组，保持 computed 引用不变
    ext.length = 0;
    if (this._persist) this._persist();
    this.toast('已清空历史卡片');
  };
})();
