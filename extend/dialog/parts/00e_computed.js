// 模块：extend/dialog/parts/00e_computed.js
// 用途：对话框 Vue 的 computed 定义：消息树派生、扁平卡片字典、
//       会话条目列表与搜索过滤、会话列表汇总。原在 00_data.js，
//       因该文件新增状态字段超过 450 行上限而迁出（先例：00c_log_mirror.js、05l_autoexec.js）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D；EMPTY_CONV、buildTimeline、
//       firstLine 等均在运行时经 D 引用，加载期无依赖）。
// 加载顺序：紧随 00_data.js 之后、app.js 之前（computed 在应用创建时才被消费）。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;

  // computed 定义
  D.computed = {
    // 当前会话记录；尚未建立时返回空壳
    curConv: function () {
      return this.conversations[this.activeConv] || D.EMPTY_CONV;
    },
    // 消息树：唯一存完整信息处
    msgTree: function () { return this.curConv.msgTree || {}; },
    // 可见区消息对象数组（镜像区渲染用）：按 visibleKeys 回树取，跳过已删除；
    // 切片与历史断裂、未入树时，回退展示这批切片内容。
    messages: function () {
      const tree = this.curConv.msgTree || {};
      const out = [];
      (this.curConv.visibleKeys || []).forEach(function (k) {
        const node = tree[k];
        if (node && !node.deleted) out.push(node);
      });
      if (!out.length && (this.curConv.orphanSlice || []).length) {
        return this.curConv.orphanSlice.slice();
      }
      return out;
    },
    // 扁平卡片字典：运行时派生（不存储），供渲染按代码块 id 取卡片
    cardMap: function () {
      const out = {};
      const conv = this.curConv;
      const tree = conv.msgTree || {};
      Object.keys(tree).forEach(function (k) {
        const node = tree[k];
        const cards = (node && node.cards) || {};
        Object.keys(cards).forEach(function (bid) { out[bid] = cards[bid]; });
      });
      // 不入树的切片：卡片挂在切片消息上，一并纳入，保证可渲染可操作
      (conv.orphanSlice || []).forEach(function (m) {
        const cards = (m && m.cards) || {};
        Object.keys(cards).forEach(function (bid) { out[bid] = cards[bid]; });
      });
      return out;
    },
    page_url: function () { return this.curConv.page_url; },
    // 外部卡片随会话隔离
    externalCards: function () { return this.curConv.externalCards || []; },
    // 会话条目列表：按 branchKeys 回树取消息，加外部卡片。
    // 每条只生成轻量摘要；key 即消息树 key（'父id-子id'），
    // 外部卡片用其自身 key，同样与消息 key 同构。
    sessionEntries: function () {
      const conv = this.curConv;
      // 保存实例引用：下方 timeline.forEach 用普通函数，其内部 this 为 undefined，
      // 直接用 this 调方法会抛错。
      const self = this;
      const tree = conv.msgTree || {};
      // 统计每个 id 作为父节点出现的次数：出现 ≥2 次即为「分支父节点」
      // （树里有两条以上边从它分叉出去），用于列表里做颜色标记。
      const childCount = {};
      Object.keys(tree).forEach(function (k) {
        const cut = k.indexOf('-');
        if (cut < 0) return;
        const pid = k.slice(0, cut);
        childCount[pid] = (childCount[pid] || 0) + 1;
      });
      // 顺序完全由消息树结构决定：消息按 branchKeys 的顺序，
      // 外部卡片按锚点插到对应消息之后。
      // 切片与历史断裂（未入树）时 branchKeys 为空：改用 orphanSlice 回退，
      // 与镜像区保持一致，否则会出现「镜像有内容、列表却为空」。
      let timeline = D.buildTimeline(conv, conv.branchKeys || []);
      if (!timeline.length && (conv.orphanSlice || []).length) {
        timeline = conv.orphanSlice.map(function (m, i) {
          return { kind: 'message', key: 'orphan-' + i, node: m };
        });
      }
      const items = [];
      timeline.forEach(function (it) {
        if (it.kind === 'message') {
          const node = it.node;
          const id = window.AIMirrorDomUtils.messageFingerprint(node);
          // 该消息节点上挂着的卡片 id 列表：列表里一并展示、并参与搜索，
          // 便于一眼认出某张卡片挂在哪条消息下、也便于排查卡片重复。
          const cards = (node && node.cards) || {};
          const cardIds = Object.keys(cards).filter(function (bid) { return !!cards[bid]; });
          // 该消息下卡片的最晚执行完成时刻（毫秒）：供列表显示，便于分析时序。
          const finishedAt = Object.keys(cards).reduce(function (mx, bid) {
            const c = cards[bid];
            return Math.max(mx, (c && c.finishedAt) || 0);
          }, 0);
          items.push({
            key: it.key,
            kind: 'message',
            id: id,
            cardIds: cardIds,
            finishedAt: finishedAt || null,
            role: node.role || '',
            // source：来源标记（user / assistant / tool）。工具结果以 user 角色落地，
            // 仅凭 role 会把工具结果标成「用户」。会话记录标签据此字段区分工具，
            // 故必须带上，供 kindLabel 判定。
            source: node.source || '',
            name: node.name || '',
            preview: D.firstLine(node),
            // 是否为外部调用信封（external-call）：在会话记录列表里单独着色标记。
            isExternalCall: !!(self.parseExternalCall && self.parseExternalCall(node)),
            isBranchParent: (childCount[id] || 0) >= 2
          });
        } else {
          const c = it.card;
          items.push({
            key: it.key,
            kind: 'external',
            id: c.id,
            label: '用户 · ' + (c.title || c.type || ''),
            status: c.status || '',
            skipped: !!c.skipped
          });
        }
      });
      return items;
    },
    // 按 id 搜索词过滤后的条目列表。
    // 只匹配条目自身的 id，不匹配 key：key 形如 'pid-id'，其中 pid 段是
    // 另一条消息的 id，匹配 key 会把「子条目」也带出来，搜一个 id 命中多条。
    filteredSessionEntries: function () {
      const list = this.sessionEntries || [];
      const q = String(this.sessionSearch || '').trim().toLowerCase();
      if (!q) return list;
      return list.filter(function (e) {
        // 匹配消息指纹，或该消息下任一卡片 id：
        // 这样既能按消息定位，也能按卡片门牌号反查它挂在哪条消息下。
        if (String(e.id || '').toLowerCase().indexOf(q) >= 0) return true;
        // 再匹配完整 key（形如 'pid-id'）：只匹配 id（右段）会漏掉「作为父段出现」
        // 的条目（如 key 112-113 里，搜 112 应命中）。故 key 也纳入匹配。
        if (String(e.key || '').toLowerCase().indexOf(q) >= 0) return true;
        const cards = e.cardIds || [];
        for (let i = 0; i < cards.length; i++) {
          if (String(cards[i] || '').toLowerCase().indexOf(q) >= 0) return true;
        }
        return false;
      });
    },
    // 已勾选的条目 key 列表
    checkedEntryKeys: function () {
      return (this.sessionEntries || [])
        .filter((e) => !!this.entryChecked[e.key])
        .map((e) => e.key);
    },
    // 对话镜像倒序显示：最新消息在前
    reversedMessages: function () {
      return this.messages.slice().reverse();
    },
    // 会话列表：按最近更新时间倒序
    convList: function () {
      const convs = this.conversations || {};
      const map = {};
      const scanned = this.convScanned || {};
      Object.keys(scanned).forEach((id) => {
        const s = scanned[id] || {};
        map[id] = {
          id: id,
          title: s.title || '（未命名会话）',
          pageUrl: s.pageUrl || '',
          updatedAt: s.updatedAt || 0,
          msgCount: s.msgCount || 0
        };
      });
      Object.keys(convs).forEach((id) => {
        const c = convs[id];
        if (!c) return;
        const prev = map[id];
        // 消息条数：统计整棵消息树的全部节点（不筛分支，含已删除）
        let msgCount = 0;
        const tree = c.msgTree || {};
        Object.keys(tree).forEach(function (k) {
          if (tree[k]) msgCount += 1;
        });
        map[id] = {
          id: id,
          title: c.title || (prev && prev.title) || '（未命名会话）',
          pageUrl: c.page_url || (prev && prev.pageUrl) || '',
          updatedAt: c.updatedAt || (prev && prev.updatedAt) || 0,
          msgCount: (tree && Object.keys(tree).length) ? msgCount : ((prev && prev.msgCount) || msgCount)
        };
      });
      const list = Object.keys(map).map(function (id) { return map[id]; });
      list.sort(function (a, b) { return (b.updatedAt || 0) - (a.updatedAt || 0); });
      return list;
    }
  };

})();
