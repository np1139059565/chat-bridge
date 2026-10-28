// 模块：extend/dialog/parts/00_data.js
// 用途：对话框 Vue 应用的共享命名空间、常量与 data/computed/mounted。
//  - 定义 window.AIMirrorDialog（下称 D），承载 methods/data/computed 等分片。
//  - 提供后端不可达时的占位工具名 FALLBACK_TOOLS、空会话壳 EMPTY_CONV。
//    工具参数的唯一来源是后端 /tools，前端不维护参数副本。
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

  // 统一的后端请求辅助 D.apiFetch 已拆分到 parts/00a_api.js（控制本文件行数）。

  // 公共工具：由 lib/dom-utils.js 提供
  D.debounce = window.AIMirrorDomUtils.debounce;
  D.hashStr = window.AIMirrorDomUtils.hashStr;
  D.toArray = window.AIMirrorDomUtils.toArray;

  // 远程桥接「推送 + 质量检测」开关的唯一默认值来源。
  // 前端初始 data 与加载后端配置时的 merge 基底都引用它，杜绝三处各写一份默认值
  // 导致「未定义」被误当作「开」、或保存时把开关配置悄悄抹掉。
  D.DEFAULT_BRIDGE_PUSH = {
    user: true, tool: true, ai: true, thinking: false, voice: false,
    check_code_only: true, check_thinking: true, check_multi_call: true, check_memory: true,
    // 语音合成引擎：auto 按 fallback 降级，也可固定为 piper / pyttsx3 / sapi / edge_tts。
    voice_engine: 'auto',
    voice_fallback: 'piper,pyttsx3,sapi,edge_tts',
    // 音色与语速：四类引擎各有自己的音色字段，留空表示用系统默认。
    pyttsx3_voice: 'Microsoft Huihui Desktop - Chinese (Simplified)',
    pyttsx3_rate: 150, sapi_voice: 'Microsoft Huihui Desktop',
    piper_model: '', edge_tts_voice: 'zh-CN-XiaoxiaoNeural'
  };

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

  // 尚未建立会话记录时的空壳
  D.EMPTY_CONV = {
    title: '', page_url: '',
    msgTree: {}, visibleKeys: [], branchKeys: [], externalCards: [],
    updatedAt: 0
  };

  // 后端不可达时的占位清单：只列名称。
  D.FALLBACK_TOOL_NAMES = [
    'list_dir', 'search_file', 'search_content', 'read_file', 'read_image',
    'list_skills', 'read_skill', 'read_lints', 'replace_in_file',
    'write_to_file', 'delete_file', 'list_rules', 'read_rule',
    'get_tool_params', 'run_command'
  ];
  D.FALLBACK_TOOLS = D.FALLBACK_TOOL_NAMES.map(function (name) {
    return { name: name, description: '（后端未连接，参数以后端为准）', parameters: [] };
  });

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

  // data 工厂
  D.data = function () {
    return {
      siteKey: '',
      profileId: '',
      config: {
        // 后端地址不预置：由 discoverFlask 探测并落盘，探测不到时留空，
        // 待用户在设置页手动填写端口。
        flaskUrl: '',
        profile: 'glm',
        flaskPort: 5000
      },
      // 工具服务地址输入框的草稿值：与 config.flaskUrl 分离，
      // 避免「一边输入、连接地址就跟着变」导致请求打到还没起来的端口。
      flaskUrlDraft: '',
      // 是否正在切换端口：为真时禁用输入框与按钮，禁止处理中途再改端口。
      portSwitching: false,
      portMismatch: false,
      configTools: {},
      // 全部内置工具（含已下线）：设置页据此列出开关，下线工具不会从界面消失
      allTools: [],
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
      // 工具结果消息（bridge-chat-res）折叠状态：镜像区默认折叠，
      // 避免那段大 JSON 独占纵向空间；点击标题行展开。
      toolMsgOpen: Vue.reactive({}),
      entryChecked: Vue.reactive({}),
      entryOpen: Vue.reactive({}),
      sessionSearch: '',
      convListWidth: 180,
      convScanned: {},
      settingsOpen: false,
      // 指令说明文本：从后端 /api/bridge/help 拉取，与 /h 同源
      bridgeHelpText: '',
      // 内置指令的结构化分组：[{group, items:[{key, name, desc}]}]，供渲染可点击按钮
      bridgeHelpGroups: [],
      panelSide: 'right',
      theme: 'light',
      _extTimer: null,
      panelVisible: false,
      // QQ 用户标识：从 QQ 卡片 payload 里缓存，上报切片时随请求带上。
      // 只存内存、不进存档：它属于当前这次 QQ 会话，重启后由下一条卡片带回。
      _bridgeQQOpenid: '',
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
      // voice：语音识别开关（默认关，关时丢弃语音文件；开后每轮 AI 回复须带 voice 块，见 05e_quality.js）。
      // push.*：推送到 QQ 的消息类型开关；check.*：质量检测开关。默认值来源见文件头部 D.DEFAULT_BRIDGE_PUSH，
      // 此处浅拷贝一份，避免多实例共享同一对象导致互相污染。
      bridgePush: Object.assign({}, D.DEFAULT_BRIDGE_PUSH),
      // 音色下拉的数据与状态：清单由 loadVoiceTones 拉取，渲染只读这些字段。
      // _voiceToneFor 记录清单对应的引擎，切换引擎时据此判断是否需重新拉取。
      _voiceToneList: [], _voiceToneFor: '', _voiceToneEngine: '',
      bridgeCommands: [],
      bridgePicking: false, bridgePicked: null, bridgeEditIdx: null,  // 元素选择状态
      // 指令录入（拆多行以避免超长行）
      bridgeNewCmdName: '', bridgeNewCmdLabel: '', bridgeNewCmdIsCombo: false,
      bridgeNewCmdKeepCollect: false, bridgeNewCmdSteps: '', bridgeNewCmdInterval: '1',
      // 内置指令参数（通用机制）：值来自后端配置，键为指令名不带 /；
      // 声明（有哪些内置指令有参数）来自后端，前端不写死指令名。
      bridgeCmdParams: {}, bridgeCmdParamDefs: [],
      _mdCaptureTarget: '', _mdCaptureTimer: null, _afterMd: null, _mdReportTimer: null,  // Markdown
      _bridgeStatusTimer: null, bridgeLastEvent: '', bridgeIntents: 0,  // 轮询/诊断
      // 远程桥接（微信 ↔ 网页 AI）：与 QQ 并列但完全独立的一条通道。
      // 字段定义集中在 00a_weixin_data.js，此处展开合并——
      // 微信状态字段较多，集中一处便于新增，也避免本文件超出长度上限。
      ...D.weixinInitialState(),
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
      // 扫描结果默认折叠：扫完一次不该一直占着抽屉高度，需要时再展开。
      scanOpen: false,
      // 工具配置：{工具名: [声明+当前值]}，toolConfOpen 控制该区块折叠
      toolConfig: {}, toolConfOpen: false, systemConfig: [],
      scanRoots: [], flaskOk: false, flaskError: '',
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


  return D;
})();
