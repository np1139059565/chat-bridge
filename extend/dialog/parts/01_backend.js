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

  /** 依次完成：发现后端 → 取配置 → 取自定义工具 → 取工具目录 → 取规则。
   *  外部卡片轮询不在这里启动，改由面板可见性驱动（见 setPanelVisible）。 */
  M.initBackend = async function () {
    await this.discoverFlask();
    await this.loadConfig();
    await this.loadCustomTools();
    // 桥接配置要先读：语音开关决定 prompt 是否注入朗读约定，须在生成前就位。
    await this.loadBridge();   // 远程桥接配置与状态（失败不阻断其余功能）
    await this.loadWeixin();   // 微信通道配置与登录状态（失败不阻断其余功能）
    await this.loadWecom();    // 企业微信通道配置与状态（失败不阻断其余功能）
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

  /** 配置从后端配置文件读取（不存浏览器）：连接地址、端口、工具上下线状态。 */
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
      // 工具配置：声明 + 当前值，供设置页按类型通用渲染
      if (cfg.tool_config) this.toolConfig = cfg.tool_config;
      // 系统级配置：目录与队列上限，独立于工具
      if (cfg.system_config) this.systemConfig = cfg.system_config;
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

  /** 工具上 / 下线：写回后端 runtime.yaml，并立即刷新工具目录（影响 System Prompt）。 */
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

  /**
   * 设置某个工具的某项配置，并立即写回后端。
   *
   * 本地先更新（界面立即反映），再提交后端；失败回滚，避免显示已生效但实际未存。
   * @param {string} tool 工具名
   * @param {string} key  配置键
   * @param {*} value     新值
   */
  M.setToolConfig = async function (tool, key, value) {
    const block = this.toolConfig || (this.toolConfig = {});
    const rows = block[tool] || [];
    const spec = rows.find((r) => r.key === key);
    const before = spec ? spec.value : undefined;
    if (spec) spec.value = value;
    try {
      await D.apiFetch(this, '/config', {
        method: 'POST',
        body: { tool_config: { [tool]: { [key]: value } } }
      });
    } catch (e) {
      if (spec) spec.value = before;
      this.toast('保存失败：' + e);
    }
  };

  /** 保存 run_command 支持的语言列表（卡片勾选）并写回后端 runtime.yaml。 */
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
   * 工具结果 JSON 体积上限：写回后端 runtime.yaml。
   * tools_impl 每次调用现读配置文件，因此改完即时生效，无需重启。
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
