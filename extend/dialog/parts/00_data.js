// 模块：extend/dialog/parts/00_data.js
// 用途：对话框 Vue 的共享命名空间、常量与 data 工厂（computed 见 00e_computed.js）。
//   定义 window.AIMirrorDialog（下称 D），承载 methods/data 等分片；
//   提供后端不可达时的占位工具名与空会话壳。工具参数唯一来源是后端 /tools。
// 依赖：lib/dom-utils.js（debounce / hashStr / toArray）
// 数据模型：会话只存 msgTree、visibleKeys、branchKeys、externalCards。
window.AIMirrorDialog = (function () {
  'use strict';
  const D = window.AIMirrorDialog || {};
  D.methods = D.methods || {};

  // 调试日志 D.log 已拆分到 parts/00c_log_mirror.js（含后端镜像与批量上报）。
  // 拆分原因：镜像逻辑使本文件超过 450 行上限。
  // 调用点保持不变，本文件内仍以 log 引用它。
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
      bridgeOpen: false, cmdOpen: false,    // 桥接 / 指令区块是否展开
      deliveryOpen: false, generalOpen: false,  // 投递策略 / 通用配置区块是否展开
      bridgeEnabled: true,   // 默认开启：远程功能开箱即用
      bridgeBroadcast: false, // 广播：一条上报发所有通道；默认关，独占是常规行为
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
      // 远程桥接（企业微信 ↔ 网页 AI）：第三条通道，字段定义见 00b_wecom_data.js
      ...D.wecomInitialState(),
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
      // 站点档案（网页 AI 站点配置）：真源在后端 definition.yaml 的 app.profiles。
      // siteProfiles 是服务端快照；siteProfDraft 是编辑工作副本（保存前不被
      // 刷新覆盖）；试运行状态与结果按 pid.field 为键。newField 是自定义字段
      // 录入区。渲染与方法见 parts/08g_site_profiles.js。
      siteProfiles: {}, siteProfDraft: {}, siteProfOpen: false,
      // 方案 v3：本地缓存的全量配置（D3）、本次刷新拉到的后端母版、逐字段差异表、
      // 离线标记 / 未覆盖标记 / 按站点渲染开关 / 覆盖确认框。
      configCache: null, configBackend: null, configDiff: {},
      configOffline: false, configDirty: false,
      siteProfShowAll: false, siteProfConfirmOpen: false,
      configPublicDiff: {}, _configRemovedSites: [], _cfgCacheTimer: null,

      siteProfExpanded: Vue.reactive({}),
      siteProfTesting: Vue.reactive({}), siteProfTestResult: Vue.reactive({}),
      siteProfDeleting: Vue.reactive({}), newField: Vue.reactive({}),
      newSiteId: '', newSiteLabel: '', newSiteHosts: '',
      scanRoots: [], flaskOk: false, flaskError: '',
      toastMsg: '',
      autoSendEnabled: false, riskRecoverEnabled: false,   // 后者为风控自动恢复开关：默认关
      // 因「推送时 AI 仍在生成」被跳过的待执行卡片。生成结束后没有新建卡推送时，
      // 靠它在下一次推送里捡回来，避免卡片永久停在待执行。
      _pendingAutoExec: null,
      pendingExtLogs: [], autoSendDelay: 3000,   // 前者：抽屉未就绪时的日志暂存
      _toastTimer: null,
      _persist: null,
      _persistTimers: null,
      _convReady: null
    };
  };

  // computed 定义已迁至 parts/00e_computed.js：本文件曾因新增状态字段
  // 超过 450 行上限，按分片惯例拆出（新片加载顺序紧随本文件之后）。

  return D;
})();
