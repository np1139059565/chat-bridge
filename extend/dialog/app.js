/* 悬浮对话框 Vue 应用（本地 Vue3 全局构建，无打包工具）
 * 注意：Manifest V3 扩展页 CSP 禁止 unsafe-eval，因此不能用 template 字符串
 * （运行期编译会触发 new Function）。这里改用渲染函数 h()，无需编译器。 */
(function () {
  const { createApp, reactive, h } = Vue;

  // 调试日志：与内容脚本同前缀，便于在网页控制台用 [AI-Mirror] 过滤
  function log() {
    console.log.apply(console, ['[AI-Mirror][dialog]'].concat(Array.prototype.slice.call(arguments)));
  }

  function debounce(fn, ms) {
    let t;
    return function () {
      const args = arguments;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  // 尚未建立会话记录时的空壳，供 computed 安全读取（避免 computed 内产生副作用）
  const EMPTY_CONV = { title: '', pageUrl: '', messages: [], cardMap: {}, updatedAt: 0 };

  // 与 Flask 服务保持一致的本地兜底工具目录（Flask 不可达时使用）
  const FALLBACK_TOOLS = [
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
      name: 'read_file', description: '读取本地文件内容，支持指定偏移与行数', parameters: [
        { name: 'filePath', type: 'string', required: true, description: '文件路径' },
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

  const app = createApp({
    data() {
      return {
        // 配置统一由后端 config.yaml 管理，插件不从浏览器存储配置（避免丢失）
        siteKey: '',
        profileId: '',   // 当前生效的站点规则（由 content.js 回传）
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
        tools: FALLBACK_TOOLS,
        // 多会话：切换左侧历史会话后各自保留消息与卡片执行状态
        activeConv: '__default__',
        conversations: {},
        expanded: reactive({}),
        thinkOpen: reactive({}),
        userOpen: reactive({}),   // 用户消息折叠态：默认折叠（与「思考过程」一致）
        resOpen: reactive({}),    // 结果信封（debug-chrome-res）折叠态：默认折叠（与用户消息一致）
        // 卡片「完整堆栈」展开状态（按卡片 id）
        stackOpen: reactive({}),
        settingsOpen: false,
        panelSide: 'right',   // 悬浮抽屉挂靠侧：right / left（由 content.js 下发）
        externalCards: [],     // 外部卡片：由后端 /api/cards/pending 投递，按时序渲染
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
        rulesExpanded: reactive({}),
        rulesEditing: reactive({}),
        rulesEdit: reactive({}),
        newRuleName: '',
        customExpanded: reactive({}),
        customEdit: reactive({}),
        customEditing: reactive({}),
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
    },
    computed: {
      // 当前会话记录；尚未建立时返回空壳
      curConv() {
        return this.conversations[this.activeConv] || EMPTY_CONV;
      },
      messages() { return this.curConv.messages; },
      cardMap() { return this.curConv.cardMap; },
      pageUrl() { return this.curConv.pageUrl; },
      // 历史卡片管理列表：把工具/代码卡片与外部卡片统一按时序（创建时间倒序）合并。
      // 外部卡片同样属于本会话发生过的卡片，必须一并按时序记录，
      // 否则「历史卡片管理」会遗漏外部卡片，时序也不完整。
      // 同毫秒用 id 保证排序稳定。
      sortedHistoryCards() {
        const local = Object.keys(this.cardMap)
          .map((id) => Object.assign({}, this.cardMap[id], { _kind: 'code' }));
        const ext = (this.externalCards || [])
          .map((c) => Object.assign({}, c, { _kind: 'external' }));
        return local.concat(ext)
          .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0)
            || String(a.id || '').localeCompare(String(b.id || '')));
      },
      // 对话镜像倒序显示：最新消息在前
      reversedMessages() {
        return this.messages.slice().reverse();
      }
    },
    mounted() {
      log('dialog mounted，准备就绪');
      this.ensureConv(this.activeConv);
      this._persist = debounce(() => this.persistConv(), 500);
      // 配置统一从后端读取：先发现后端地址，再取配置，再取工具目录
      this.initBackend();
      window.addEventListener('message', this.onPageMessage);
      // 对话框可能晚于初始推送加载，主动请求一次当前工具调用
      window.parent.postMessage({ type: 'request_page' }, '*');
      window.parent.postMessage({ type: 'request_panel_side' }, '*');
      log('已发送 request_page 请求重发结构化对话');
    },
    methods: {
      toast(msg) {
        this.toastMsg = msg;
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => { this.toastMsg = ''; }, 1600);
      },
      // 切换抽屉挂靠侧：右 ⇄ 左。外框位置由 content.js 负责（iframe 运行在页面上下文）
      switchPanelSide() {
        const next = this.panelSide === 'left' ? 'right' : 'left';
        this.panelSide = next;
        window.parent.postMessage({ type: 'set_panel_side', side: next }, '*');
      },
      // 关闭抽屉：请求 content.js 隐藏 iframe，并记录关闭状态
      closePanel() {
        window.parent.postMessage({ type: 'close_panel' }, '*');
      },
      async initBackend() {
        await this.discoverFlask();
        await this.loadConfig();
        await this.loadCustomTools();
        await this.fetchTools();   // 内部会刷新技能说明段落并生成 System Prompt
        await this.loadRules();
        this.startExternalPoll();
      },
      // 技能说明段落：注入 System Prompt 末尾
      async loadPromptSections() {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/prompt_sections', { headers: { 'Accept': 'application/json' } });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const data = await r.json();
          this.promptSections = (data && data.sections) || [];
        } catch (e) {
          this.promptSections = [];
        }
        this.systemPrompt = this.generateSystemPrompt();
      },
      // ---------- 外部卡片：轮询后端取待投递卡片，渲染后自动发送并等待结果 ----------
      startExternalPoll() {
        if (this._extTimer) return;
        this._extTimer = setInterval(() => this.pollExternalCards(), 1000);
        this.pollExternalCards();
      },
      async pollExternalCards() {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/api/cards/pending', { headers: { 'Accept': 'application/json' } });
          if (!r.ok) return;
          const data = await r.json();
          const cards = (data && data.cards) || [];
          cards.forEach((c) => {
            if (this.externalCards.some((x) => x.id === c.id)) return;
            const card = {
              id: c.id,
              type: c.type || '',
              title: c.title || '外部卡片',
              content: c.content || '',
              payload: c.payload || {},
              source: c.source || 'external',
              status: 'pending',
              phase: '',
              countdown: 0,
              result: null,
              error: null,
              createdAt: c.created_at || Date.now()
            };
            this.externalCards.push(card);
            log('外部卡片已投递', card.id, card.title);
            // 与工具卡片一致：仅当全局自动开关开启时才自动倒计时发送；
            // 未开启时等待用户手动发送。
            if (this.autoSendEnabled) this.scheduleExternalSend(card);
          });
        } catch (e) { /* 后端未就绪时静默重试 */ }
      },
      // 倒计时后把卡片内容发送到网页 AI（与工具卡片共用 autoSendDelay 与倒计时机制）
      scheduleExternalSend(card) {
        if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
        const secs = Math.max(1, Math.round((this.autoSendDelay || 3000) / 1000));
        card.status = 'counting';
        card.phase = 'send';
        card.countdown = secs;
        const tick = () => {
          card.countdown -= 1;
          if (card.countdown > 0) {
            card._cdTimer = setTimeout(tick, 1000);
          } else {
            card._cdTimer = null;
            card.countdown = 0;
            card.phase = '';
            this.sendExternalCard(card);
          }
        };
        card._cdTimer = setTimeout(tick, 1000);
      },
      // 立即发送外部卡片到网页 AI
      sendExternalCard(card) {
        card.status = 'waiting_reply';
        // 按输入信封封装：{ type, id, request }
        const envelope = { type: card.type || 'debug-chrome-req', id: card.id, request: card.content };
        const text = JSON.stringify(envelope, null, 2);
        window.parent.postMessage({ type: 'auto_send', text }, '*');
        this.toast('外部卡片已发送到网页 AI');
      },
      // 手动发送（自动开关未开启时使用）
      onExternalSendClick(card) {
        if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
        card.countdown = 0;
        card.phase = '';
        this.sendExternalCard(card);
      },
      // 按 id 回填外部卡片结果，并通知后端唤醒挂起的创建请求
      async resolveExternalCard(cardId, result) {
        const card = this.externalCards.find((x) => x.id === cardId);
        if (!card) return false;
        card.status = 'done';
        card.result = result;
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          await fetch(base + '/api/cards/' + encodeURIComponent(cardId) + '/reply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ result })
          });
        } catch (e) { /* 回填失败仅记录 */ }
        this.toast('外部卡片已回填结果');
        return true;
      },
      // ---------- 规则文件（rules/*.md）：设置页增删改，AI 通过 list_rules / read_rule 按需读取 ----------
      async loadRules() {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/rules', { headers: { 'Accept': 'application/json' } });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const data = await r.json();
          this.rules = data.rules || [];
          this.rulesDir = data.rulesDir || '';
        } catch (e) {
          this.rules = [];
        }
        // 规则列表进入 System Prompt，规则变动后需重新生成
        this.systemPrompt = this.generateSystemPrompt();
      },
      toggleRule(name) {
        this.rulesExpanded[name] = !this.rulesExpanded[name];
      },
      async setRulePriority(name, priority) {
        const r = this.rules.find((x) => x.name === name);
        const old = r ? r.priority : null;
        if (r) r.priority = priority;   // 乐观更新
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const resp = await fetch(base + '/rules/' + encodeURIComponent(name), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ priority: priority }),
          });
          const data = await resp.json();
          if (!data.ok) throw new Error(data.error);
          await this.loadRules();   // 优先级影响 System Prompt，重新生成
          this.toast('已设置优先级：' + name + ' → ' + priority);
        } catch (e) {
          if (r) r.priority = old;   // 回滚
          this.toast('设置优先级失败：' + e);
        }
      },
      async editRule(name) {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/rules/' + encodeURIComponent(name), { headers: { 'Accept': 'application/json' } });
          const data = await r.json();
          if (!data.ok) throw new Error(data.error);
          this.rulesEdit[name] = data.content || '';
          this.rulesEditing[name] = true;
          this.rulesExpanded[name] = true;
          this.$forceUpdate();
        } catch (e) {
          this.toast('读取规则失败：' + e);
        }
      },
      async saveRule(name) {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/rules/' + encodeURIComponent(name), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: this.rulesEdit[name] || '' }),
          });
          const data = await r.json();
          if (!data.ok) throw new Error(data.error);
          this.rulesEditing[name] = false;
          await this.loadRules();
          this.toast('已保存规则：' + name);
        } catch (e) {
          this.toast('保存规则失败：' + e);
        }
      },
      async createRule() {
        const name = (this.newRuleName || '').trim();
        if (!/^[A-Za-z0-9_-]+$/.test(name)) { this.toast('规则名非法（仅字母、数字、下划线、连字符）'); return; }
        if (this.rules.some((x) => x.name === name)) { this.toast('规则已存在：' + name); return; }
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/rules', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, content: '# ' + name + '\n\n' }),
          });
          const data = await r.json();
          if (!data.ok) throw new Error(data.error);
          this.newRuleName = '';
          await this.loadRules();
          await this.editRule(name);
          this.toast('已创建规则：' + name);
        } catch (e) {
          this.toast('创建规则失败：' + e);
        }
      },
      async removeRule(name) {
        if (!confirm('确认删除规则 ' + name + '？此操作不可撤销。')) return;
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/rules/' + encodeURIComponent(name), { method: 'DELETE' });
          const data = await r.json();
          if (!data.ok) throw new Error('HTTP ' + r.status);
          await this.loadRules();
          this.toast('已删除规则：' + name);
        } catch (e) {
          this.toast('删除规则失败：' + e);
        }
      },
      // 后端地址发现：config 不存浏览器，启动时探测若干候选端口找到 /config 端点。
      // 这样即使 config.yaml 改了端口，也无需在浏览器里手动填地址。
      async discoverFlask() {
        const candidates = [
          this.config.flaskUrl,
          'http://127.0.0.1:5000',
          'http://127.0.0.1:8080',
          'http://127.0.0.1:8000',
          'http://localhost:5000'
        ];
        for (let i = 0; i < candidates.length; i++) {
          const base = candidates[i].replace(/\/+$/, '');
          try {
            const r = await fetch(base + '/config', { headers: { 'Accept': 'application/json' } });
            if (r.ok) { this.config.flaskUrl = base; return; }
          } catch (e) { /* 该地址无服务，试下一个 */ }
        }
        log('discoverFlask: 未找到后端，保留默认地址', this.config.flaskUrl);
      },
      // 切换网站：数据与设置都按站点隔离，互不干扰（配置是全局的，无需按站点重载）
      applySite(key) {
        const k = key || 'unknown-site';
        if (k === this.siteKey) return;
        log('切换站点：', this.siteKey || '(初始)', '→', k);
        this.siteKey = k;
        // 清空上一站点的数据视图，避免不同站点内容混在一起
        this.conversations = {};
        this.activeConv = '__default__';
        this.ensureConv(this.activeConv);
      },
      // 会话存档键：带站点前缀，保证 A 站看不到 B 站的记录
      convKey(id) {
        return 'aiMirrorConv_' + this.siteKey + '__' + (id || '__default__');
      },
      // 配置从后端 config.yaml 读取（不存浏览器）：连接地址、端口、工具上下线状态
      async loadConfig() {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/config', { headers: { 'Accept': 'application/json' } });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const cfg = await r.json();
          // 注意：flaskUrl 由 discoverFlask() 探测到的「实际可连通地址」决定，绝不能用
          // cfg.flask.url（= 配置文件里声明的端口）覆盖——否则端口改了但服务还没重启时，
          // 会连到一个根本没在监听的新端口，导致连接断开。
          if (cfg.flask && cfg.flask.port) this.config.flaskPort = cfg.flask.port;
          if (cfg.tools) this.configTools = cfg.tools;
          if (cfg.limits && cfg.limits.max_json_chars) this.maxJsonChars = cfg.limits.max_json_chars;
          if (cfg.default_profile) this.config.profile = cfg.default_profile;
          // 配置端口与实际连通端口不一致 = 端口已改但服务尚未重启（需重启才生效）
          const m = /:(\d+)/.exec(this.config.flaskUrl);
          const livePort = m ? parseInt(m[1], 10) : 5000;
          this.portMismatch = livePort !== parseInt(this.config.flaskPort, 10);
          log('loadConfig: 后端=' + this.config.flaskUrl, '工具数=' + Object.keys(this.configTools).length,
            '端口一致=' + !this.portMismatch);
        } catch (e) {
          log('loadConfig 失败，使用内置默认值', e);
        }
      },
      // 工具上 / 下线：写回后端 config.yaml，并立即刷新工具目录（影响 System Prompt）
      async setToolEnabled(name, enabled) {
        if (!this.configTools[name]) this.configTools[name] = {};
        this.configTools[name].enabled = enabled;   // 乐观更新
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tools: { [name]: { enabled: enabled } } })
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          await this.fetchTools();   // 上下线影响 System Prompt 与支持的工具树
          this.toast(enabled ? ('已上线：' + name) : ('已下线：' + name));
        } catch (e) {
          this.configTools[name].enabled = !enabled;   // 回滚
          this.toast('保存失败：' + e);
        }
      },
      // 保存 run_command 支持的语言列表（卡片勾选）并写回后端 config.yaml
      async setRunCommandLanguages(languages) {
        const name = 'run_command';
        const enabled = !this.configTools[name] || this.configTools[name].enabled !== false;
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tools: { [name]: { enabled: enabled, languages: languages } } })
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          await Promise.all([this.fetchTools(), this.loadConfig()]);
          this.toast('已更新 run_command 支持语言');
        } catch (e) {
          this.toast('保存失败：' + e);
        }
      },
      // 渲染 run_command 支持语言的勾选卡片（在工具展开详情中展示）
      renderRunCommandLanguages(tool) {
        const all = ['cmd', 'powershell', 'shell', 'git', 'python'];
        const cfgLangs = (this.configTools.run_command && this.configTools.run_command.languages) || [];
        const current = (tool && tool.languages) || cfgLangs || [];
        return h('div', { class: 'lang-checks' }, [
          h('div', { class: 'desc' }, '支持语言（勾选后 AI 可用该语言执行命令）'),
          h('div', { class: 'check-row' }, all.map((lang) => {
            const checked = current.indexOf(lang) !== -1;
            return h('label', { class: 'check-item', key: lang }, [
              h('input', {
                type: 'checkbox',
                checked: checked,
                onChange: (e) => {
                  const next = all.filter((x) => {
                    if (x === lang) return e.target.checked;
                    return current.indexOf(x) !== -1;
                  });
                  this.setRunCommandLanguages(next);
                }
              }),
              lang
            ]);
          }))
        ]);
      },
      // 端口配置：写回后端 config.yaml。端口改动需重启 Flask 才能真正监听新端口，
      // 因此不能立即把连接切到新端口——先保存，再重新探测（若已重启则连新端口，
      // 否则仍连旧端口保持可用），并提示用户重启。
      async savePort() {
        const port = parseInt(this.config.flaskPort, 10);
        if (!port || port < 1 || port > 65535) { this.toast('端口非法'); return; }
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ flask: { port: port } })
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const data = await r.json().catch(() => ({}));
          // 不改连接地址：重新探测，只有新端口真的在监听才切过去
          await this.initBackend();
          if (data.requireRestart) {
            this.toast('端口已保存（' + port + '）。请重启 Flask 服务，再点「重新连接后端」');
          } else {
            this.toast('端口已保存');
          }
        } catch (e) {
          this.toast('保存失败：' + e);
        }
      },
      // 工具结果 JSON 体积上限：写回后端 config.yaml。
      // tools_impl 每次调用现读 config.yaml，因此改完即时生效，无需重启。
      async saveMaxJsonChars() {
        const v = parseInt(this.maxJsonChars, 10);
        if (!v || v <= 0) { this.toast('上限必须为正整数'); return; }
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ limits: { max_json_chars: v } })
          });
          const data = await r.json().catch(() => ({}));
          if (!r.ok || !data.success) throw new Error(data.error || ('HTTP ' + r.status));
          this.maxJsonChars = v;
          this.toast('已保存体积上限：' + v + ' 字符');
        } catch (e) {
          this.toast('保存失败：' + e);
        }
      },
      // ---------- 自定义工具（来自标准 skill 的 tool.json） ----------
      async loadCustomTools() {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/custom_tools', { headers: { 'Accept': 'application/json' } });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const data = await r.json();
          this.customTools = data.tools || [];
          this.scanRoots = data.scanRoots || [];
        } catch (e) {
          this.customTools = [];
        }
      },
      toggleCustom(name) {
        this.customExpanded[name] = !this.customExpanded[name];
      },
      async setCustomEnabled(name, enabled) {
        const t = this.customTools.find((x) => x.name === name);
        if (t) t.enabled = enabled;  // 乐观更新
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/custom_tools/' + encodeURIComponent(name), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enabled }),
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          await this.loadCustomTools();
          await this.fetchTools();  // 上线影响 System Prompt
          this.toast(enabled ? ('已上线：' + name) : ('已下线：' + name));
        } catch (e) {
          if (t) t.enabled = !enabled;
          this.toast('保存失败：' + e);
        }
      },
      async removeCustom(name) {
        if (!confirm('确认删除自定义工具 ' + name + '？此操作不可撤销。')) return;
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/custom_tools/' + encodeURIComponent(name), { method: 'DELETE' });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          await this.loadCustomTools();
          await this.fetchTools();   // 删除影响工具列表与技能说明段落
          this.toast('已删除：' + name);
        } catch (e) {
          this.toast('删除失败：' + e);
        }
      },
      pickDir() {
        const fs = (window.chrome && chrome.fileSystem) || null;
        if (!fs || !fs.chooseEntry) {
          this.toast('当前环境不支持目录选择，请手动输入路径');
          return;
        }
        fs.chooseEntry({ type: 'openDirectory' }, (entry) => {
          if (chrome.runtime.lastError || !entry) return;
          fs.getDisplayPath(entry, (p) => {
            if (p) { this.skillScanDir = p; this.scanSkills(); }
          });
        });
      },
      async scanSkills() {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/custom_tools/scan', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dir: this.skillScanDir }),
          });
          const data = await r.json();
          if (!data.ok) throw new Error(data.error);
          this.scanResults = data.skills || [];
        } catch (e) {
          this.toast('扫描失败：' + e);
        }
      },
      async scanDefaults() {
        if (this.scanRoots && this.scanRoots.length) this.skillScanDir = this.scanRoots[0];
        await this.scanSkills();
      },
      async installSkill(dir, name) {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/custom_tools/install', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dir: dir, names: [name] }),
          });
          const data = await r.json();
          if (!data.ok) throw new Error(data.error);
          await this.loadCustomTools();
          await this.fetchTools();   // 安装后刷新工具列表与技能说明段落
          // 即时更新扫描列表中的安装态，无需重新扫描
          this.scanResults.forEach((skill) => {
            (skill.tools || []).forEach((ts) => {
              if (ts.name === name) ts.installed = true;
            });
          });
          this.toast('已安装：' + name);
        } catch (e) {
          this.toast('安装失败：' + e);
        }
      },
      editCustom(name) {
        const t = this.customTools.find((x) => x.name === name);
        if (!t) return;
        this.customEdit[name] = JSON.stringify({
          description: t.description,
          arg_style: t.arg_style,
          interpreter: t.interpreter,
          parameters: t.parameters,
        }, null, 2);
        this.customEditing[name] = true;
        this.$forceUpdate();
      },
      async saveCustom(name) {
        try {
          const obj = JSON.parse(this.customEdit[name]);
          if (typeof obj.description !== 'string' || !obj.description.trim()) {
            throw new Error('description 不能为空');
          }
          obj.parameters = (obj.parameters || []).map((p) => ({
            name: String(p.name || ''),
            type: p.type || 'string',
            required: !!p.required,
            description: String(p.description || ''),
          }));
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/custom_tools/' + encodeURIComponent(name), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              description: obj.description,
              arg_style: obj.arg_style,
              interpreter: obj.interpreter,
              parameters: obj.parameters,
            }),
          });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          await this.loadCustomTools();
          this.customEditing[name] = false;
          this.toast('已保存：' + name);
        } catch (e) {
          this.toast('保存失败：' + e);
        }
      },
      // ---------- 多会话：切换 / 恢复 / 持久化 ----------
      ensureConv(id) {
        const key = id || '__default__';
        if (!this.conversations[key]) {
          this.conversations[key] = {
            title: '', pageUrl: '', messages: [], cardMap: {}, updatedAt: 0
          };
        }
        return this.conversations[key];
      },
      // 网页端切换会话时调用：切换活动记录并恢复该会话已保存的卡片状态
      applyConversation(convId, title, url) {
        const id = convId || '__default__';
        if (id !== this.activeConv) {
          log('会话切换：', this.activeConv, '→', id, title ? '（' + title + '）' : '');
          this.activeConv = id;
          this.loadConversation(id);
        }
        const conv = this.ensureConv(id);
        if (title) conv.title = title;
        if (url) conv.pageUrl = url;
      },
      // 从本地存储恢复会话（含卡片「是否已执行过」的状态）
      loadConversation(convId) {
        const key = this.convKey(convId);
        this._restoring = (this._restoring || 0) + 1;
        chrome.storage.local.get(key, (res) => {
          this._restoring = (this._restoring || 0) - 1;
          const saved = res && res[key];
          if (!saved || this.activeConv !== convId) return;
          const conv = this.ensureConv(convId);
          // 消息：仅在本地尚无内容时用快照恢复，避免旧快照覆盖刚从网页抓到的新内容
          if (!conv.messages.length && (saved.messages || []).length) {
            conv.messages = saved.messages;
            conv.title = saved.title || conv.title;
            conv.pageUrl = saved.pageUrl || conv.pageUrl;
            log('已恢复会话消息', convId, '消息数=' + conv.messages.length);
          }
          // 卡片执行状态：必须无条件合并，绝不能也加「消息为空」的条件。
          // 因为 chrome.storage 是异步的，而 ingestMessages 是同步执行的：
          // 本回调触发时页面内容早已灌入（conv.messages 非空），
          // 一旦加了那道门，卡片状态就永远恢复不了 —— 刷新后一律变回待执行。
          this.mergeCardMap(convId, saved.cardMap);
        });
      },
      // 把持久化的卡片执行状态合并回当前会话
      mergeCardMap(convId, savedCardMap) {
        const conv = this.conversations[convId];
        if (!conv || !savedCardMap) return;
        let n = 0;
        Object.keys(savedCardMap).forEach((id) => {
          const saved = savedCardMap[id];
          if (!saved) return;
          const cur = conv.cardMap[id];
          if (cur) {
            // 已跳过状态优先恢复：跳过的卡片不应因页面重绘而变回可自动执行
            if (saved.skipped) {
              cur.skipped = true;
              cur.countdown = 0;
              cur.phase = '';
            }
            // 页面重绘只会重建出 pending 卡片，把已执行的结果回填
            if (saved.executed && !cur.executed) {
              cur.status = saved.status || cur.status;
              cur.result = saved.result;
              cur.error = saved.error;
              cur.stack = saved.stack || null;
              cur.errorType = saved.errorType || '';
              cur.origin = saved.origin || '';
              cur.location = saved.location || null;
              cur.hint = saved.hint || '';
              cur.executed = true;
              n++;
            }
          } else {
            // 页面上已不存在的代码块：仍恢复，切回来时执行记录不丢
            conv.cardMap[id] = saved;
            n++;
          }
        });
        if (n) log('已恢复卡片执行状态', convId, '卡片数=' + n);
        // 无论是否恢复出内容都要落盘，确保合并后的状态被保存
        if (this._persist) this._persist();
      },
      persistConv() {
        const convId = this.activeConv;
        const conv = this.conversations[convId];
        if (!conv) return;
        const payload = {
          title: conv.title,
          pageUrl: conv.pageUrl,
          messages: conv.messages,
          cardMap: conv.cardMap,
          updatedAt: Date.now()
        };
        chrome.storage.local.set({ [this.convKey(convId)]: payload });
      },
      // 删除单个历史卡片（若在自动倒计时中一并取消）
      removeCard(id) {
        const card = this.cardMap[id];
        if (card && card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
        delete this.cardMap[id];
        if (this._persist) this._persist();
        this.toast('已删除卡片');
      },
      // 删除外部卡片：取消其倒计时并从外部卡片列表中移除
      removeExternalCard(id) {
        const idx = (this.externalCards || []).findIndex((c) => c.id === id);
        if (idx < 0) return;
        const card = this.externalCards[idx];
        if (card && card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
        this.externalCards.splice(idx, 1);
        this.toast('已删除外部卡片');
      },
      // 历史卡片管理列表中的删除入口：按来源分派到对应的删除方法
      removeHistoryCard(card) {
        if (!card) return;
        if (card._kind === 'external') this.removeExternalCard(card.id);
        else this.removeCard(card.id);
      },
      // 清空当前会话全部历史卡片（工具/代码卡片与外部卡片一并清空）
      clearAllCards() {
        if (!confirm('确认清空当前会话全部历史卡片？此操作不可撤销。')) return;
        Object.keys(this.cardMap).forEach((id) => {
          const card = this.cardMap[id];
          if (card && card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
          delete this.cardMap[id];
        });
        (this.externalCards || []).forEach((c) => {
          if (c && c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; }
        });
        this.externalCards = [];
        if (this._persist) this._persist();
        this.toast('已清空历史卡片');
      },
      async fetchTools() {
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const r = await fetch(base + '/tools', { headers: { 'Accept': 'application/json' } });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          const data = await r.json();
          this.tools = data.tools || data;
          this.flaskOk = true;
        } catch (e) {
          this.tools = FALLBACK_TOOLS;
          this.flaskOk = false;
          this.flaskError = String(e);
        }
        // 工具上下线会改变技能说明段落的生效集合，故一并刷新后再生 System Prompt
        await this.loadPromptSections();
      },
      generateSystemPrompt() {
        const tools = this.tools || [];
        // 工具列表只展示名称与描述；参数定义由 AI 在调用前通过 get_tool_params 自行查询。
        // 这样 prompt 体积随工具数增长可控，也避免 AI 凭直觉臆造参数名
        // （不同工具参数名不统一，如 list_dir 用 target_directory、read_file 用 filePath）。
        const listLines = tools.map((t, i) => {
          return `${i + 1}. ${t.name} — ${t.description}`;
        }).join('\n');
        // 规则列表：展示规则名、读取优先级与摘要；内容由 AI 通过 read_rule 按需读取。
        // off 的规则不写入（视为关闭，AI 不应主动读取）。
        const ruleLabel = (p) => ({ always: '总是', 'on-demand': '按需', off: '关闭' }[p] || '按需');
        const ruleActive = (this.rules || []).filter((r) => r.priority !== 'off');
        const ruleLines = ruleActive.map((r, i) => {
          return `${i + 1}. [${ruleLabel(r.priority)}] ${r.name} — ${r.summary || ''}`;
        }).join('\n') || '（暂无规则）';
        return `本会话通过「AI 工具调用镜像插件」与本地工具服务联动。

【工具调用格式】
当你需要调用工具时，请在一个独立的代码块中返回 JSON，代码块语言标记为 tool，
且必须携带 "type": "bridge-chat-call" 标记（插件仅识别带此标记的代码块）：
\`\`\`tool
{
  "tool": "工具名称",
  "type": "bridge-chat-call",
  "parameters": { "参数名": "参数值" }
}
\`\`\`
插件会自动提取该代码块、调用本地服务执行，并把执行结果作为下一条消息回传给你，请据此继续完成任务。

【执行结果回传格式】
插件回传的结果是一段 JSON 文本，以 { 开始，无代码块围栏，形如（你无需再次调用，直接基于结果继续）：
{
  "tool": "工具名称",
  "type": "bridge-chat-res",
  "success": true,
  "result": ...
}
失败时同一结构返回，字段为 success: false 与 error 等诊断信息。

【支持的工具】
${listLines}

【工具参数查询】
工具的完整参数定义（参数名、类型、必填性、说明）不直接列在此处。
调用任何工具前，请先用 get_tool_params 工具查询该工具的参数定义（传入参数 tool_id = 工具名称），获得完整 schema 后再用正确的参数名调用。

【单次只生成一个代码块】
每次回复只允许包含一个工具调用代码块（即一个 \`\`\`tool 块）。
不要在一次回复里并列多个代码块，也不要把解释文字与工具调用混在同一回复中。
完成当前工具调用、收到插件回传的结果后，再决定并执行下一步；需要多步操作时请分步进行，每一步单独回复一个代码块。
这样插件才能稳定地以「提取 → 执行 → 回传结果」逐轮推进，避免并发多个调用导致结果错乱。

请在涉及文件读取、搜索、写入、删除等需求时，主动使用上述工具，并始终以 tool 代码块格式发起调用。

【规则 Rules】
- 先调用 list_rules 查看有哪些规则（规则名 + 优先级 + 摘要）；
- 再用 read_rule（参数 name=规则名）读取对应规则的完整内容，并遵守它。
每条规则前标注了读取优先级：
- [总是]：必须读取并始终遵守，开始任务前先用 read_rule 读取其内容。
- [按需]：在相关场景下先调用 read_rule 读取后再执行，不要凭记忆臆测。
- （优先级为「关闭」的规则不会出现在此列表，也不应主动读取。）


【规则列表】
${ruleLines}
${this.promptSectionText()}`;
      },
      // 技能说明区域：置于 System Prompt 最末尾，无段落时整块省略
      promptSectionText() {
        const secs = this.promptSections || [];
        if (!secs.length) return '';
        const body = secs.map((s) => '### ' + (s.skill || '') + '\n' + (s.text || '')).join('\n\n');
        return '\n【技能说明】\n' + body + '\n';
      },
      onPageMessage(e) {
        const d = e.data;
        if (!d || !d.type) return;
        if (d.type === 'panel_side') {
          this.panelSide = d.side === 'left' ? 'left' : 'right';
          return;
        }
        if (d.type === 'auto_send_result') {
          this.toast(d.ok ? (d.msg || '已回传结果到网页 AI') : ('回传失败：' + (d.msg || '')));
          return;
        }
        if (d.type === 'page_blocks') {
          // 先按站点切换（数据与设置都按站点隔离），再切会话，最后灌内容
          // 注意：profileId 要在 applySite 之前赋值 —— applySite 内部会 loadConfig，
          // 该站尚无存档时用 content.js 自动识别到的规则作为下拉框默认值。
          if (d.profileId) this.profileId = d.profileId;
          this.applySite(d.siteKey);
          this.applyConversation(d.conversationId, d.conversationTitle, d.url);
          this.ingestMessages(d.messages);
        }
      },
      // 判断某工具是否为 silent（一次性副作用，结果不回传网页 AI）
      toolSilent(name) {
        const t = (this.tools || []).find((x) => x.name === name);
        return !!(t && t.silent);
      },
      // 判断代码块是否为一次工具调用：内容是 { tool, parameters } 即算。
      // 不再依赖语言标记 —— DeepSeek 的代码块是 .md-code-block > pre，
      // 根本没有 language 标记，按 lang 过滤会导致工具调用完全识别不出来。
      // 安全性由调用方保证：只有「助手消息」里的代码块才会被判为工具调用，
      // 用户消息（System Prompt 自带的 ```tool 示例）永远只渲染为只读代码块。
      parseToolCall(block) {
        if (!block || block.type !== 'code') return null;
        const src = String(block.code || '').trim();
        if (!src || src.charAt(0) !== '{') return null; // 快速排除非 JSON
        try {
          const obj = JSON.parse(src);
          // type 过滤：只有 bridge-chat-call 才是工具调用，其余代码块按普通代码渲染
          if (obj && typeof obj === 'object' && obj.tool && obj.type === 'bridge-chat-call') {
            return { tool: String(obj.tool), parameters: obj.parameters || {} };
          }
        } catch (e) { /* 不是工具调用，按普通代码块渲染 */ }
        return null;
      },
      // 从文本中提取所有顶层 JSON 对象（网页 AI 可能把 bridge-chat-res 放在
      // 代码块里，也可能直接作为普通段落文本返回，故两种都要扫）。
      extractJsonObjects(text) {
        const out = [];
        const s = String(text || '');
        let i = 0;
        while (i < s.length) {
          const start = s.indexOf('{', i);
          if (start === -1) break;
          let depth = 0, inStr = false, esc = false, end = -1;
          for (let j = start; j < s.length; j++) {
            const ch = s[j];
            if (inStr) {
              if (esc) esc = false;
              else if (ch === '\\') esc = true;
              else if (ch === '"') inStr = false;
              continue;
            }
            if (ch === '"') inStr = true;
            else if (ch === '{') depth++;
            else if (ch === '}') { depth--; if (depth === 0) { end = j; break; } }
          }
          if (end === -1) break;
          const chunk = s.slice(start, end + 1);
          try { out.push(JSON.parse(chunk)); } catch (e) { /* 非 JSON，跳过 */ }
          i = end + 1;
        }
        return out;
      },
      // 由输入信封类型推导输出信封类型：-req → -res
      replyTypeOf(cardType) {
        const t = cardType || 'debug-chrome-req';
        return t.endsWith('-req') ? (t.slice(0, -4) + '-res') : t;
      },
      // 从镜像到的助手消息里检索输出信封，按 id 归属外部卡片
      scanBridgeResults(messages) {
        if (!this.externalCards.length) return;
        (messages || []).forEach((m) => {
          if (m.role !== 'assistant') return;
          (m.blocks || []).forEach((b) => {
            // 代码块取 code，其它类型取 text；两种都可能承载输出信封
            const raw = b.type === 'code' ? b.code : (b.text || '');
            if (!raw) return;
            this.extractJsonObjects(raw).forEach((obj) => {
              if (!obj || !obj.id) return;
              const card = this.externalCards.find((x) => x.id === obj.id);
              if (!card || card.status === 'done') return;
              // 校验输出信封类型，防止误配
              if (obj.type !== this.replyTypeOf(card.type)) return;
              this.resolveExternalCard(obj.id, obj.result);
            });
          });
        });
      },
      ingestMessages(messages) {
        const conv = this.curConv;
        log('ingestMessages 收到', (messages || []).length, '条消息（会话=' + this.activeConv + '）');
        this.scanBridgeResults(messages);
        conv.messages = messages || [];
        conv.messages.forEach((m) => {
          (m.blocks || []).forEach((b) => {
            if (b.type !== 'code' || !b.id) return;
            // 已存在：保留执行状态（结果 / 错误 / 是否已执行过）
            if (conv.cardMap[b.id]) return;
            // 只把「助手回答」里的代码块当成可执行的工具调用。
            // 用户消息里的 System Prompt 自带 ```tool 示例块，绝不能生成卡片。
            const call = m.role === 'assistant' ? this.parseToolCall(b) : null;
            // silent 工具（如推送消息）为一次性副作用：执行后不回传结果，避免多一轮 AI 请求
            const silent = !!(call && this.toolSilent(call.tool));
            conv.cardMap[b.id] = {
              id: b.id,
              lang: b.lang || '',
              phase: '',   // 自动流程阶段：'' / 'exec'(执行倒计时) / 'send'(回传倒计时)
              code: b.code || '',
              isTool: !!call,
              silent: silent,
              tool: call ? call.tool : '',
              parameters: call ? call.parameters : {},
              status: 'pending',
              result: null,
              error: null,
              executed: false,   // 是否已被执行过（切换会话 / 刷新后据此恢复）
              stack: null,       // 本地工具代码完整堆栈（失败自愈用）
              errorType: '',
              origin: '',        // parameter / environment / tool_internal
              location: null,
              hint: '',
              createdAt: Date.now()
            };
            // 开启自动回传时，新建的工具卡片自动倒计时触发执行（无需点击）
            if (this.autoSendEnabled && !!call && !conv.cardMap[b.id].skipped) this.scheduleExecute(conv.cardMap[b.id]);
            log('新建卡片', b.id, call ? '工具:' + call.tool : '代码:' + (b.lang || '无'));
          });
        });
        // 恢复进行中先不写盘：等 mergeCardMap 合并完再写，
        // 避免把「尚未恢复的 pending 状态」写进存档把执行记录冲掉
        if (this._restoring > 0) return;
        if (this._persist) this._persist();
      },
      reparse() {
        window.parent.postMessage({ type: 'request_page' }, '*');
        this.toast('已重新解析当前网页对话');
      },
      // 导出对话记录：纯 JSON，不含任何样式 / DOM 信息，便于存档与排查问题
      buildLogJson() {
        const cards = [];
        Object.keys(this.cardMap).forEach((id) => {
          const c = this.cardMap[id];
          cards.push({
            id: c.id,
            type: c.isTool ? 'tool_call' : 'code',
            language: c.lang,
            tool: c.tool || undefined,
            parameters: c.isTool ? c.parameters : undefined,
            code: c.isTool ? undefined : c.code,
            status: c.status,
            executed: !!c.executed,          // 该卡片是否已被执行过
            origin: c.origin || undefined,   // 失败分类（parameter / environment / tool_internal）
            result: c.result,
            error: c.error
          });
        });
        return {
          source: 'ai-mirror',
          pageUrl: this.pageUrl,
          conversationId: this.activeConv,
          exportedAt: new Date().toISOString(),
          messageCount: this.messages.length,
          messages: this.messages.map((m) => ({
            role: m.role,
            name: m.name,
            blocks: (m.blocks || []).map((b) => {
              const base = { type: b.type };
              if (b.type === 'code') {
                base.language = b.lang;
                base.code = b.code;
                const c = this.cardMap[b.id];
                if (c && c.isTool) {
                  base.tool = c.tool;
                  base.parameters = c.parameters;
                  base.status = c.status;
                  if (c.result != null) base.result = c.result;
                  if (c.error != null) base.error = c.error;
                }
              } else if (b.type === 'list') {
                base.ordered = b.ordered;
                base.items = b.items;
              } else if (b.type === 'table') {
                base.rows = b.rows;
              } else if (b.type === 'heading') {
                base.level = b.level;
                base.text = b.text;
              } else {
                base.text = b.text;
              }
              return base;
            })
          })),
          cards: cards
        };
      },
      copyConversationJson() {
        const json = JSON.stringify(this.buildLogJson(), null, 2);
        this.copy(json);
        log('已导出对话记录 JSON，长度=' + json.length);
        this.toast('对话记录已复制为 JSON');
      },
      toggleTool(name) {
        this.expanded[name] = !this.expanded[name];
      },
      usageOf(tool) {
        const params = {};
        (tool.parameters || []).forEach((p) => {
          params[p.name] = p.type === 'integer' || p.type === 'boolean' ? `<${p.type}>` : `<${p.type}>`;
        });
        return JSON.stringify({ tool: tool.name, parameters: params }, null, 2);
      },
      statusText(s) {
        return ({ pending: '待执行', running: '执行中', done: '完成', error: '失败' })[s] || s;
      },
      fmt(val) {
        if (val == null) return '';
        return typeof val === 'string' ? val : JSON.stringify(val, null, 2);
      },
      // 回传给 AI 的结果：bridge-chat-res 结构化 JSON 代码块。
      // 失败时务必带上「错误分类 + 完整堆栈」，让 AI 能一眼分清是
      // 「参数写错」还是「本地工具代码缺陷」。
      resultText(card) {
        const payload = { tool: card.tool, type: 'bridge-chat-res' };
        if (card.status === 'done') {
          payload.success = true;
          payload.result = card.result;
        } else {
          payload.success = false;
          payload.origin = card.origin || 'unknown';
          payload.originNote = 'parameter=参数问题，改参数重试即可；environment=路径/权限问题；'
            + 'tool_internal=本地工具代码缺陷，必须用 hot_reload_fix 修代码，改参数无效';
          if (card.errorType) payload.errorType = card.errorType;
          if (card.error) payload.error = card.error;
          if (card.location && card.location.file) payload.location = card.location;
          if (card.hint) payload.hint = card.hint;
          if (card.stack) payload.stack = card.stack;
        }
        return JSON.stringify(payload, null, 2);
      },
      copy(text) {
        const t = String(text);
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(t).then(() => this.toast('已复制'), () => this.fallbackCopy(t));
        } else {
          this.fallbackCopy(t);
        }
      },
      fallbackCopy(t) {
        const ta = document.createElement('textarea');
        ta.value = t; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); this.toast('已复制'); }
        catch (e) { this.toast('复制失败，请手动选择'); }
        document.body.removeChild(ta);
      },
      async executeCard(card) {
        card.status = 'running';
        card.error = null;
        card.result = null;
        // 清空上一轮的失败诊断信息
        card.stack = null;
        card.errorType = '';
        card.origin = '';
        card.location = null;
        card.hint = '';
        try {
          const base = this.config.flaskUrl.replace(/\/+$/, '');
          const resp = await fetch(base + '/tool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool: card.tool, parameters: card.parameters })
          });
          const data = await resp.json();
          card.status = data.success ? 'done' : 'error';
          card.result = data.success ? data.result : data;
          card.error = data.success ? null : (data.error || '未知错误');
          if (!data.success) {
            // 关键：完整堆栈与错误分类必须留存。否则 AI 无法区分「参数写错」与
            // 「本地工具代码有 bug」，会陷入反复改参却始终失败的死循环。
            card.stack = data.traceback || null;
            card.errorType = data.errorType || '';
            card.origin = data.origin || '';
            card.location = data.location || null;
            card.hint = data.hint || '';
          }
        } catch (e) {
          card.status = 'error';
          card.error = String(e);
        }
        // 无论成功失败都记为「已执行过」，切换会话 / 刷新后可据此恢复
        card.executed = true;
        if (this._persist) this._persist();
        // silent 工具为一次性副作用，不把结果回传网页 AI（避免多一轮 AI 请求）
        if (card.silent) return;
        // 开了自动回传：执行完倒计时后再把结果写回网页 AI 输入框并触发发送
        if (this.autoSendEnabled) this.scheduleAutoSend(card);
      },
      // 全局「自动」开关：开启时未执行的工具卡片自动倒计时触发；关闭时取消所有倒计时。
      // 外部卡片与工具卡片共用该开关与延迟，不做特殊化。
      setAutoSendEnabled(on) {
        this.autoSendEnabled = on;
        const cardMap = (this.curConv && this.curConv.cardMap) || {};
        if (on) {
          Object.keys(cardMap).forEach((id) => {
            const c = cardMap[id];
            if (c && c.isTool && !c.executed && !c.skipped && !c._cdTimer) this.scheduleExecute(c);
          });
          // 未发送的外部卡片一并进入倒计时
          this.externalCards.forEach((c) => {
            if (c && c.status === 'pending' && !c._cdTimer) this.scheduleExternalSend(c);
          });
        } else {
          Object.keys(cardMap).forEach((id) => {
            const c = cardMap[id];
            if (!c) return;
            if (c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; }
            c.countdown = 0;
            c.phase = '';
          });
          this.externalCards.forEach((c) => {
            if (c && c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; }
            if (c) { c.countdown = 0; c.phase = ''; }
          });
          this.toast('已关闭自动回传');
        }
      },
      // 点击执行：跳过倒计时立即执行（卡片出现后若开启自动回传会自动倒计时触发）
      onExecuteClick(card) {
        if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
        card.countdown = 0;
        card.phase = '';
        this.executeCard(card);
      },
      execButtonLabel(card) {
        if (this.autoSendEnabled && card.phase === 'exec' && card.countdown > 0) return '执行 ' + card.countdown + 's';
        return card.executed ? '重新执行' : '执行';
      },
      // 跳过卡片：取消其倒计时与自动回传，标记为已跳过，不再自动执行
      skipCard(card) {
        if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
        card.countdown = 0;
        card.phase = '';
        card.skipped = true;
        if (this._persist) this._persist();
        this.toast('已跳过该卡片');
      },
      // 倒计时后自动执行（与自动发送共享 autoSendDelay）
      scheduleExecute(card) {
        if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
        const secs = Math.max(1, Math.round((this.autoSendDelay || 3000) / 1000));
        card.phase = 'exec';
        card.countdown = secs;
        const tick = () => {
          card.countdown -= 1;
          if (card.countdown > 0) {
            card._cdTimer = setTimeout(tick, 1000);
          } else {
            card._cdTimer = null;
            card.countdown = 0;
            card.phase = '';
            this.executeCard(card);
          }
        };
        card._cdTimer = setTimeout(tick, 1000);
      },
      // 倒计时后把结果写回网页 AI 输入框并触发发送
      scheduleAutoSend(card) {
        if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
        const secs = Math.max(1, Math.round((this.autoSendDelay || 3000) / 1000));
        card.phase = 'send';
        card.countdown = secs;
        const tick = () => {
          card.countdown -= 1;
          if (card.countdown > 0) {
            card._cdTimer = setTimeout(tick, 1000);
          } else {
            card._cdTimer = null;
            card.countdown = 0;
            card.phase = '';
            window.parent.postMessage({ type: 'auto_send', text: this.resultText(card) }, '*');
            this.toast('已回传结果到网页 AI');
          }
        };
        card._cdTimer = setTimeout(tick, 1000);
      }
    },
    render() {
      // 代码块就地渲染为卡片：工具调用可直接执行，普通代码提供复制
      const codeCard = (block) => {
        const card = this.cardMap[block.id];
        const isTool = !!(card && card.isTool);
        const kids = [
          h('div', { class: 'code-head' }, [
            isTool
              ? h('span', { class: 'toolname' }, '工具调用 · ' + card.tool)
              : h('span', { class: 'lang' }, String(block.lang || 'code').toUpperCase()),
            h('span', { class: 'head-controls' }, [
              isTool ? h('span', { class: 'badge ' + card.status }, this.statusText(card.status)) : null,
              isTool ? h('label', { class: 'auto-send' }, [
                h('input', {
                  type: 'checkbox',
                  checked: this.autoSendEnabled,
                  onChange: (e) => this.setAutoSendEnabled(e.target.checked)
                }),
                '自动'
              ]) : null,
              (isTool && card.countdown > 0) ? h('span', { class: 'countdown' }, (card.phase === 'send' ? '回传 ' : '执行 ') + card.countdown + 's') : null
            ])
          ])
        ];
        if (isTool) {
          kids.push(h('pre', { class: 'params-json' }, JSON.stringify(card.parameters, null, 2)));
          kids.push(h('div', { class: 'row' }, [
            h('button', {
              onClick: () => this.onExecuteClick(card),
              disabled: card.status === 'running'
            }, this.execButtonLabel(card)),
            // 跳过：取消该卡片的倒计时与自动回传，用户可自行决定不执行
            (!card.skipped && !card.executed) ? h('button', { class: 'secondary', onClick: () => this.skipCard(card) }, '跳过') : null,
            card.skipped ? h('span', { class: 'hint' }, '已跳过') : null,
            (card.result != null || card.error) ? h('button', { onClick: () => this.copy(this.resultText(card)) }, '复制结果') : null
          ]));
          if (card.status === 'done') kids.push(h('pre', { class: 'result' }, this.fmt(card.result)));
          if (card.status === 'error') {
            kids.push(h('pre', { class: 'error' }, card.error || this.fmt(card.result)));
            if (card.origin) {
              kids.push(h('div', { class: 'origin-line' },
                '错误分类：' + card.origin +
                (card.origin === 'tool_internal'
                  ? ' — 本地工具代码缺陷，请用 hot_reload_fix 修代码，改参数无效'
                  : '')));
            }
            if (card.stack) {
              const open = !!this.stackOpen[card.id];
              kids.push(h('div', { class: 'row' }, [
                h('button', { onClick: () => { this.stackOpen[card.id] = !open; } },
                  open ? '收起堆栈' : '查看完整堆栈')
              ]));
              if (open) kids.push(h('pre', { class: 'stack' }, card.stack));
            }
          }
        } else {
          kids.push(h('pre', { class: 'code-body' }, block.code));
          kids.push(h('div', { class: 'row' }, [
            h('button', { onClick: () => this.copy(block.code) }, '复制代码')
          ]));
        }
        return h('div', { class: 'code-card', key: block.id }, kids);
      };

      // 按块类型渲染，保留原网页的内容分类（标题 / 段落 / 列表 / 引用 / 表格 / 思考 / 代码）
      const renderBlock = (block, j, mKey) => {
        const k = mKey + '-' + j;
        if (block.type === 'heading') return h('div', { class: 'mb-h', key: k }, block.text);
        if (block.type === 'paragraph') return h('p', { class: 'mb-p', key: k }, block.text);
        if (block.type === 'list') {
          return block.ordered
            ? h('ol', { class: 'mb-list', key: k }, block.items.map((t, n) => h('li', { key: n }, t)))
            : h('ul', { class: 'mb-list', key: k }, block.items.map((t, n) => h('li', { key: n }, t)));
        }
        if (block.type === 'quote') return h('blockquote', { class: 'mb-quote', key: k }, block.text);
        if (block.type === 'table') {
          return h('table', { class: 'mb-table', key: k }, [
            h('tbody', block.rows.map((row, r) => h('tr', { key: r },
              row.map((cell, c) => h(r === 0 ? 'th' : 'td', { key: c }, cell))
            )))
          ]);
        }
        if (block.type === 'thinking') {
          const open = !!this.thinkOpen[k];
          return h('div', { class: 'mb-think', key: k }, [
            h('div', { class: 'mb-think-head', onClick: () => { this.thinkOpen[k] = !open; } },
              (open ? '▾' : '▸') + ' 思考过程'),
            open ? h('div', { class: 'mb-think-body' }, block.text) : null
          ]);
        }
        if (block.type === 'code') return codeCard(block);
        return h('p', { class: 'mb-p', key: k }, block.text || '');
      };

      // 取消息的首行纯文本，作为折叠态下的预览摘要
      const firstLine = (m) => {
        const blocks = m.blocks || [];
        for (let i = 0; i < blocks.length; i++) {
          const b = blocks[i];
          const t = b && (b.text || b.code || (b.items && b.items.join(' ')) || '');
          if (t) return String(t).split('\n')[0].slice(0, 120);
        }
        return '';
      };

      // 判断一条助手消息是否为结果信封（debug-chrome-res）：
      // 用于让这类消息与用户消息一样默认折叠。
      const isResultMessage = (m) => {
        if (m.role !== 'assistant') return false;
        const blocks = m.blocks || [];
        for (let i = 0; i < blocks.length; i++) {
          const b = blocks[i];
          const raw = b && (b.type === 'code' ? b.code : b.text);
          if (!raw) continue;
          const objs = this.extractJsonObjects(raw);
          for (let j = 0; j < objs.length; j++) {
            if (objs[j] && objs[j].type === 'debug-chrome-res') return true;
          }
        }
        return false;
      };

      // 折叠行渲染：用户消息与结果信封共用
      const collapsibleItem = (m, mKey, cls, avatar, store) => {
        const open = !!store[mKey];
        return h('div', { class: 'msg ' + cls, key: mKey }, [
          h('div', { class: 'avatar' }, avatar),
          h('div', { class: 'bubble' }, [
            h('div', { class: 'user-head', onClick: () => { store[mKey] = !open; } }, [
              h('span', { class: 'caret' }, open ? '▾' : '▸'),
              h('span', { class: 'who-inline' }, m.name || 'AI'),
              open ? null : h('span', { class: 'user-preview' }, firstLine(m))
            ]),
            open ? h('div', { class: 'blocks' }, (m.blocks || []).map((b, j) => renderBlock(b, j, mKey))) : null
          ])
        ]);
      };

      const messageItem = (m, i, originalIdx) => {
        const mKey = (m.role || 'msg') + '-' + originalIdx;
        const isUser = m.role === 'user';
        // 用户消息：默认折叠，点标题行展开 / 收起
        if (isUser) return collapsibleItem(m, mKey, 'user', '我', this.userOpen);
        // 结果信封消息：与用户消息一致，默认折叠
        if (isResultMessage(m)) return collapsibleItem(m, mKey, 'assistant result-msg', 'AI', this.resOpen);
        return h('div', { class: 'msg assistant', key: mKey }, [
          h('div', { class: 'avatar' }, 'AI'),
          h('div', { class: 'bubble' }, [
            h('div', { class: 'who' }, m.name || 'AI'),
            h('div', { class: 'blocks' }, (m.blocks || []).map((b, j) => renderBlock(b, j, mKey)))
          ])
        ]);
      };

      // 1) System Prompt：已迁移到设置页。设置面板本身由 ⚙ 开合，
      //    内部再套一层「隐藏/显示」属于重复开关，故去掉，只保留复制。
      const systemPromptBlock = h('div', { class: 'sp-block' }, [
        h('div', { class: 'card-head' }, [
          h('span', 'System Prompt（请复制粘贴到网页 AI 对话框）'),
          h('button', { onClick: () => this.copy(this.systemPrompt) }, '复制')
        ]),
        h('pre', { class: 'sysprompt' }, this.systemPrompt)
      ]);

      // 2) 工具（内置 + 自定义）：合并「支持的工具」与「后端工具上 / 下线」为同一区块
      const unifiedToolRow = (tool) => {
        const name = tool.name;
        const on = !this.configTools[name] || this.configTools[name].enabled !== false;
        return h('li', { class: 'tool-row', key: 'b:' + name }, [
          h('div', { class: 'tree-node', onClick: () => this.toggleTool(name) }, [
            h('span', { class: 'caret' }, this.expanded[name] ? '▾' : '▸'),
            h('b', name),
            h('span', { class: 'desc' }, tool.description)
          ]),
          h('div', { class: 'tool-btns' }, [
            h('button', {
              class: 'switch ' + (on ? 'on' : 'off'),
              onClick: () => this.setToolEnabled(name, !on)
            }, on ? '已上线' : '已下线')
          ]),
          this.expanded[name] ? h('div', { class: 'tree-detail' }, [
            h('p', tool.description),
            h('table', { class: 'params' }, [
              h('thead', h('tr', [h('th', '参数'), h('th', '类型'), h('th', '必填'), h('th', '说明')])),
              h('tbody', (tool.parameters || []).map((p) => h('tr', { key: p.name }, [
                h('td', h('code', p.name)),
                h('td', p.type),
                h('td', p.required ? '是' : '否'),
                h('td', p.description)
              ])))
            ]),
            name === 'run_command' ? this.renderRunCommandLanguages(tool) : null,
            h('pre', { class: 'usage' }, this.usageOf(tool))
          ]) : null
        ]);
      };
      const customToolRow = (t) => {
        const name = t.name;
        return h('li', { class: 'tool-row custom', key: 'c:' + name }, [
          h('div', { class: 'tree-node', onClick: () => this.toggleCustom(name) }, [
            h('span', { class: 'caret' }, this.customExpanded[name] ? '▾' : '▸'),
            h('b', name),
            h('span', { class: 'desc' }, '[自定义] ' + t.description)

          ]),
          h('div', { class: 'tool-btns' }, [
            h('div', { class: 'tool-actions' }, [
              h('span', { class: 'badge custom' }, 'skill: ' + t.skill_name),
              h('button', { onClick: () => this.editCustom(name) }, '编辑'),
              h('button', { class: 'danger', onClick: () => this.removeCustom(name) }, '删除')
            ]),
            h('button', {
              class: 'switch ' + (t.enabled ? 'on' : 'off'),
              onClick: () => this.setCustomEnabled(name, !t.enabled)
            }, t.enabled ? '已上线' : '已下线')
          ]),
          this.customExpanded[name] ? h('div', { class: 'tree-detail' }, [
            h('p', t.description),
            h('table', { class: 'params' }, [
              h('thead', h('tr', [h('th', '参数'), h('th', '类型'), h('th', '必填'), h('th', '说明')])),
              h('tbody', (t.parameters || []).map((p) => h('tr', { key: p.name }, [
                h('td', h('code', p.name)),
                h('td', p.type),
                h('td', p.required ? '是' : '否'),
                h('td', p.description)
              ])))
            ]),
            h('p', { class: 'desc' }, '脚本：' + t.script + '　解释器：' + t.interpreter + '　参数风格：' + t.arg_style),
            this.customEditing[name]
              ? h('div', { class: 'custom-edit' }, [
                h('textarea', {
                  value: this.customEdit[name] || '',
                  onInput: (e) => { this.customEdit[name] = e.target.value; }
                }),
                h('div', { class: 'row' }, [
                  h('button', { onClick: () => this.saveCustom(name) }, '保存'),
                  h('button', { onClick: () => { this.customEditing[name] = false; } }, '取消')
                ])
              ])
              : null
          ]) : null
        ]);
      };
      const customInstallBlock = h('div', { class: 'custom-install' }, [
        h('div', { class: 'card-head' }, [h('span', '安装自定义工具（来自标准 skill 的 tool.json）')]),
        h('label', ['skill 目录（选包含 skill 的父目录）', h('div', { class: 'dir-row' }, [
          h('input', {
            type: 'text', value: this.skillScanDir,
            onInput: (e) => { this.skillScanDir = e.target.value; }
          })//,
          //h('button', { onClick: () => this.pickDir() }, '选择目录')
        ])]),
        h('div', [
          h('button', { onClick: () => this.scanSkills() }, '扫描可安装'),
          h('button', { onClick: () => this.scanDefaults() }, '用默认目录扫描')
        ]),
        this.scanResults.length
          ? h('div', { class: 'scan-results' },
            this.scanResults.map((skill) => h('div', { class: 'scan-skill' }, [
              h('div', skill.skill_name + (skill.error ? '（解析失败：' + skill.error + '）' : '')),
              ...(skill.tools || []).map((ts) => h('div', { class: 'scan-tool' }, [
                h('span', ts.name + ' — ' + ts.description),
                h('button', {
                  disabled: ts.installed,
                  onClick: () => this.installSkill(skill.skill_dir, ts.name)
                }, ts.installed ? '已安装' : '安装')
              ]))
            ]))
          )
          : null
      ]);

      // 规则模块：用户自定义约定文件（rules/*.md），可增删改；AI 通过 list_rules / read_rule 按需读取
      const rulesBlock = h('div', { class: 'sp-block' }, [
        h('div', { class: 'card-head' }, [
          h('span', '规则（' + this.rules.length + '）（AI 通过 list_rules / read_rule 按需读取）'),
          h('button', { onClick: () => { this.rulesOpen = !this.rulesOpen; } }, this.rulesOpen ? '▾' : '▸')
        ]),
        this.rulesDir ? h('div', { class: 'hint' }, '规则目录：' + this.rulesDir) : null,
        this.rulesOpen ? h('div', { class: 'rule-list' }, [
          h('div', { class: 'rule-new' }, [
            h('input', {
              type: 'text', value: this.newRuleName, placeholder: '新规则名（字母/数字/下划线/连字符）',
              onInput: (e) => { this.newRuleName = e.target.value; }
            }),
            h('button', { onClick: () => this.createRule() }, '新建')
          ]),
          this.rules.length
            ? this.rules.map((r) => h('div', { class: 'rule-item', key: r.name }, [
              h('div', { class: 'tree-node', onClick: () => this.toggleRule(r.name) }, [
                h('span', { class: 'caret' }, this.rulesExpanded[r.name] ? '▾' : '▸'),
                h('b', r.name),
                h('span', { class: 'desc' }, r.summary)
              ]),
              h('div', { class: 'tool-btns' }, [
                h('label', { class: 'rule-priority' }, [
                  '读取优先级',
                  h('select', {
                    value: r.priority || 'on-demand',
                    onChange: (e) => this.setRulePriority(r.name, e.target.value)
                  }, this.rulePriorities.map((p) => h('option', { value: p.value }, p.label)))
                ]),
                h('button', { onClick: () => this.editRule(r.name) }, '编辑'),
                h('button', { class: 'danger', onClick: () => this.removeRule(r.name) }, '删除')
              ]),
              this.rulesExpanded[r.name] ? h('div', { class: 'tree-detail' }, [
                this.rulesEditing[r.name]
                  ? h('div', { class: 'custom-edit' }, [
                    h('textarea', {
                      value: this.rulesEdit[r.name] || '',
                      onInput: (e) => { this.rulesEdit[r.name] = e.target.value; }
                    }),
                    h('div', { class: 'row' }, [
                      h('button', { onClick: () => this.saveRule(r.name) }, '保存'),
                      h('button', { onClick: () => { this.rulesEditing[r.name] = false; } }, '取消')
                    ])
                  ])
                  : h('pre', { class: 'rule-view' }, this.rulesEdit[r.name] || r.summary)
              ]) : null
            ]))
            : h('div', { class: 'empty' }, '（暂无规则，可新建；首次启动会自动生成 self-healing 规则）')
        ]) : null
      ]);

      // 已安装的自定义工具名集合：内置工具列表需排除它们，避免「上线后」与自定义列表重复出现两条同名
      const customNames = new Set(this.customTools.map((t) => t.name));
      // 3) 设置面板：配置统一由后端 config.yaml 管理（不从浏览器存储）
      const settings = this.settingsOpen ? h('div', { class: 'settings' }, [
        h('div', { class: 'settings-bar' }, [
          h('span', '设置'),
          h('button', { class: 'close', onClick: () => { this.settingsOpen = false; } }, '✕')
        ]),
        h('div', { class: 'settings-body' }, [
          // 1) System Prompt：供复制粘贴到网页 AI 对话框
          systemPromptBlock,
          // 2) 规则：用户自定义约定文件，AI 按需读取
          rulesBlock,
          // 3) 工具（内置 + 自定义）：合并「支持的工具」与「后端工具上 / 下线」，
          //    开关写回后端，立即影响 System Prompt。默认折叠。
          h('div', { class: 'sp-block' }, [
            h('div', { class: 'card-head' }, [
              h('span', { title: '内置 + 自定义；点名称展开参数，开关控制是否上线到 System Prompt' }, '工具'),
              h('button', { onClick: () => { this.toolsOpen = !this.toolsOpen; } }, this.toolsOpen ? '▾' : '▸')
            ]),
            this.toolsOpen ? h('div', { class: 'tool-list' }, [
              ...this.tools.filter((t) => !customNames.has(t.name)).map(unifiedToolRow),
              ...this.customTools.map(customToolRow),
              (this.tools.length === 0 && this.customTools.length === 0)
                ? h('div', { class: 'hint' }, '（未读取到工具列表，请先连接后端）')
                : null
            ]) : null,
            customInstallBlock
          ]),
          // 4) 通用配置：连接地址 / 端口 / 自动回传延迟
          h('div', { class: 'sp-block' }, [
            h('div', { class: 'card-head' }, [h('span', '通用配置')]),
            // 自动延迟配置 + 全局自动开关（右侧按钮直接切换）
            h('label', ['自动回传延迟(秒)', h('div', { class: 'inline-row' }, [
              h('input', {
                type: 'number', min: '1', step: '1',
                value: this.autoSendDelay / 1000,
                onInput: (e) => { const v = parseInt(e.target.value, 10); this.autoSendDelay = (v > 0 ? v : 3) * 1000; }
              }),
              h('button', {
                class: 'switch ' + (this.autoSendEnabled ? 'on' : 'off'),
                title: '切换全局自动：开启后卡片自动倒计时执行并回传',
                onClick: () => this.setAutoSendEnabled(!this.autoSendEnabled)
              }, this.autoSendEnabled ? '自动：开' : '自动：关')
            ])]),
            h('div', { class: 'hint' }, '开启自动后：卡片会倒计时自动执行，执行完再倒计时自动发送到网页 AI（两者共用此时长）；卡片上可单独跳过。'),
            (!this.flaskOk) ? h('div', { class: 'flask-warn' }, '⚠ 无法连接 Flask 服务（' + this.flaskError + '），当前使用内置工具目录。') : null,
            h('br'),
            // Flask 连接地址：由后端 config.yaml 下发，仅会话内使用，不持久化到浏览器
            h('label', ['Flask 连接地址（来自后端 config.yaml）',
              h('div', { class: 'ro' }, this.config.flaskUrl)]),
            h('div', [
              h('button', { onClick: () => this.initBackend() }, '重新连接后端'),
              h('span', { class: 'hint' }, '改了 config.yaml 端口后点此重新发现')
            ]),
            // 端口不一致告警：配置端口已改但服务仍在旧端口运行（尚未重启）
            this.portMismatch
              ? h('div', { class: 'flask-warn' },
                '⚠ 配置端口 ' + this.config.flaskPort + ' 与服务实际端口不一致：服务仍在旧端口运行。'
                + '请重启 Flask 服务监听新端口，然后点「重新连接后端」。插件当前仍连接旧端口，未使用未生效的新配置。')
              : null,
            // 端口配置：写入后端 config.yaml，重启 Flask 后生效
            h('label', ['Flask 端口（重启服务生效）', h('input', {
              type: 'number', value: this.config.flaskPort,
              onInput: (e) => { this.config.flaskPort = e.target.value; }
            })]),
            h('div', [
              h('button', { onClick: () => this.savePort() }, '保存端口'),
              h('span', { class: 'hint' }, '端口修改需重启 Flask 服务才能监听新端口')
            ]),
            // 工具结果 JSON 体积上限：写入后端 config.yaml，即时生效
            h('label', ['工具结果体积上限(字符)', h('input', {
              type: 'number', min: '1', step: '1',
              value: this.maxJsonChars,
              onInput: (e) => { const v = parseInt(e.target.value, 10); this.maxJsonChars = v > 0 ? v : 100000; }
            })]),
            h('div', [
              h('button', { onClick: () => this.saveMaxJsonChars() }, '保存上限'),
              h('span', { class: 'hint' }, 'search_content / read_file 等结果超过此字符数会报错，提示 AI 缩小范围')
            ])
          ]),
          // 5) 历史卡片管理：严格按创建时间倒序展示，可单删 / 清空
          h('div', { class: 'sp-block' }, [
            h('div', { class: 'card-head' }, [
              h('span', '历史卡片管理（' + this.sortedHistoryCards.length + '）'),
              h('button', { onClick: () => this.clearAllCards() }, '清空')
            ]),
            this.sortedHistoryCards.length
              ? h('div', { class: 'history-list' },
                this.sortedHistoryCards.map((c) => {
                  const time = c.createdAt ? new Date(c.createdAt).toLocaleString() : '';
                  // 外部卡片与工具/代码卡片字段不同：按 _kind 分别生成可读标签
                  const label = c._kind === 'external'
                    ? ('外部卡片 · ' + (c.title || c.type || ''))
                    : (c.isTool ? ('工具 · ' + (c.tool || '')) : ('代码 · ' + (c.lang || '')));
                  return h('div', { class: 'history-item', key: c.id }, [
                    h('span', { class: 'h-time' }, time),
                    h('span', { class: 'h-label' }, label),
                    h('span', { class: 'badge ' + c.status }, this.statusText(c.status)),
                    h('button', { class: 'h-del', onClick: () => this.removeHistoryCard(c) }, '删除')
                  ]);
                }))
              : h('div', { class: 'empty' }, '（暂无历史卡片）')
          ])
        ]),
      ]) : null;

      // 外部卡片：与工具卡片视觉一致，以徽标区分来源；倒计时与自动发送受全局开关控制
      const externalCardView = (c) => {
        const kids = [
          h('div', { class: 'code-head' }, [
            h('span', { class: 'toolname' }, '外部卡片 · ' + (c.title || '')),
            h('span', { class: 'head-controls' }, [
              h('span', { class: 'badge external' }, 'external'),
              c.countdown > 0 ? h('span', { class: 'countdown' }, '发送 ' + c.countdown + 's') : null
            ])
          ]),
          h('pre', { class: 'params-json' }, c.content)
        ];
        if (c.status === 'pending') {
          kids.push(h('div', { class: 'row' }, [
            h('button', { onClick: () => this.onExternalSendClick(c) }, '发送到网页 AI')
          ]));
        }
        if (c.status === 'waiting_reply') {
          kids.push(h('div', { class: 'origin-line' }, '等待网页 AI 按约定 id 返回结果…'));
        }
        if (c.status === 'done') kids.push(h('pre', { class: 'result' }, this.fmt(c.result)));
        return h('div', { class: 'code-card external-card', key: c.id }, kids);
      };

      // 外部卡片与对话消息合并到同一镜像流：均按「最新在前」排列
      const externalSorted = this.externalCards.slice().sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
      const mirrorItems = externalSorted.map((c) => externalCardView(c))
        .concat(this.reversedMessages.map((m, i) => messageItem(m, i, this.messages.length - 1 - i)));

      // 4) 主界面只保留网页对话镜像（外部卡片与工具卡片一并呈现）
      const mirrorBlock = h('section', { class: 'card' }, [
        h('div', { class: 'card-head' }, [
          h('span', '网页对话镜像（' + this.messages.length + '）'),
          h('span', { class: 'head-actions' }, [
            h('button', { onClick: () => this.reparse() }, '重新解析'),
            h('button', { onClick: () => this.copyConversationJson() }, '复制JSON')
          ])
        ]),
        this.curConv.title ? h('div', { class: 'conv-title' }, '当前会话：' + this.curConv.title) : null,
        mirrorItems.length
          ? h('div', { class: 'mirror' }, mirrorItems)
          : h('div', { class: 'empty' }, '（等待网页对话内容…）')
      ]);

      const body = h('div', { class: 'm-body' }, [mirrorBlock]);

      return h('div', { class: 'mirror-app' }, [
        h('header', { class: 'm-header' }, [
          h('div', { class: 'title' }, [
            'AI 工具调用镜像',
            this.siteKey ? h('span', { class: 'site-badge' }, this.siteKey) : null
          ]),
          h('div', { class: 'actions' }, [
            h('button', {
              title: this.panelSide === 'left' ? '切换到右侧挂靠' : '切换到左侧挂靠',
              onClick: () => this.switchPanelSide()
            }, this.panelSide === 'left' ? '⇥' : '⇤'),
            h('button', { title: '设置', onClick: () => { this.settingsOpen = !this.settingsOpen; } }, '⚙'),
            h('button', { title: '关闭', onClick: () => this.closePanel() }, '✕')
          ])
        ]),
        settings,
        body,
        this.toastMsg ? h('div', { class: 'toast' }, this.toastMsg) : null
      ]);
    }
  });

  app.mount('#app');
})();
