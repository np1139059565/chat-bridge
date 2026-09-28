// 模块：extend/dialog/parts/00_data.js
// 用途：对话框 Vue 应用的共享命名空间、常量与 data/computed/mounted。
//  - 定义 window.AIMirrorDialog（下称 D），承载 methods/data/computed 等分片。
//  - 提供后端不可达时的占位工具名 FALLBACK_TOOLS、空会话壳 EMPTY_CONV。
//    工具参数的唯一来源是后端 /tools，前端不维护参数副本。
//  - 外部卡片与消息的时序装配见 00b_timeline.js。
// 依赖：lib/dom-utils.js（debounce / hashStr / toArray）
//
// 数据模型：会话只存 msgTree（节点含完整信息）、visibleKeys、branchKeys、
//   externalCards。顺序完全由消息树结构与入列先后决定。
window.AIMirrorDialog = (function () {
  'use strict';
  const D = window.AIMirrorDialog || {};
  D.methods = D.methods || {};

  // 调试日志：与内容脚本同前缀，便于在网页控制台用 [AI-Mirror] 过滤
  D.log = function () {
    console.log.apply(console, ['[AI-Mirror][dialog]'].concat(Array.prototype.slice.call(arguments)));
  };
  const log = D.log;

  /**
   * 统一的后端请求辅助：拼地址、按需序列化 JSON 请求体、检查响应状态、解析 JSON。
   * @param {Object} ctx Vue 实例（读取 config.flaskUrl）
   * @param {string} path 接口路径
   * @param {Object} [options] fetch 选项
   * @returns {Promise<Object>} 解析后的 JSON
   */
  D.apiFetch = async function (ctx, path, options) {
    const opts = Object.assign({}, options || {});
    const lenientJson = !!opts.lenientJson;
    delete opts.lenientJson;
    const base = (ctx.config.flaskUrl || '').replace(/\/+$/, '');
    opts.headers = Object.assign({}, opts.headers || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    const r = await fetch(base + path, opts);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    if (lenientJson) return r.json().catch(function () { return {}; });
    return r.json();
  };

  // 公共工具：由 lib/dom-utils.js 提供
  D.debounce = window.AIMirrorDomUtils.debounce;
  D.hashStr = window.AIMirrorDomUtils.hashStr;
  D.toArray = window.AIMirrorDomUtils.toArray;

  // 尚未建立会话记录时的空壳
  D.EMPTY_CONV = {
    title: '', page_url: '',
    msgTree: {}, visibleKeys: [], branchKeys: [], externalCards: [],
    updatedAt: 0
  };

  // 后端不可达时的占位清单：只列名称。
  D.FALLBACK_TOOL_NAMES = [
    'list_dir', 'search_file', 'search_content', 'read_file',
    'list_skills', 'read_skill', 'read_lints', 'replace_in_file',
    'write_to_file', 'delete_file', 'list_rules', 'read_rule',
    'get_tool_params', 'run_command'
  ];
  D.FALLBACK_TOOLS = D.FALLBACK_TOOL_NAMES.map(function (name) {
    return { name: name, description: '（后端未连接，参数以后端为准）', parameters: [] };
  });

  // data 工厂
  D.data = function () {
    return {
      siteKey: '',
      profileId: '',
      config: {
        flaskUrl: 'http://127.0.0.1:5000',
        profile: 'glm',
        flaskPort: 5000
      },
      portMismatch: false,
      configTools: {},
      maxJsonChars: 100000,
      systemPrompt: '',
      toolsOpen: false,
      tools: D.FALLBACK_TOOLS,
      // 多会话
      activeConv: '__default__',
      conversations: {},
      expanded: Vue.reactive({}),
      thinkOpen: Vue.reactive({}),
      userOpen: Vue.reactive({}),
      stackOpen: Vue.reactive({}),
      entryChecked: Vue.reactive({}),
      entryOpen: Vue.reactive({}),
      sessionSearch: '',
      convListWidth: 180,
      convScanned: {},
      settingsOpen: false,
      panelSide: 'right',
      theme: 'light',
      _extTimer: null,
      panelVisible: false,
      promptSections: [],
      skills: [],
      skillsManage: [],
      skillsOpen: false,
      skillsExpanded: Vue.reactive({}),
      skillDocOpen: Vue.reactive({}),
      skillDocText: Vue.reactive({}),
      skillDocEdit: Vue.reactive({}),
      skillDocEditing: Vue.reactive({}),
      customTools: [],
      // 远程桥接（QQ ↔ 网页 AI）
      bridgeOpen: false,
      bridgeEnabled: true,   // 默认开启：远程功能开箱即用
      bridgeConnected: false,
      bridgeAppId: '', bridgeAppSecret: '',
      bridgePush: { user: true, tool: true, ai: true, thinking: false },
      bridgeCommands: [],
      bridgePicking: false, bridgePicked: null, bridgeEditIdx: null,  // 元素选择状态
      bridgeNewCmdName: '', bridgeNewCmdLabel: '', bridgeNewCmdIsCombo: false, bridgeNewCmdKeepCollect: false, bridgeNewCmdSteps: '', bridgeNewCmdInterval: '1',  // 指令录入
      bridgeMdSelector: '', _mdCaptureTarget: '', _mdCaptureTimer: null, _afterMd: null, _mdReportTimer: null,  // Markdown
      _bridgeStatusTimer: null, bridgeLastEvent: '', bridgeIntents: 0,  // 轮询/诊断
      rules: [],
      rulesDir: '',
      rulesOpen: false,
      rulePriorities: [
        { value: 'always', label: '总是' },
        { value: 'on-demand', label: '按需' },
        { value: 'off', label: '关闭' }
      ],
      rulesExpanded: Vue.reactive({}),
      rulesEditing: Vue.reactive({}),
      rulesEdit: Vue.reactive({}),
      newRuleName: '',
      customExpanded: Vue.reactive({}),
      customEdit: Vue.reactive({}),
      customEditing: Vue.reactive({}),
      skillScanDir: '',
      scanResults: [],
      scanRoots: [],
      flaskOk: false,
      flaskError: '',
      toastMsg: '',
      autoSendEnabled: false,
      autoSendDelay: 3000,
      _toastTimer: null,
      _persist: null,
      _persistTimers: null,
      _convReady: null
    };
  };

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
          items.push({
            key: it.key,
            kind: 'message',
            id: id,
            cardIds: cardIds,
            role: node.role || '',
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

  /**
   * 启动带倒计时的卡片状态机（工具卡片与外部卡片共用）。
   * @param {Object} ctx Vue 实例
   * @param {Object} card 目标卡片
   * @param {string} phase 'exec' 或 'send'
   * @param {Function} onDone 倒计时结束后的动作
   */
  D.startCountdown = function (ctx, card, phase, onDone) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    const secs = Math.max(1, Math.round((ctx.autoSendDelay || 3000) / 1000));
    card.phase = phase;
    card.countdown = secs;
    const tick = () => {
      card.countdown -= 1;
      if (card.countdown > 0) {
        card._cdTimer = setTimeout(tick, 1000);
        return;
      }
      card._cdTimer = null;
      card.countdown = 0;
      card.phase = '';
      onDone();
    };
    card._cdTimer = setTimeout(tick, 1000);
  };

  /** 取消卡片上正在进行的倒计时，并复位阶段与计数。 */
  D.cancelCountdown = function (card) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    card.countdown = 0;
    card.phase = '';
  };

  // mounted 生命周期
  D.mounted = function () {
    log('dialog mounted，准备就绪');
    this.ensureConv(this.activeConv);
    // 落盘队列：按会话 id 各自延迟排队
    this._persistTimers = {};
    this._persist = function (convId) {
      const id = convId || this.activeConv;
      const timers = this._persistTimers;
      if (timers[id]) clearTimeout(timers[id]);
      timers[id] = setTimeout(function () {
        delete timers[id];
        this.persistConv(id);
      }.bind(this), 500);
    };
    this.initBackend();
    window.addEventListener('message', this.onPageMessage);
    window.parent.postMessage({ type: 'request_page' }, '*');
    window.parent.postMessage({ type: 'request_panel_side' }, '*');
    window.parent.postMessage({ type: 'request_theme' }, '*');
    window.parent.postMessage({ type: 'request_panel_visible' }, '*');
  };

  return D;
})();
