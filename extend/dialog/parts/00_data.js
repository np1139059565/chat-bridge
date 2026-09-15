// 模块：extend/dialog/parts/00_data.js
// 用途：对话框 Vue 应用的共享命名空间、常量与 data/computed/mounted。
//  - 定义 window.AIMirrorDialog（下称 D），承载 methods/data/computed 等分片。
//  - 提供本地兜底工具目录 FALLBACK_TOOLS、空会话壳 EMPTY_CONV。
// 依赖：lib/dom-utils.js（debounce / hashStr）
//
// 背景：原 app.js 是单个 IIFE 内的 createApp 选项对象。拆分后改为把各段
// 挂到 D.methods / D.data / D.computed，由 app.js 统一装配成 createApp 的选项。
// Vue 会在实例上绑定 methods，因此 this 语义与原实现一致。
window.AIMirrorDialog = (function () {
  'use strict';
  const D = window.AIMirrorDialog || {};
  D.methods = D.methods || {};

  // 调试日志：与内容脚本同前缀，便于在网页控制台用 [AI-Mirror] 过滤
  D.log = function () {
    console.log.apply(console, ['[AI-Mirror][dialog]'].concat(Array.prototype.slice.call(arguments)));
  };
  const log = D.log;

  // 公共工具：由 lib/dom-utils.js 提供
  D.debounce = window.AIMirrorDomUtils.debounce;
  D.hashStr = window.AIMirrorDomUtils.hashStr;

  // 尚未建立会话记录时的空壳，供 computed 安全读取（避免 computed 内产生副作用）
  D.EMPTY_CONV = { title: '', pageUrl: '', messages: [], cardMap: {}, externalCards: [], updatedAt: 0 };

  // 与 Flask 服务保持一致的本地兜底工具目录（Flask 不可达时使用）
  D.FALLBACK_TOOLS = [
    {
      name: 'list_dir', description: '列出指定目录下的文件和子目录（不含点文件）', parameters: [
        { name: 'target_directory', type: 'string', required: true, description: '要列出的目录路径（相对或绝对）' },
        { name: 'ignore_globs', type: 'array', required: false, description: '要忽略的通配符模式列表' }
      ]
    },
    {
      name: 'search_file', description: '按文件名通配符模式递归搜索文件，支持忽略特定模式', parameters: [
        { name: 'target_directory', type: 'string', required: true, description: '搜索根目录' },
        { name: 'pattern', type: 'string', required: true, description: '文件名通配符，如 *.js' },
        { name: 'recursive', type: 'boolean', required: false, description: '是否递归子目录，默认 true' },
        { name: 'caseSensitive', type: 'boolean', required: false, description: '是否区分大小写' },
        { name: 'ignore_globs', type: 'array', required: false, description: '忽略模式列表' }
      ]
    },
    {
      name: 'search_content', description: '基于正则在文件内容中搜索匹配（支持上下文、类型过滤）', parameters: [
        { name: 'pattern', type: 'string', required: true, description: '正则表达式' },
        { name: 'path', type: 'string', required: false, description: '搜索路径，默认当前目录' },
        { name: 'glob', type: 'string', required: false, description: '文件名过滤，如 *.py' },
        { name: 'contextAround', type: 'integer', required: false, description: '上下文字节数/行数' },
        { name: 'caseSensitive', type: 'boolean', required: false, description: '是否区分大小写' }
      ]
    },
    {
      name: 'read_file', description: '读取本地文件内容（仅接受绝对路径），支持指定偏移与行数', parameters: [
        { name: 'filePath', type: 'string', required: true, description: '文件绝对路径' },
        { name: 'offset', type: 'integer', required: false, description: '起始行（从 1 开始）' },
        { name: 'limit', type: 'integer', required: false, description: '读取行数' }
      ]
    },
    {
      name: 'read_skill', description: '读取某个 skill 目录下的文档（相对该 skill 目录的路径，如 SKILL.md）', parameters: [
        { name: 'skill', type: 'string', required: true, description: 'skill 名称（skills/ 下的目录名，如 debug_chrome）' },
        { name: 'file', type: 'string', required: true, description: 'skill 目录内的相对路径，如 SKILL.md' },
        { name: 'offset', type: 'integer', required: false, description: '起始行（从 1 开始）' },
        { name: 'limit', type: 'integer', required: false, description: '读取行数' }
      ]
    },
    {
      name: 'read_lints', description: '读取工作区或指定文件的 linter 诊断信息（错误/警告）', parameters: [
        { name: 'paths', type: 'array', required: false, description: '文件或目录路径' },
        { name: 'severity', type: 'array', required: false, description: '过滤严重级别' }
      ]
    },
    {
      name: 'replace_in_file', description: '在已有文件中进行精确字符串替换（用于最小化改动）', parameters: [
        { name: 'filePath', type: 'string', required: true, description: '文件路径' },
        { name: 'old_str', type: 'string', required: true, description: '待替换原文（须唯一）' },
        { name: 'new_str', type: 'string', required: true, description: '替换后的文本' }
      ]
    },
    {
      name: 'write_to_file', description: '创建或覆盖写入完整文件内容', parameters: [
        { name: 'filePath', type: 'string', required: true, description: '文件路径' },
        { name: 'content', type: 'string', required: true, description: '完整文件内容' }
      ]
    },
    {
      name: 'delete_file', description: '删除指定路径的文件', parameters: [
        { name: 'target_file', type: 'string', required: true, description: '要删除的文件路径' }
      ]
    },
    {
      name: 'get_tool_params', description: '根据工具 id 查询其参数、说明与用法', parameters: [
        { name: 'tool_id', type: 'string', required: true, description: '工具名称/id' }
      ]
    },
    {
      name: 'list_rules', description: '列出本机可用的规则文件（规则名 + 摘要），供 AI 判断该读取哪条规则', parameters: []
    },
    {
      name: 'read_rule', description: '按规则名读取某条规则的完整内容（如 self-healing 异常自愈规则）', parameters: [
        { name: 'name', type: 'string', required: true, description: '规则名（不含扩展名），先用 list_rules 获取' }
      ]
    },
    {
      name: 'run_command', description: '执行本地命令（按指定脚本语言选择解释器；支持的语言由后端配置决定）', parameters: [
        { name: 'language', type: 'string', required: true, description: '脚本语言类型，如 python / shell / cmd / powershell / git 等（以 get_tool_params 返回的支持列表为准）' },
        { name: 'command', type: 'string', required: true, description: '要执行的命令或代码块内容' },
        { name: 'cwd', type: 'string', required: false, description: '工作目录，默认使用当前工程目录' },
        { name: 'timeout', type: 'integer', required: false, description: '超时秒数，默认 60 秒' }
      ]
    }
  ];

  // data 工厂：Vue 组件的数据定义
  D.data = function () {
    return {
      // 配置统一由后端 config.yaml 管理，插件不从浏览器存储配置（避免丢失）
      siteKey: '',
      profileId: '',   // 当前生效的站点规则（由 content 脚本回传）
      config: {
        flaskUrl: 'http://127.0.0.1:5000',   // 由后端 /config 下发，仅会话内使用，不持久化到浏览器
        profile: 'glm',
        flaskPort: 5000
      },
      portMismatch: false,   // 配置端口 ≠ 实际连通端口（端口已改但服务未重启）
      configTools: {},   // { 工具名: { enabled: bool } }，来自后端 /config
      maxJsonChars: 100000,  // 工具结果 JSON 体积上限（字符），来自后端 config.yaml 的 limits
      systemPrompt: '',
      toolsOpen: false,
      tools: D.FALLBACK_TOOLS,
      // 多会话：切换左侧历史会话后各自保留消息与卡片执行状态
      activeConv: '__default__',
      conversations: {},
      expanded: Vue.reactive({}),
      thinkOpen: Vue.reactive({}),
      userOpen: Vue.reactive({}),   // 用户消息折叠态：默认折叠（与「思考过程」一致）
      // 卡片「完整堆栈」展开状态（按卡片 id）
      stackOpen: Vue.reactive({}),
      settingsOpen: false,
      panelSide: 'right',   // 悬浮抽屉挂靠侧：right / left（由 content 脚本下发）
      // 外部卡片已改为按会话存放（见 computed externalCards / curConv.externalCards），
      // 不再放在 data 顶层，避免跨会话串台与刷新丢失。
      _extTimer: null,       // 外部卡片轮询定时器
      promptSections: [],    // 技能说明段落：来自后端 /prompt_sections
      // 自定义工具（来自标准 skill 的 tool.json）：列表 / 展开态 / 内联编辑态
      customTools: [],
      // 规则文件（用户自定义约定，AI 按需读取）：列表 / 展开态 / 编辑态
      rules: [],
      rulesDir: '',
      rulesOpen: false,
      // 规则读取优先级：always(总是) / on-demand(按需) / off(关闭)
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
      autoSendEnabled: false,  // 全局「自动」开关：勾选后执行按钮倒计时自动执行并回传
      autoSendDelay: 3000,     // 自动执行 / 自动回传共用倒计时（毫秒），在设置页配置
      _toastTimer: null,
      _persist: null,
      _restoring: 0   // 正在从存储恢复的会话数（>0 时暂停写盘）
    };
  };

  // computed 定义
  D.computed = {
    // 当前会话记录；尚未建立时返回空壳
    curConv: function () {
      return this.conversations[this.activeConv] || D.EMPTY_CONV;
    },
    messages: function () { return this.curConv.messages; },
    cardMap: function () { return this.curConv.cardMap; },
    pageUrl: function () { return this.curConv.pageUrl; },
    // 外部卡片随会话隔离：切换会话 / 站点时各自保留，与工具卡片行为一致。
    // 写入方式与 cardMap 相同（直接 push/splice 当前会话的数组），不整体替换引用。
    externalCards: function () { return this.curConv.externalCards || []; },
    // 历史卡片管理列表：把工具/代码卡片与外部卡片统一按时序（创建时间倒序）合并。
    // 外部卡片同样属于本会话发生过的卡片，必须一并按时序记录，
    // 否则「历史卡片管理」会遗漏外部卡片，时序也不完整。
    // 同毫秒用 id 保证排序稳定。
    sortedHistoryCards: function () {
      const local = Object.keys(this.cardMap)
        .map(function (id) { return Object.assign({}, this.cardMap[id], { _kind: 'code' }); }.bind(this));
      const ext = (this.externalCards || [])
        .map(function (c) { return Object.assign({}, c, { _kind: 'external' }); });
      return local.concat(ext)
        .sort(function (a, b) {
          return (b.createdAt || 0) - (a.createdAt || 0)
            || String(a.id || '').localeCompare(String(b.id || ''));
        });
    },
    // 对话镜像倒序显示：最新消息在前
    reversedMessages: function () {
      return this.messages.slice().reverse();
    }
  };

  /**
   * 启动带倒计时的卡片状态机（工具卡片与外部卡片共用）。
   * 倒计时期间只改 phase / countdown，不改 status，
   * 这样中途关闭「自动」时卡片能自然退回待处理态，不会卡死。
   *
   * @param {Object} ctx Vue 实例（读取 autoSendDelay）
   * @param {Object} card 目标卡片（就地修改 _cdTimer / phase / countdown）
   * @param {string} phase 阶段名：'exec'（执行）或 'send'（回传 / 发送）
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
      // 倒计时归零：清理定时器与阶段标记，交给调用方执行最终动作
      card._cdTimer = null;
      card.countdown = 0;
      card.phase = '';
      onDone();
    };
    card._cdTimer = setTimeout(tick, 1000);
  };

  /**
   * 取消卡片上正在进行的倒计时，并复位阶段与计数。
   * @param {Object} card 目标卡片
   */
  D.cancelCountdown = function (card) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    card.countdown = 0;
    card.phase = '';
  };

  // mounted 生命周期
  D.mounted = function () {
    log('dialog mounted，准备就绪');
    this.ensureConv(this.activeConv);
    this._persist = D.debounce(function () { this.persistConv(); }.bind(this), 500);
    // 配置统一从后端读取：先发现后端地址，再取配置，再取工具目录
    this.initBackend();
    window.addEventListener('message', this.onPageMessage);
    // 对话框可能晚于初始推送加载，主动请求一次当前工具调用
    window.parent.postMessage({ type: 'request_page' }, '*');
    window.parent.postMessage({ type: 'request_panel_side' }, '*');
    log('已发送 request_page 请求重发结构化对话');
  };

  return D;
})();
