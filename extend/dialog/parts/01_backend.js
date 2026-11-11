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

  /**
   * 把当前扩展版本打到后端日志，供排查「跑的是不是最新版」。
   *
   * 为什么由抽屉打：抽屉是扩展页面，请求本地服务不受混合内容策略限制，
   * 是唯一稳定可达后端的通道。内容脚本的日志也经这里转发。
   *
   * 版本号取自 manifest（chrome.runtime.getManifest），不手写，避免与实际不符。
   * 失败静默：版本上报失败不影响任何功能。
   */
  M.reportVersion = function () {
    // 抽屉侧只能拿到自身构建标识（内容脚本的常量在页面上下文，读不到）。
    // 这里同时报清单版本与抽屉侧标识，便于区分「抽屉新、内容脚本旧」的情况。
    let manifestVer = 'unknown';
    try { manifestVer = chrome.runtime.getManifest().version; } catch (e) { /* 忽略 */ }
    const items = [{
      tag: 'ext-版本',
      msg: '抽屉已加载 清单版本=' + manifestVer
        + ' 时间=' + new Date().toISOString()
    }];
    D.apiFetch(this, '/api/web/client_log', { method: 'POST', body: items })
      .catch(function () { /* 静默 */ });
  };

  /** 依次完成：发现后端 → 取配置 → 取自定义工具 → 取工具目录 → 取规则。
   *  外部卡片轮询不在这里启动，改由面板可见性驱动（见 setPanelVisible）。 */
  M.initBackend = async function () {
    await this.discoverFlask();
    // 启动即把版本打到后端日志：
    // 排查「页面跑的到底是不是最新扩展」时，直接看日志即可，
    // 不必让人每次都去开浏览器控制台核对。
    // 放在 discoverFlask 之后：此时地址已确定，请求才发得出去。
    this.reportVersion();
    await this.loadConfig();
    await this.loadCustomTools();
    // 桥接配置要先读：语音开关决定 prompt 是否注入朗读约定，须在生成前就位。
    await this.loadBridge();   // 远程桥接配置与状态（失败不阻断其余功能）
    await this.loadSystemPromptBase();  // 标准 System Prompt 主体（失败回退旧版全量拼装）
    await this.loadWeixin();   // 微信通道配置与登录状态（失败不阻断其余功能）
    await this.loadWecom();    // 企业微信通道配置与状态（失败不阻断其余功能）
    await this.fetchTools();   // 内部会刷新技能说明段落并生成 System Prompt
    await this.loadRules();
    // 外部卡片轮询不在此启动，改由面板可见性驱动（见 setPanelVisible）。
    // 补发抽屉就绪前积压的内容脚本日志：
    // 页面刷新瞬间内容脚本就开始发日志，那时本抽屉还没探测到后端地址，
    // 那批日志会被暂存（见 05_messages.js 的 ext_log 分支）。此处统一补发。
    this.flushPendingExtLogs();
  };

  /**
   * 补发抽屉就绪前积压的内容脚本日志。
   *
   * 有上限地一次发完；失败静默——日志不能反过来拖累主流程。
   */
  M.flushPendingExtLogs = function () {
    const items = this.pendingExtLogs || [];
    if (!items.length) return;
    this.pendingExtLogs = [];
    D.apiFetch(this, '/api/web/client_log', { method: 'POST', body: items })
      .catch(function () { /* 静默 */ });
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


  /**
   * 后端地址发现：config 不存浏览器，启动时探测若干候选端口找到 /config 端点。
   * 这样即使 runtime.yaml 改了端口，也无需在浏览器里手动填地址。
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
    if (!k || k === this.siteKey) return;
    log('切换站点：', this.siteKey || '(初始)', '→', k);
    this.siteKey = k;
    // 切站必须按新 siteKey 重读缓存并重建站点草稿，否则一直显示上一站点档案
    const _self = this;
    Promise.resolve(this.configBackend
      ? this.configLoadAndDiff(this.configBackend)
      : (this.loadConfig ? this.loadConfig() : null)).then(function () {
        if (_self.siteKey !== k) return;
        _self.siteProfiles = (_self.configCache && _self.configCache.profiles) || {};
        if (_self.resetSiteProfDraft) _self.resetSiteProfDraft();
        if (_self.recomputeConfigDiff) _self.recomputeConfigDiff();
      }).catch(function () {});
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

  /** 配置从后端配置文件读取（不存浏览器）：连接地址、端口、工具上下线状态。 */
  /** 刷新：拉后端母版做比对，派生 state 一律以本地缓存为准（不覆盖本地修改）。 */
  M.loadConfig = async function () {
    try {
      const backend = await D.apiFetch(this, '/config', {
        headers: { 'Accept': 'application/json' }
      });
      await this.configLoadAndDiff(backend);
      const cache = this.configCache || backend;
      if (cache.tools) this.configTools = cache.tools;
      if (cache.tool_config) this.toolConfig = cache.tool_config;
      if (cache.system_config) this.systemConfig = cache.system_config;
      if (cache.limits && cache.limits.max_json_chars) this.maxJsonChars = cache.limits.max_json_chars;
      if (cache.default_profile) this.config.profile = cache.default_profile;
      if (backend.flask && backend.flask.port) this.config.flaskPort = backend.flask.port;
      const m = /:(\d+)/.exec(this.config.flaskUrl || '');
      const livePort = m ? parseInt(m[1], 10) : NaN;
      this.portMismatch = !isNaN(livePort) && livePort !== parseInt(this.config.flaskPort, 10);
      log('loadConfig: 后端=' + this.config.flaskUrl, '本地缓存已恢复',
        '端口一致=' + !this.portMismatch);
    } catch (e) {
      this.configOffline = true;
      this.configBackend = null;
      this.configDiff = {};
      this.configPublicDiff = {};
      log('loadConfig 失败：离线，使用本地缓存', e);
    }
  };

  M.setToolEnabled = async function (name, enabled) {
    if (!this.configTools[name]) this.configTools[name] = {};
    this.configTools[name].enabled = enabled;
    try {
      await this.syncPublicToCache();
      this.toast((enabled ? '已上线：' : '已下线：') + name + '（本地，点【覆盖】生效）');
    } catch (e) {
      this.configTools[name].enabled = !enabled;
      this.toast('保存失败：' + e);
    }
  };

  /**
   * 设置某个工具（或 system 分组）的某项配置，并立即写回后端。
   *
   * 本地先更新（界面立即反映），再提交后端；失败回滚，避免显示已生效但实际未存。
   * system 分组的声明在 this.systemConfig（GET 的 system_config 数组），与工具分组
   * （this.toolConfig 对象，键为工具名）形状不同，查找口径必须分开：原实现只查
   * toolConfig，system 分组查不到 spec、乐观更新失效，spec.value 停留旧值；任何
   * 重渲染（5 秒状态轮询等触发）都会按旧 spec.value 重设输入框 DOM 值，表现为
   * 「系统级配置改完立即弹回旧值」（后端保存链其实正常，CONFIG_SCHEMA 含 system）。
   * @param {string} tool 工具名或 'system'
   * @param {string} key  配置键
   * @param {*} value     新值
   */
  M.setToolConfig = async function (tool, key, value) {
    const rows = (tool === 'system')
      ? (this.systemConfig || [])
      : ((this.toolConfig || {})[tool] || []);
    const spec = rows.find((r) => r.key === key);
    const before = spec ? spec.value : undefined;
    if (spec) spec.value = value;
    try {
      await this.syncPublicToCache();
    } catch (e) {
      if (spec) spec.value = before;
      this.toast('保存失败：' + e);
    }
  };

  /** 保存 run_command 支持的语言列表（卡片勾选）并写回后端 runtime.yaml。 */
  M.setRunCommandLanguages = async function (languages) {
    const name = 'run_command';
    const enabled = !this.configTools[name] || this.configTools[name].enabled !== false;
    if (!this.configTools[name]) this.configTools[name] = {};
    this.configTools[name].enabled = enabled;
    this.configTools[name].languages = languages;
    try {
      await this.syncPublicToCache();
      this.toast('已更新 run_command 支持语言（本地，点【覆盖】生效）');
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

  /** 渲染 run_command 支持语言的勾选卡片（在工具展开详情中展示）。 */
  M.renderRunCommandLanguages = function (tool) {
    const all = ['cmd', 'powershell', 'shell', 'git', 'python'];
    const cfgLangs = (this.configTools.run_command && this.configTools.run_command.languages) || [];
    const current = (tool && tool.languages) || cfgLangs || [];
    return h('div', { class: 'lang-checks' + (D.publicFieldClass
      ? D.publicFieldClass(this, 'tools', 'run_command', 'languages', current) : '') }, [
      D.publicRestoreBtn
        ? D.publicRestoreBtn(this, 'tools', 'run_command', 'languages', current) : null,
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
   * 工具结果 JSON 体积上限：写回后端 runtime.yaml。
   * tools_impl 每次调用现读配置文件，因此改完即时生效，无需重启。
   */
  M.saveMaxJsonChars = async function () {
    const v = parseInt(this.maxJsonChars, 10);
    if (!v || v <= 0) { this.toast('上限必须为正整数'); return; }
    this.maxJsonChars = v;
    try {
      await this.syncPublicToCache();
      this.toast('体积上限已存本地：' + v + ' 字符（点【覆盖】生效）');
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

})();
