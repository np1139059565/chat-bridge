// 模块：extend/dialog/parts/05h_tree_query.js
// 用途：消息树的只读查询与分支组装：按 id 取键、取父 id、判末条、组装分支路径。
//       从 05_messages.js 抽出，使该文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、05f_parse.js（M.msgId）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  // 四个查询函数挂在 D.methods 上：调用方一律以 this.keyOfId / this.msgId 的形式访问，
  // this 是 Vue 组件实例，实例方法只来自 D.methods；挂在 D 上的属性不会成为实例方法。
  const M = D.methods;

  /**
   * 取某消息 id 在树中的 key（形如「父id-子id」）。
   * 树键以「父-子」编码，故取子段等于目标 id 的那条边即为该消息的键。
   * @param {Object} tree 消息树
   * @param {string} id 消息指纹
   * @returns {string} 命中返回树键，不存在返回空串
   */
  M.keyOfId = function (tree, id) {
    if (!tree || !id) return '';
    const keys = Object.keys(tree);
    for (let i = 0; i < keys.length; i++) {
      const cut = keys[i].indexOf('-');
      if (cut >= 0 && keys[i].slice(cut + 1) === id) return keys[i];
    }
    return '';
  };

  /**
   * 取某消息 id 在树中的父 id。
   * @param {Object} tree 消息树
   * @param {string} id 消息指纹
   * @returns {string} 父 id；不存在返回空串
   */
  M.parentIdOf = function (tree, id) {
    const k = this.keyOfId(tree, id);
    return k ? k.slice(0, k.indexOf('-')) : '';
  };

  /**
   * 判断某条消息是否是「会话树的末条」：树里不存在以它为父的边。
   *
   * 树键格式为「父消息id-子消息id」，因此只要有一条边以该 id 作父，
   * 就说明它后面还有消息，不是末条。
   * 这是自动执行的硬门槛：非末条消息里的卡片任何情况下都不得自动执行，
   * 与「切片末条」不同——切片可能被截断或混入历史，末位未必是会话最新消息。
   * @param {Object} conv 会话记录
   * @param {string} msgId 待判定的消息指纹
   * @returns {boolean} 是会话末条返回 true
   */
  M.isTreeTail = function (conv, msgId) {
    if (!conv || !msgId) return false;
    const tree = conv.msgTree || {};
    const keys = Object.keys(tree);
    for (let i = 0; i < keys.length; i++) {
      const key = keys[i];
      const cut = key.indexOf('-');
      if (cut < 0) continue;
      if (key.slice(0, cut) === msgId) return false;  // 有后继，不是末条
    }
    return true;
  };

  /**
   * 从切片末条回溯，组装出一条分支的树键列表。
   *
   * 优先用切片内相邻边（本轮真实边），避免内容指纹碰撞时 keyOfId 返回
   * 更早的旧 key、导致回溯变浅、分支串到浅处。
   * @param {Object} conv 会话记录
   * @param {Array} slice 本轮消息切片
   * @returns {Array<string>} 从根到末条的树键序列
   */
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
})();
