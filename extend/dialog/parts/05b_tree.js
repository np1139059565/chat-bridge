// 模块：extend/dialog/parts/05b_tree.js
// 用途：消息树的核心写入口 upsertTree（把网页推送的消息切片并入树）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、05_messages.js（M.msgId 等）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /**
   * 把一批（有序）消息并入消息树。
   *
   * 对比单位是「边」：切片内相邻两条构成 '父id-子id'，拿去树里比对。
   *   1) 树为空            → 整片作为新树
   *   2) 切片不足两条      → 报错忽略
   *   3) 命中边为空        → 生产轮次回退为「从已知节点按顺序接上」；否则仅展示不入树
   *   4) 命中边不连续      → 判定碰撞，整片不入树
   *   5) 命中的是前缀一节  → 向后追加新节点
   *   6) 命中的是后缀一节  → 向前补接新节点（根随之变更）
   *   7) 命中位于中间      → 暂不支持，忽略
   *   8) 整片命中          → 无新增
   * 已在树中的节点一律不改写。
   * @param {Object} conv 会话记录（就地修改 msgTree）
   * @param {Array} incoming 本次网页推送的消息（有序）
   * @param {string} [reason] 触发来源：'generate' / 'scroll' / 'switch' / 'manual'
   * @returns {Object} { mode } 本次处理结果
   */
  M.upsertTree = function (conv, incoming, reason) {
    const tree = conv.msgTree || (conv.msgTree = {});
    const list = incoming || [];
    const n = list.length;
    if (!n) return { mode: 'empty' };
    const ids = list.map((m) => this.msgId(m));

    // 1) 空历史：整片建树
    if (!Object.keys(tree).length) {
      for (let i = 0; i < n; i++) {
        const key = (i === 0 ? '0' : ids[i - 1]) + '-' + ids[i];
        tree[key] = this.makeNode(list[i]);
      }
      conv.orphanSlice = [];
      log('upsertTree：空历史，整片建树，节点=' + Object.keys(tree).length);
      return { mode: 'new' };
    }

    // 2) 单节点切片：构不成链
    if (n < 2) {
      log('upsertTree：收到单节点切片，已忽略。id=' + ids[0]);
      if (this.toast) this.toast('收到单节点切片，已忽略');
      conv.orphanSlice = [];
      return { mode: 'single' };
    }

    // 3) 计算切片的所有边，并与树比对
    const sliceKeys = [];
    for (let i = 0; i + 1 < n; i++) sliceKeys.push(ids[i] + '-' + ids[i + 1]);
    const matched = [];
    sliceKeys.forEach((k, i) => { if (tree[k]) matched.push(i); });

    // 4) 完全无交集：生产轮次回退为「从已知节点按顺序接上」；否则仅展示不入树
    if (!matched.length) {
      if (reason === 'generate') {
        // 新消息的第一条边天然不在树里，故按节点定位：
        // 找到切片中最后一个已在树的节点，把其后按顺序接上。
        let baseIdx = -1;
        for (let i = 0; i < n; i++) {
          if (this.keyOfId(tree, ids[i])) baseIdx = i;
        }
        if (baseIdx >= 0) {
          for (let i = baseIdx + 1; i < n; i++) {
            const key = ids[i - 1] + '-' + ids[i];
            if (!tree[key]) tree[key] = this.makeNode(list[i]);
          }
          conv.orphanSlice = [];
          log('upsertTree：生产场景无命中边，从第 ' + baseIdx + ' 条后接上，节点=' + Object.keys(tree).length);
          return { mode: 'append' };
        }
      }
      // 诊断：断裂时打印切片各条身份与树中现有身份，便于比对差异来源
      log('upsertTree：切片与历史无任何相同边，仅展示不入树');
      log('切片边=' + JSON.stringify(sliceKeys));
      log('切片明细=' + JSON.stringify(list.map((m, i) => ({
        i: i, role: m.role, name: m.name, fp: ids[i]
      }))));
      log('树中现有 key=' + JSON.stringify(Object.keys(tree)));
      if (this.toast) this.toast('切片与历史断裂，仅展示本次内容');
      conv.orphanSlice = list.slice();
      conv.visibleKeys = [];
      conv.branchKeys = [];
      return { mode: 'orphan' };
    }

    // 5) 命中的边必须连续，否则视为碰撞
    let contiguous = true;
    for (let i = 1; i < matched.length; i++) {
      if (matched[i] !== matched[i - 1] + 1) { contiguous = false; break; }
    }
    if (!contiguous) {
      log('upsertTree：切片命中多处不连续的边，判定碰撞，整片不入树');
      if (this.toast) this.toast('切片命中多处，已跳过本次入库');
      conv.orphanSlice = [];
      return { mode: 'collision' };
    }

    const a = matched[0];
    const b = matched[matched.length - 1];
    // 边 a..b 命中 => 节点 a+1 .. b+1 已在树中

    // 8) 整片已存在
    if (a === 0 && b === n - 2) {
      conv.orphanSlice = [];
      log('upsertTree：整片已存在，无新增');
      return { mode: 'full' };
    }

    // 5) 前缀命中：向后追加
    if (a === 0) {
      for (let i = b + 2; i < n; i++) {
        const key = (i === 0 ? '0' : ids[i - 1]) + '-' + ids[i];
        if (!tree[key]) tree[key] = this.makeNode(list[i]);
      }
      conv.orphanSlice = [];
      log('upsertTree：前缀命中，向后追加，节点=' + Object.keys(tree).length);
      return { mode: 'append' };
    }

    // 6) 后缀命中：向前补接（根随之变更）
    if (b === n - 2) {
      // 补接前先取 ids[a] 原有的父边：补接会把 ids[a] 接到新段尾部，
      // 原父边必须随之删除。否则 ids[a] 出现两个父、旧根残留成第二棵树，
      // 消息树就不再是单根。这正是注释里「根随之变更」的落点。
      const oldEdge = this.keyOfId(tree, ids[a]);
      for (let i = 0; i <= a; i++) {
        const key = (i === 0 ? '0' : ids[i - 1]) + '-' + ids[i];
        if (!tree[key]) tree[key] = this.makeNode(list[i]);
      }
      // 删掉被取代的旧父边；若旧边恰是本次新接的边则不删，避免误删。
      const newEdge = (a === 0 ? '0' : ids[a - 1]) + '-' + ids[a];
      if (oldEdge && oldEdge !== newEdge) delete tree[oldEdge];
      conv.orphanSlice = [];
      log('upsertTree：后缀命中，向前补接，节点=' + Object.keys(tree).length);
      return { mode: 'prepend' };
    }

    // 7) 命中位于中间：暂不支持
    log('upsertTree：切片命中位于中间，暂不支持，已忽略');
    if (this.toast) this.toast('切片位于历史中间，已跳过本次入库');
    conv.orphanSlice = [];
    return { mode: 'middle' };
  };
})();
