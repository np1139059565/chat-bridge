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

  /** 依次完成：发现后端 → 取配置 → 取自定义工具 → 取工具目录 → 取规则。
   *  外部卡片轮询不在这里启动，改由面板可见性驱动（见 setPanelVisible）。 */
  M.initBackend = async function () {
    await this.discoverFlask();
    await this.loadConfig();
    await this.loadCustomTools();
    // 桥接配置要先读：语音开关决定 prompt 是否注入朗读约定，须在生成前就位。
    await this.loadBridge();   // 远程桥接配置与状态（失败不阻断其余功能）
    await this.fetchTools();   // 内部会刷新技能说明段落并生成 System Prompt
    await this.loadRules();
    // 外部卡片轮询不在此启动，改由面板可见性驱动（见 setPanelVisible）。
  };

  /** 技能数据：说明段落与技能清单，注入 System Prompt。 */
  M.loadPromptSections = async function () {
    try {
      const data = await D.apiFetch(this, '/prompt_sections', {
        headers: { 'Accept': 'application/json' }
      });
      this.promptSections = (data && data.sections) || [];
      this.skills = (data && data.skills) || [];
      this.skillsManage = (data && data.skillsManage) || [];
    } catch (e) {
      this.promptSections = [];
      this.skills = [];
      this.skillsManage = [];
    }
    this.systemPrompt = this.generateSystemPrompt();
  };

  // ---------- 外部卡片：轮询后端取待投递卡片，渲染后自动发送并等待结果 ----------

  /**
   * 启动外部卡片轮询（幂等）。
   * 固定 5 秒一次：外部卡片是「用户主动发送」的低频事件，
   * 秒级轮询没有必要，还会持续占用后端与浏览器资源。
   * 仅面板可见时运行：面板关闭即停，避免关闭后仍把卡片取走。
   */
  M.startExternalPoll = function () {
    if (this._extTimer) return;
    this._extTimer = setInterval(() => this.pollExternalCards(), 5000);
    this.pollExternalCards();
  };

  /**
   * 停止外部卡片轮询：清掉定时器。
   * 面板关闭时调用，此后本对话框不再取外部卡片，卡片留给其他打开的页面。
   */
  M.stopExternalPoll = function () {
    if (this._extTimer) {
      clearInterval(this._extTimer);
      this._extTimer = null;
    }
  };

  /**
   * 按面板可见性启停外部卡片轮询。
   * 可见才轮询、关闭即停：面板关着时不该再收到并消费外部卡片。
   * @param {boolean} visible 面板是否可见
   */
  M.setPanelVisible = function (visible) {
    const was = this.panelVisible;
    this.panelVisible = !!visible;
    // 可见才轮询、关闭即停：外部卡片与桥接状态共用同一生命周期
    if (visible) { this.startExternalPoll(); this.startBridgeStatusPoll(); }
    else { this.stopExternalPoll(); this.stopBridgeStatusPoll(); }
    // 仅在可见性真的变化时打印：避免重复消息刷屏。
    if (was !== this.panelVisible) {
      log('面板可见性：' + (this.panelVisible ? '打开 → 启动卡片轮询' : '关闭 → 停止卡片轮询'));
    }
  };

  /** 轮询后端待投递卡片；新卡片入列，并按全局自动开关决定是否进入倒计时。 */
  M.pollExternalCards = async function () {
    // 面板不可见时不取卡片：关闭的面板不该再消费外部卡片，
    // 把它留给其他打开的页面。
    if (!this.panelVisible) return;
    try {
      const data = await D.apiFetch(this, '/api/cards/pending', {
        headers: { 'Accept': 'application/json' }
      });
      const cards = (data && data.cards) || [];
      // 只在真取到卡片时打印：轮询每 5 秒一次，逐次打印会淹没控制台。
      // 取到卡片说明本对话框当前可见且在消费卡片；若关闭后仍看到这条，
      // 即说明可见性同步没生效。
      if (cards.length) log('取到外部卡片 ' + cards.length + ' 张：', cards.map((c) => c.id).join(', '));
      // 确保当前会话对象存在再写入：curConv 在会话未建立时会回退到共享的
      // EMPTY_CONV，直接 push 会把卡片写进这个全局空壳，随后创建真实会话对象时
      // 读不到，表现为「卡片莫名消失」。
      const conv = this.ensureConv(this.activeConv);
      const added = [];
      cards.forEach((c) => {
        // QQ 图片卡片：不下发网页 AI，直接把图片贴进输入框（截图逆向流程）
        if (this.consumeQqImage(c)) return;
        // 抽屉命令卡片：不下发网页 AI，直接执行本地动作（桥接指令）
        if (this.consumeBridgeCommand(c)) return;
        if (this.externalCards.some((x) => x.id === c.id)) return;
        // 锚点定位：记下创建时「当前分支末端」那条消息的树 key，
        // 渲染时据此把卡片插到该消息之后。会话尚无消息时锚点为空，卡片排在最前。
        const bk = conv.branchKeys || [];
        const anchorKey = bk.length ? bk[bk.length - 1] : '';
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
          skipped: false,   // 是否已被用户跳过（跳过后不再自动发送）
          // anchorKey：结构定位锚点（创建时分支末端的树 key）。
          anchorKey: anchorKey,
          // key：条目 key，与消息的 'pid-id' 同构（两段、连字符连接）。
          // 左段取锚点消息 id（无锚点用 '0'，与消息树根一致）；
          // 右段是卡片短 id（'x' + 哈希），替代 36 字符 UUID，避免巨长。
          key: (anchorKey ? anchorKey.slice(anchorKey.indexOf('-') + 1) : '0')
            + '-' + ('x' + D.hashStr(c.id)),
          nonce: ''
        };
        this.externalCards.push(card);
        added.push(card);
        // 卡片已入列，回执后端确认收货；若在回执前中断，后端判为未确认，
        // 下次轮询可再取走，不会出现「取走了却没展示、还再也拿不到」的情况。
        this.confirmCardDelivered(c.id);
        log('外部卡片已投递', card.id, card.title);
      });
      // 与工具卡片一致：仅当全局自动开关开启时才自动发送，且本轮只自动发送
      // 最新一张（积压多张时不全部触发，其余等待用户手动发送）。
      if (this.autoSendEnabled && added.length) {
        // 从响应式列表末位回读（Vue 代理），改它才会驱动界面刷新；
        // added 里存的是原始对象，改它不刷新。末位即最新卡片。
        this.scheduleExternalSend(this.externalCards[this.externalCards.length - 1]);
      }
      // 新卡片入列后立即写盘：待处理卡片此前只存在内存里，刷新会整批丢失。
      // 恢复进行中不写盘，避免尚未合并完的存档被空列表覆盖。
      if (added.length && this._persist) this._persist();
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
   * 发送即结束：投递完成即置为完成态。
   * 后续进展由网页 AI 通过 push_message 工具主动推送给用户。
   */
  M.sendExternalCard = async function (card) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    card.countdown = 0;
    card.phase = '';
    // 输入信封：{ type, request, page_url }，不携带 id。
    // page_url 为卡片发起方所在页面的地址（由调试扩展随卡片一并传来），
    // 让网页 AI 知道这条外部卡片来自哪个页面。
    const sourceUrl = (card.payload && card.payload.page_url) || card.page_url || '';
    const envelope = {
      type: card.type || 'external-call',
      nonce: this.ensureNonce(card),
      request: card.content,
      page_url: sourceUrl
    };
    const text = JSON.stringify(envelope, null, 2);
    // 经统一发送队列回传：与工具卡片结果、质量告警串行，避免同时到达互相顶掉。
    D.enqueueSend({ type: 'auto_send', text: text });
    // 执行完成即结束：立即置为完成态并记为已执行过（供刷新/切会话后恢复）
    card.status = 'done';
    card.executed = true;
    card.result = {
      delivered: true,
      note: '已发送到网页 AI。任务执行与进展由网页 AI 通过 push_message 工具主动推送到调试抽屉。'
    };
    if (this._persist) this._persist();
    this.toast('外部卡片已发送到网页 AI');
  };

  /**
   * 按 id 或对象取回本会话中的外部卡片原件。
   * 历史卡片管理列表里的条目是浅拷贝，直接改它不会影响真实数据，
   * 因此所有操作入口都先经此函数取回原件。
   * @param {Object|string} idOrCard 卡片对象或卡片 id
   * @returns {Object|null} 本会话中的卡片原件
   */
  M.findExternalCard = function (idOrCard) {
    if (!idOrCard) return null;
    const id = typeof idOrCard === 'object' ? idOrCard.id : idOrCard;
    if (!id) return null;
    // 优先按 id 查回原件；查不到（例如新建后尚未入列）时回退到传入对象本身
    return (this.externalCards || []).find((c) => c.id === id) || (typeof idOrCard === 'object' ? idOrCard : null);
  };

  /**
   * 回执后端：该卡片已生成并展示，此后不再投递。
   * 在卡片推入列表（即进入渲染流程）后调用；
   * 调用失败仅记录——后端仍视其为未确认，下次轮询会再次投递，
   * 接收方按卡片 id 去重，不会出现重复卡片。
   * @param {string} cardId 卡片 id
   */
  M.confirmCardDelivered = async function (cardId) {
    if (!cardId) return;
    try {
      await D.apiFetch(this, '/api/cards/' + encodeURIComponent(cardId) + '/delivered', {
        method: 'POST'
      });
    } catch (e) { /* 回执失败不阻断；下次轮询会重新投递，接收方按 id 去重 */ }
  };

  /** 手动发送（自动开关未开启时使用）。 */
  M.onExternalSendClick = function (idOrCard) {
    const card = this.findExternalCard(idOrCard);
    if (card) this.sendExternalCard(card);
  };

  /**
   * 跳过某张外部卡片：取消其倒计时并标记为已跳过，不再自动发送。
   * 与工具卡片的跳过语义一致；已发送过的卡片不提供跳过。
   * @param {Object|string} idOrCard 卡片对象或卡片 id
   */
  M.skipExternalCard = function (idOrCard) {
    const card = this.findExternalCard(idOrCard);
    if (!card) return;
    D.cancelCountdown(card);
    card.skipped = true;
    if (this._persist) this._persist();
    this.toast('已跳过该外部卡片');
  };

  /**
   * 后端地址发现：config 不存浏览器，启动时探测若干候选端口找到 /config 端点。
   * 这样即使 config.yaml 改了端口，也无需在浏览器里手动填地址。
   */
  M.discoverFlask = async function () {
    // 优先用上次探通的地址：端口改过后，刷新页面也能直接连回新端口，
    // 不必再靠固定候选列表瞎试。
    let saved = '';
    try {
      saved = await new Promise((res) => {
        chrome.storage.local.get(['aiMirrorFlaskUrl'], (r) => res((r && r.aiMirrorFlaskUrl) || ''));
      });
    } catch (e) { /* 存储不可用则忽略 */ }
    // 探测地址来源：上次探通的地址 → 当前连通地址 → 设置页端口输入框构造的地址。
    // 不再附带写死的候选端口，避免改端口后仍被旧端口悄悄接住；
    // 端口输入框的默认值（可被用户修改）是唯一的兜底依据。
    const byPort = this.config.flaskPort ? ('http://127.0.0.1:' + this.config.flaskPort) : '';
    const candidates = [
      saved,
      this.config.flaskUrl,
      byPort
    ].filter(Boolean);
    for (let i = 0; i < candidates.length; i++) {
      const base = candidates[i].replace(/\/+$/, '');
      try {
        const r = await fetch(base + '/config', { headers: { 'Accept': 'application/json' } });
        if (r.ok) {
          this.config.flaskUrl = base;
          // 落盘：让「改端口 + 刷新」后仍能连回同一地址。
          try { chrome.storage.local.set({ aiMirrorFlaskUrl: base }); } catch (e) { /* 忽略 */ }
          return;
        }
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
    // 清掉上一站点的待写计时器：它们持有旧会话 id，稍后触发会把数据串到别的站点。
    if (this._persistTimers) {
      Object.keys(this._persistTimers).forEach((id) => {
        clearTimeout(this._persistTimers[id]);
        delete this._persistTimers[id];
      });
    }
    // 会话「已从存档恢复」标记按站点隔离：不同站点的同名会话对应不同存档键。
    this._convReady = {};
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
      const cfg = await D.apiFetch(this, '/config', {
        headers: { 'Accept': 'application/json' }
      });
      // 注意：flaskUrl 由 discoverFlask() 探测到的「实际可连通地址」决定，
      // 绝不能用 cfg.flask.url（配置文件声明的端口）覆盖——否则端口改了
      // 但服务还没重启时会连到空端口，导致连接断开。
      if (cfg.flask && cfg.flask.port) this.config.flaskPort = cfg.flask.port;
      if (cfg.tools) this.configTools = cfg.tools;
      if (cfg.limits && cfg.limits.max_json_chars) this.maxJsonChars = cfg.limits.max_json_chars;
      if (cfg.default_profile) this.config.profile = cfg.default_profile;
      // 配置端口与实际连通端口不一致 = 端口已改但服务尚未重启（需重启才生效）
      // 从当前实际连通的地址里取端口做比对；取不到就不判不一致，
      // 避免用一个写死的端口去猜。
      const m = /:(\d+)/.exec(this.config.flaskUrl || '');
      const livePort = m ? parseInt(m[1], 10) : NaN;
      this.portMismatch = !isNaN(livePort) && livePort !== parseInt(this.config.flaskPort, 10);
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
      await D.apiFetch(this, '/config', {
        method: 'POST',
        body: { tools: { [name]: { enabled: enabled } } }
      });
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
      await D.apiFetch(this, '/config', {
        method: 'POST',
        body: { tools: { [name]: { enabled: enabled, languages: languages } } }
      });
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
   * 工具结果 JSON 体积上限：写回后端 config.yaml。
   * tools_impl 每次调用现读 config.yaml，因此改完即时生效，无需重启。
   */
  M.saveMaxJsonChars = async function () {
    const v = parseInt(this.maxJsonChars, 10);
    if (!v || v <= 0) { this.toast('上限必须为正整数'); return; }
    try {
      const data = await D.apiFetch(this, '/config', {
        method: 'POST',
        body: { limits: { max_json_chars: v } },
        lenientJson: true
      });
      if (!data.success) throw new Error(data.error || '保存失败');
      this.maxJsonChars = v;
      this.toast('已保存体积上限：' + v + ' 字符');
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };
})();
