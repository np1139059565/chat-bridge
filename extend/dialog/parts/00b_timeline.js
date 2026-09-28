// 模块：extend/dialog/parts/00b_timeline.js
// 用途：外部卡片与消息树的时序装配：外部卡片条目 key、卡片是否已有消息本体、
//       把消息与外部卡片按锚点装配成时序条目列表。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
// 说明：本文件是 00_data.js 的时序装配部分独立拆分。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;

  /**
   * 外部卡片的条目 key：与消息的 'pid-id' 同构（两段、连字符连接）。
   * 卡片在创建时即生成 key 字段。
   * @param {Object} c 外部卡片
   * @returns {string} 条目 key
   */
  D.externalCardKey = function (c) {
    return (c && c.key) || '';
  };

  /**
   * 判断外部卡片是否已由消息树中的 external-call 消息代表。
   * 卡片发送完成后，本体以一条 user 消息落在消息树里；此时数组里那份不应
   * 再单独渲染，否则同一张卡片会重复出现两次。以 nonce 匹配二者。
   * @param {Object} conv 会话记录
   * @param {Object} card 外部卡片
   * @returns {boolean} 是否已有消息本体
   */
  D.cardHasMessage = function (conv, card) {
    if (!card || !card.executed || !card.nonce) return false;
    const tree = (conv && conv.msgTree) || {};
    const keys = Object.keys(tree);
    for (let i = 0; i < keys.length; i++) {
      const node = tree[keys[i]];
      if (!node || node.role !== 'user') continue;
      const blocks = window.AIMirrorDomUtils.toArray(node.blocks);
      for (let j = 0; j < blocks.length; j++) {
        const b = blocks[j];
        const src = String((b && (b.code || b.text)) || '').trim();
        if (!src || src.charAt(0) !== '{') continue;
        try {
          const obj = JSON.parse(src);
          if (obj && obj.type === 'external-call' && obj.nonce === card.nonce) return true;
        } catch (e) { /* 非信封内容 */ }
      }
    }
    return false;
  };

  /**
   * 按结构关系装配时序列表：消息严格按给定的 key 顺序，
   * 外部卡片按锚点（创建时所在分支末端的 key）插到对应消息之后。
   * 顺序完全由结构与入列先后决定。
   * @param {Object} conv 会话记录
   * @param {Array<string>} msgKeys 有序的消息树 key 列表
   * @param {Object} [opts]
   * @param {string} [opts.orphanMode] 锚点不在列表时的处理：'end'（默认，放到末尾）
   *   或 'skip-handled'（已处理的不显示，未处理的放末尾，用于镜像区）
   * @returns {Array} 条目数组 { kind, key, node?, card? }
   */
  D.buildTimeline = function (conv, msgKeys, opts) {
    const tree = (conv && conv.msgTree) || {};
    const mode = (opts && opts.orphanMode) || 'end';
    // 已发送、且消息树里已有对应 external-call 消息本体的卡片不再单独渲染：
    // 否则同一张卡片会以「数组卡片」和「消息本体」两种形态各出现一次。
    const cards = ((conv && conv.externalCards) || []).filter(function (c) {
      return c && !D.cardHasMessage(conv, c);
    });
    // 外部卡片按入列先后排列：同一锚点内的先后即入列顺序。
    const byAnchor = {};
    const orphan = [];
    cards.forEach(function (c) {
      const a = c.anchorKey;
      if (a && tree[a]) (byAnchor[a] = byAnchor[a] || []).push(c);
      else orphan.push(c);
    });
    const items = [];
    (msgKeys || []).forEach(function (k) {
      const node = tree[k];
      if (!node || node.deleted) return;
      items.push({ kind: 'message', key: k, node: node });
      const cs = byAnchor[k];
      if (cs) cs.forEach(function (c) { items.push({ kind: 'external', key: D.externalCardKey(c), card: c }); });
    });
    orphan.forEach(function (c) {
      // 锚点不在当前列表：镜像区里已处理的不显示，未处理的放到末尾；会话记录里一律放末尾。
      if (mode === 'skip-handled' && (c.executed || c.skipped)) return;
      items.push({ kind: 'external', key: D.externalCardKey(c), card: c });
    });
    return items;
  };
})();
