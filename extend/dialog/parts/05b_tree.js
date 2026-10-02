// 模块：extend/dialog/parts/05b_tree.js
// 用途：消息树的核心写入口 upsertTree（把网页推送的消息切片并入树）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、05_messages.js（M.msgId 等）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /**
   * 判断切片能否从树中已有节点往下延伸接上。
   * 条件：切片首条已在树中，且其余节点都还不在树里。此时整片是「从某个
   * 已知节点长出的新内容」，无论该节点是叶子还是已有子节点，都能安全接上：
   *   - 叶子情形（末节点纯追加）：把当前末端往下延伸；
   *   - 非叶子情形（新开分支，如重新生成 / 切换回复版本）：给该节点补一条
   *     新出边，消息树由此分叉。
   * 回看历史不会误触发：往回滚时切片要么首条不在树里（更早的内容），
   * 要么其后继边早已在树里（走命中边分支），都不会落进这个判据。
   * @param {Object} tree 消息树
   * @param {Array<string>} ids 切片各条消息 id（有序）
   * @returns {boolean} 是否可从已有节点接上
   */
  M.isAppendableFromExisting = function (tree, ids) {
    if (!ids || ids.length < 2) return false;
    // 首条必须已在树中，作为接入点
    if (!this.keyOfId(tree, ids[0])) return false;
    // 其余节点都不得已在树中，避免与既有节点 / 分支碰撞
    for (let i = 1; i < ids.length; i++) {
      if (this.keyOfId(tree, ids[i])) return false;
    }
    return true;
  };

  /**
   * 把一批（有序）消息并入消息树。
   *
   * 对比单位是「边」：切片内相邻两条构成 '父id-子id'，拿去树里比对。
   *   1) 树为空            → 整片作为新树
   *   2) 切片不足两条      → 报错忽略
   *   3) 命中边为空        → 可回退时从已知节点接上（来源为 generate，
   *                          或切片首条在树、其余都不在树：叶子末端追加，
   *                          或非叶子新开分支）；否则仅展示不入树
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
  M.upsertTree = function (conv, incoming, reason, atBottom) {
    const tree = conv.msgTree || (conv.msgTree = {});
    const list = incoming || [];
    const n = list.length;
    if (!n) return { mode: 'empty' };
    const ids = list.map((m) => this.msgId(m));

    // 1) 空历史：整片建树
    if (!Object.keys(tree).length) return this._treeBuildNew(conv, tree, ids, list);

    // 2) 单节点切片：构不成链
    if (n < 2) return this._treeSingle(conv, ids);

    // 3) 计算切片的所有边，并与树比对
    const sliceKeys = [];
    for (let i = 0; i + 1 < n; i++) sliceKeys.push(ids[i] + '-' + ids[i + 1]);
    const matched = [];
    sliceKeys.forEach((k, i) => { if (tree[k]) matched.push(i); });

    // 4) 完全无交集：寻点回退 + 末路兜底，统一交给 _treeNoMatch 处理
    if (!matched.length) {
      return this._treeNoMatch(conv, tree, ids, list, reason, atBottom, sliceKeys);
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
    if (a === 0) return this._treeAppendTail(conv, tree, ids, list, b, n);

    // 6) 后缀命中：向前补接（根随之变更）
    if (b === n - 2) return this._treePrepend(conv, tree, ids, list, a);

    // 7) 命中位于中间：暂不支持
    log('upsertTree：切片命中位于中间，暂不支持，已忽略');
    if (this.toast) this.toast('切片位于历史中间，已跳过本次入库');
    conv.orphanSlice = [];
    return { mode: 'middle' };
  };

  /**
   * 无命中边时的统一处理：先「寻点」回退接上，再「末路兜底」接到分支末端，
   * 都不行才落到「仅展示不入树」。从 upsertTree 抽出，使主函数保持简短。
   *
   * 三步依次尝试：
   *   1) 寻点回退（_treeAppendFromExisting）：切片里有节点已在树中，从它往后接；
   *   2) 末路兜底（_treeAppendToTail）：generate 且视口在底部时，整片接到分支末端；
   *   3) orphan：以上都失败，仅展示、不入树。
   * 为何兜底要限定「generate + 在底部」：往回翻看历史时也会出现「与树无任何相同边」
   * 的切片，不加约束会把历史误接到末端、污染整棵树。
   * @param {boolean} atBottom 视口是否停在对话最底部（由调用方传入）
   * @param {Array} sliceKeys 切片各相邻边（仅 orphan 诊断用）
   * @returns {Object} 处理结果 { mode }
   */
  M._treeNoMatch = function (conv, tree, ids, list, reason, atBottom, sliceKeys) {
    // 1) 寻点回退：允许按节点接上的两种情形——
    //    · 来源是 generate：AI 刚说完新话，切片首条边的另一端天然不在树里；
    //    · 切片可从树中已有节点往下延伸：首条已在树、其余都不在树。
    //    回看类来源（scroll / switch / manual）只在后者放行，避免把历史误接到末端。
    const canAppend = reason === 'generate' || this.isAppendableFromExisting(tree, ids);
    if (canAppend) {
      const r = this._treeAppendFromExisting(conv, tree, ids, list, reason);
      if (r) return r;
    }
    // 2) 末路兜底：寻点也失效时，generate 且在底部才整片接到分支末端
    if (reason === 'generate' && atBottom) {
      const r2 = this._treeAppendToTail(conv, tree, ids, list);
      if (r2) return r2;
    }
    // 3) 都不行：仅展示、不入树
    return this._treeOrphan(conv, tree, ids, list, sliceKeys);
  };

  /**
   * 无命中边时，尝试「从树中最后一个已知节点往后按顺序接上」。
   * 新消息的第一条边天然不在树里，故按节点定位接入点。
   * @returns {Object|null} 成功返回 { mode:'append' }；无法接上返回 null
   */
  M._treeAppendFromExisting = function (conv, tree, ids, list, reason) {
    const n = ids.length;
    let baseIdx = -1;
    for (let i = 0; i < n; i++) {
      if (this.keyOfId(tree, ids[i])) baseIdx = i;
    }
    if (baseIdx < 0) return null;
    for (let i = baseIdx + 1; i < n; i++) {
      const key = ids[i - 1] + '-' + ids[i];
      if (!tree[key]) tree[key] = this.makeNode(list[i]);
    }
    conv.orphanSlice = [];
    log('upsertTree：无命中边，从第 ' + baseIdx + ' 条后接上（来源=' + (reason || 'generate') + '），节点=' + Object.keys(tree).length);
    return { mode: 'append' };
  };

  /**
   * 末路兜底：寻边、寻点都失败时，把整片接到「当前分支末端」之后。
   *
   * 前提（由调用方 upsertTree 校验）：来源为 generate 且视口在底部，
   * 即确实是「用户正看着最新处、AI 刚生成的新内容」，而非往回翻看的历史。
   *
   * 接入点取当前分支末端（branchKeys 末节点）：它代表树中「用户当前所处的最新位置」。
   * 若分支末端取不到（罕见），退回取树中「最后写入的节点」作末端。
   * 整片按顺序串接到该节点之后，父边为「末端id-首条id」。
   * @returns {Object|null} 成功返回 { mode:'append-tail' }；无法确定末端返回 null
   */
  M._treeAppendToTail = function (conv, tree, ids, list) {
    // 1) 定位当前分支末端：优先用 branchKeys 的末节点，其次用 visibleKeys 末节点
    let tailKey = '';
    const bk = conv.branchKeys || [];
    const vk = conv.visibleKeys || [];
    if (bk.length) tailKey = bk[bk.length - 1];
    else if (vk.length) tailKey = vk[vk.length - 1];
    if (!tailKey || !tree[tailKey]) {
      // 2) 退路：分支/可见 key 都取不到时，用树中最后一个节点的 key 作末端
      const keys = Object.keys(tree);
      tailKey = keys.length ? keys[keys.length - 1] : '';
    }
    if (!tailKey) return null;
    // 末端节点的「右段」即其自身 id，作为整片首条的父
    const cut = tailKey.indexOf('-');
    const tailId = cut >= 0 ? tailKey.slice(cut + 1) : tailKey;
    // 3) 从末端往后依次串接整片
    for (let i = 0; i < ids.length; i++) {
      const parentId = (i === 0) ? tailId : ids[i - 1];
      const key = parentId + '-' + ids[i];
      if (!tree[key]) tree[key] = this.makeNode(list[i]);
    }
    conv.orphanSlice = [];
    log('upsertTree：末路兜底，整片接到分支末端 ' + tailId + ' 之后，新增 ' + ids.length + ' 条');
    return { mode: 'append-tail' };
  };

  /**
   * 断裂处理：切片与历史无任何相同边，仅作展示、不入树，并打印诊断信息。
   * @returns {Object} { mode:'orphan' }
   */
  M._treeOrphan = function (conv, tree, ids, list, sliceKeys) {
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
  };

  /**
   * 前缀命中：切片前半段已在树中，把命中段之后的节点依次往后追加。
   * @param {number} b 最后一条命中边的下标
   * @param {number} n 切片长度
   * @returns {Object} { mode:'append' }
   */
  /**
   * 空历史：把整片切片建成新树（第一条从哨兵根 0 长出）。
   * @returns {Object} { mode:'new' }
   */
  M._treeBuildNew = function (conv, tree, ids, list) {
    const n = ids.length;
    for (let i = 0; i < n; i++) {
      const key = (i === 0 ? '0' : ids[i - 1]) + '-' + ids[i];
      tree[key] = this.makeNode(list[i]);
    }
    conv.orphanSlice = [];
    log('upsertTree：空历史，整片建树，节点=' + Object.keys(tree).length);
    return { mode: 'new' };
  };

  /**
   * 单节点切片：构不成链，忽略并清空切片。
   * @returns {Object} { mode:'single' }
   */
  M._treeSingle = function (conv, ids) {
    log('upsertTree：收到单节点切片，已忽略。id=' + ids[0]);
    if (this.toast) this.toast('收到单节点切片，已忽略');
    conv.orphanSlice = [];
    return { mode: 'single' };
  };

  M._treeAppendTail = function (conv, tree, ids, list, b, n) {
    for (let i = b + 2; i < n; i++) {
      const key = (i === 0 ? '0' : ids[i - 1]) + '-' + ids[i];
      if (!tree[key]) tree[key] = this.makeNode(list[i]);
    }
    conv.orphanSlice = [];
    log('upsertTree：前缀命中，向后追加，节点=' + Object.keys(tree).length);
    return { mode: 'append' };
  };

  /**
   * 后缀命中：切片后半段已在树中，把命中段之前的节点向前补接（根随之变更）。
   * @param {number} a 第一条命中边的下标
   * @returns {Object} { mode:'prepend' }
   */
  M._treePrepend = function (conv, tree, ids, list, a) {
    // 补接前先取 ids[a] 原有的父边：补接会把 ids[a] 接到新段尾部，
    // 原父边必须随之删除。否则 ids[a] 出现两个父、旧根残留成第二棵树。
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
  };
})();
