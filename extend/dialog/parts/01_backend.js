// 模块：extend/dialog/parts/01_backend.js
// 用途：与本地 Flask 服务的交互：后端地址发现、配置读写、工具上下线、
//       端口与体积上限保存、外部卡片轮询与发送。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;
  // 渲染函数依赖 Vue 全局构建提供的 h
  const h = Vue.h;

  /** 轻提示：显示一条短消息，1.6 秒后自动消失。 */
  M.toast = function (msg) {
    this.toastMsg = msg;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { this.toastMsg = ''; }, 1600);
  };

  /** 切换抽屉挂靠侧：右 ⇄ 左。外框位置由内容脚本负责（iframe 运行在页面上下文）。 */
  M.switchPanelSide = function () {
    const next = this.panelSide === 'left' ? 'right' : 'left';
    this.panelSide = next;
    window.parent.postMessage({ type: 'set_panel_side', side: next }, '*');
  };

  /** 关闭抽屉：请求内容脚本隐藏 iframe。 */
  M.closePanel = function () {
    window.parent.postMessage({ type: 'close_panel' }, '*');
  };

  /** 依次完成：发现后端 → 取配置 → 取自定义工具 → 取工具目录 → 取规则 → 启动外部卡片轮询。 */
  M.initBackend = async function () {
    await this.discoverFlask();
    await this.loadConfig();
    await this.loadCustomTools();
    await this.fetchTools();   // 内部会刷新技能说明段落并生成 System Prompt
    await this.loadRules();
    this.startExternalPoll();
  };

  /** 技能说明段落：注入 System Prompt 末尾。 */
  M.loadPromptSections = async function () {
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
  };

  // ---------- 外部卡片：轮询后端取待投递卡片，渲染后自动发送并等待结果 ----------

  /** 启动外部卡片轮询（幂等）。 */
  M.startExternalPoll = function () {
    if (this._extTimer) return;
    this._extTimer = setInterval(() => this.pollExternalCards(), 1000);
    this.pollExternalCards();
  };

  /** 轮询后端待投递卡片；新卡片入列，并按全局自动开关决定是否进入倒计时。 */
  M.pollExternalCards = async function () {
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
          executed: false,
          // 统一时间戳：与文字消息同字段、同量纲（毫秒）。
          // 渲染时所有条目一律按 _ts 排序，无任何类型特殊处理。
          _ts: (c.created_at || Date.now()),
          createdAt: c.created_at || Date.now()
        };
        this.externalCards.push(card);
        log('外部卡片已投递', card.id, card.title);
        // 与工具卡片一致：仅当全局自动开关开启时才自动倒计时发送；
        // 未开启时等待用户手动发送。
        if (this.autoSendEnabled) this.scheduleExternalSend(card);
      });
    } catch (e) { /* 后端未就绪时静默重试 */ }
  };

  /**
   * 倒计时后把卡片内容发送到网页 AI（与工具卡片共用 autoSendDelay 与倒计时机制）。
   * 与工具卡片一致：倒计时期间 status 保持 pending、只改 phase/countdown，
   * 这样中途关闭「自动」时卡片能自然退回待发送态，不会卡死（历史缺陷）。
   */
  M.scheduleExternalSend = function (card) {
    // 倒计时状态机由 D.startCountdown 统一提供（工具卡片与外部卡片共用）
    D.startCountdown(this, card, 'send', () => this.sendExternalCard(card));
  };

  /**
   * 立即发送外部卡片到网页 AI。
   * 发送即结束：不再等待网页 AI 回传结果信封，避免卡片长期悬挂。
   * 后续进展由网页 AI 通过 push_message 工具主动推送给用户。
   */
  M.sendExternalCard = async function (card) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    card.countdown = 0;
    card.phase = '';
    // 输入信封：{ type, request }。
    // 不再携带 id —— 外部卡片已取消「等待回复」，无需与网页 AI 的返回结果配对。
    const envelope = { type: card.type || 'debug-chrome-req', request: card.content };
    const text = JSON.stringify(envelope, null, 2);
    window.parent.postMessage({ type: 'auto_send', text }, '*');
    // 执行完成即结束：立即置为完成态并记为已执行过（供刷新/切会话后恢复）
    card.status = 'done';
    card.executed = true;
    card.result = {
      delivered: true,
      note: '已发送到网页 AI。任务执行与进展由网页 AI 通过 push_message 工具主动推送到调试抽屉。'
    };
    if (this._persist) this._persist();
    // 唤醒后端挂起的创建请求，让抽屉的 POST /api/cards 立即返回（不再空等超时）
    await this.ackExternalCard(card.id, card.result);
    this.toast('外部卡片已发送到网页 AI');
  };

  /** 手动发送（自动开关未开启时使用）。 */
  M.onExternalSendClick = function (card) {
    this.sendExternalCard(card);
  };

  /** 通知后端唤醒挂起的创建请求：外部卡片不再等待 AI 回复，仅回一个「已投递」确认。 */
  M.ackExternalCard = async function (cardId, result) {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      await fetch(base + '/api/cards/' + encodeURIComponent(cardId) + '/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result: result })
      });
    } catch (e) { /* 回填失败仅记录 */ }
    return true;
  };

  /**
   * 后端地址发现：config 不存浏览器，启动时探测若干候选端口找到 /config 端点。
   * 这样即使 config.yaml 改了端口，也无需在浏览器里手动填地址。
   */
  M.discoverFlask = async function () {
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
  };

  /** 切换网站：数据与设置都按站点隔离，互不干扰（配置是全局的，无需按站点重载）。 */
  M.applySite = function (key) {
    const k = key || 'unknown-site';
    if (k === this.siteKey) return;
    log('切换站点：', this.siteKey || '(初始)', '→', k);
    this.siteKey = k;
    // 清空上一站点的数据视图，避免不同站点内容混在一起
    this.conversations = {};
    this.activeConv = '__default__';
    this.ensureConv(this.activeConv);
  };

  /** 会话存档键：带站点前缀，保证 A 站看不到 B 站的记录。 */
  M.convKey = function (id) {
    return 'aiMirrorConv_' + this.siteKey + '__' + (id || '__default__');
  };

  /** 配置从后端 config.yaml 读取（不存浏览器）：连接地址、端口、工具上下线状态。 */
  M.loadConfig = async function () {
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
  };

  /** 工具上 / 下线：写回后端 config.yaml，并立即刷新工具目录（影响 System Prompt）。 */
  M.setToolEnabled = async function (name, enabled) {
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
  };

  /** 保存 run_command 支持的语言列表（卡片勾选）并写回后端 config.yaml。 */
  M.setRunCommandLanguages = async function (languages) {
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
  };

  /** 渲染 run_command 支持语言的勾选卡片（在工具展开详情中展示）。 */
  M.renderRunCommandLanguages = function (tool) {
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
  };

  /**
   * 端口配置：写回后端 config.yaml。端口改动需重启 Flask 才能真正监听新端口，
   * 因此不能立即把连接切到新端口——先保存，再重新探测（若已重启则连新端口，
   * 否则仍连旧端口保持可用），并提示用户重启。
   */
  M.savePort = async function () {
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
  };

  /**
   * 工具结果 JSON 体积上限：写回后端 config.yaml。
   * tools_impl 每次调用现读 config.yaml，因此改完即时生效，无需重启。
   */
  M.saveMaxJsonChars = async function () {
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
  };
})();
