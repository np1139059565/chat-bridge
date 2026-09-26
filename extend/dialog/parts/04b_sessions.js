// 模块：extend/dialog/parts/04b_sessions.js
// 用途：会话记录条目操作：勾选、删除条目（含消息节点改挂）、清空当前会话、
//       会话列表栏宽拖动、条目跳转与导出。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、04_sessions.js（M.eachCard 等）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /** 切换单个条目的勾选态。 */
  M.toggleEntryChecked = function (key) {
    this.entryChecked[key] = !this.entryChecked[key];
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

  /**
   * 删除一条消息节点，并把它的子节点改挂到其父之下，避免树断裂。
   * 例：删除 1-2，则子边 2-3 改为 1-3。
   * 同时同步改写可见区与分支里存的旧 key。
   * @param {string} delKey 待删除节点的 key（'父id-子id'）
   * @returns {boolean} 是否实际删除
   */
  M.deleteNodeAndRewire = function (delKey) {
    const conv = this.curConv;
    const tree = conv.msgTree || {};
    const node = tree[delKey];
    if (!node) return false;
    const cut = delKey.indexOf('-');
    const pid = delKey.slice(0, cut);
    const id = delKey.slice(cut + 1);
    // 1) 收集所有以被删节点为父的子边，改挂到被删节点的父之下
    const renames = {};
    Object.keys(tree).forEach((k) => {
      const c = k.indexOf('-');
      if (c < 0) return;
      if (k.slice(0, c) === id) {
        const childId = k.slice(c + 1);
        const newKey = pid + '-' + childId;
        renames[k] = newKey;
      }
    });
    Object.keys(renames).forEach((oldKey) => {
      tree[renames[oldKey]] = tree[oldKey];
      delete tree[oldKey];
    });
    // 2) 删除该节点自身（取消其卡片倒计时）
    const cards = node.cards || {};
    Object.keys(cards).forEach((bid) => {
      const card = cards[bid];
      if (card && card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    });
    delete tree[delKey];
    // 3) 同步改写可见区与分支里存的旧 key
    const mapKey = (k) => (renames[k] || k);
    conv.visibleKeys = (conv.visibleKeys || []).map(mapKey).filter((k) => !!tree[k]);
    conv.branchKeys = (conv.branchKeys || []).map(mapKey).filter((k) => !!tree[k]);
    // 4) 外部卡片锚点同步改写
    (conv.externalCards || []).forEach((c) => {
      if (c && c.anchorKey && renames[c.anchorKey]) c.anchorKey = renames[c.anchorKey];
    });
    if (this._persist) this._persist();
    log('deleteNodeAndRewire：删除 ' + delKey + '，改挂 ' + Object.keys(renames).length + ' 条子边');
    return true;
  };

  /**
   * 按条目 key 删除对应内容。
   * 消息：真删节点并把子边改挂（树保持连通）；
   * 外部卡片：从列表移除。
   * @param {string} key 条目 key（消息树 key，或与消息 key 同构的外部卡片 key）
   */
  M.removeEntry = function (key) {
    if (!key) return;
    // 消息 key 与外部卡片 key 现在同构（都是 'pid-id'），不能靠前缀区分。
    // 先按消息树查：命中即删消息；否则按外部卡片 key 查。
    const tree = (this.curConv && this.curConv.msgTree) || {};
    if (tree[key]) {
      if (this.deleteNodeAndRewire(key)) { this.toast('已删除该消息'); return; }
    }
    const ext = (this.externalCards || []).find((c) => c && D.externalCardKey(c) === key);
    if (ext) { this.removeExternalCard(ext.id); return; }
  };

  /**
   * 删除一条网页消息：真删节点并把子边改挂。
   * @param {string} id 消息 id（内容指纹）
   */
  M.removeMessage = function (id) {
    if (!id) return;
    const tree = this.curConv.msgTree || {};
    const key = this.keyOfId(tree, id);
    if (key && this.deleteNodeAndRewire(key)) this.toast('已删除该消息');
  };

  /**
   * 清空当前会话的全部记录：消息树、可见区、分支、外部卡片。
   */
  M.clearSession = function () {
    if (!confirm('确认清空当前会话的全部记录（消息 + 卡片）？此操作不可撤销。')) return;
    const conv = this.curConv;
    // 取消所有卡片倒计时
    this.eachCard(conv, (c) => { if (c && c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; } });
    (conv.externalCards || []).forEach((c) => {
      if (c && c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; }
    });
    conv.msgTree = {};
    conv.visibleKeys = [];
    conv.branchKeys = [];
    conv.externalCards = [];
    conv.orphanSlice = [];
    Object.keys(this.entryChecked).forEach((k) => { delete this.entryChecked[k]; });
    Object.keys(this.entryOpen).forEach((k) => { delete this.entryOpen[k]; });
    if (this._persist) this._persist();
    log('已清空会话记录', this.activeConv);
    this.toast('已清空当前会话记录');
  };

  /**
   * 设置会话列表栏宽度：钳制下限 50px、上限为面板宽度的一半。
   * @param {number} px 目标宽度（像素）
   */
  M.setConvListWidth = function (px) {
    const min = 50;
    const max = Math.max(min, Math.floor(window.innerWidth / 2));
    const w = Math.min(max, Math.max(min, Math.round(px)));
    this.convListWidth = w;
  };

  /**
   * 开始拖动会话列表与会话记录之间的分隔条。
   * @param {PointerEvent} e 分隔条上的 pointerdown 事件
   */
  M.startConvResize = function (e) {
    if (!e) return;
    e.preventDefault();
    const self = this;
    const wrap = e.currentTarget && e.currentTarget.parentElement;
    const left = wrap ? wrap.getBoundingClientRect().left : 0;
    const onMove = function (ev) {
      self.setConvListWidth(ev.clientX - left);
    };
    const onUp = function () {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.style.userSelect = '';
    };
    document.body.style.userSelect = 'none';
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  /**
   * 取一条消息在消息树中的 key（形如「父id-子id」）。
   * @param {string} id 消息 id（内容指纹）
   * @returns {string} 消息树 key；该消息不在树中时返回空串
   */
  M.msgTreeKeyOf = function (id) {
    return this.keyOfId(this.curConv.msgTree || {}, id);
  };

  /**
   * 跳转到「会话记录」中的某条消息：打开设置页、清空搜索、展开该条目并滚动到它。
   * @param {string} id 消息 id（内容指纹）
   */
  M.jumpToSessionEntry = function (id) {
    if (!id) return;
    const key = this.msgTreeKeyOf(id);
    if (!key) return;
    this.settingsOpen = true;
    this.sessionSearch = '';
    this.entryOpen[key] = true;
    setTimeout(function () {
      const el = document.querySelector('.conv-entry[data-entry-key="' + key + '"]');
      if (el && el.scrollIntoView) el.scrollIntoView({ block: 'center' });
    }, 60);
  };

  /**
   * 按条目 key 判断是否在导出范围内。
   * 未勾选任何条目时返回 true（导出全部）。
   * @param {string} key 条目 key
   * @returns {boolean}
   */
  M.entryInRange = function (key) {
    const checked = this.checkedEntryKeys;
    if (!checked.length) return true;
    return checked.indexOf(key) >= 0;
  };

  /**
   * 导出当前会话的 JSON 并复制到剪贴板。
   * 勾选条目时只导出所选范围；未勾选时导出全部。
   */
  M.exportSessionJson = function () {
    const exportAll = this.checkedEntryKeys.length === 0;
    const out = this.buildConvExport(this.activeConv, this.curConv, exportAll ? null : this.entryInRange.bind(this), 'history');
    this.copy(JSON.stringify(out, null, 2));
    this.toast(exportAll ? '已复制当前会话的 JSON' : ('已复制所选 ' + this.checkedEntryKeys.length + ' 个条目的 JSON'));
  };
})();
