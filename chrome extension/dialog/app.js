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
        systemPrompt: '',
        toolsOpen: true,
        tools: FALLBACK_TOOLS,
        // 多会话：切换左侧历史会话后各自保留消息与卡片执行状态
        activeConv: '__default__',
        conversations: {},
        expanded: reactive({}),
        thinkOpen: reactive({}),
        // 卡片「完整堆栈」展开状态（按卡片 id）
        stackOpen: reactive({}),
        settingsOpen: false,
        // 自定义工具（来自标准 skill 的 tool.json）：列表 / 展开态 / 内联编辑态
        customTools: [],
        customExpanded: reactive({}),
        customEdit: reactive({}),
        customEditing: reactive({}),
        skillScanDir: '',
        scanResults: [],
        scanRoots: [],
        flaskOk: false,
        flaskError: '',
        toastMsg: '',
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
      pageUrl() { return this.curConv.pageUrl; }
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
      log('已发送 request_page 请求重发结构化对话');
    },
    methods: {
      toast(msg) {
        this.toastMsg = msg;
        clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => { this.toastMsg = ''; }, 1600);
      },
      async initBackend() {
        await this.discoverFlask();
        await this.loadConfig();
        await this.fetchTools();
        await this.loadCustomTools();
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
        this.systemPrompt = this.generateSystemPrompt();
      },
      generateSystemPrompt() {
        const tools = this.tools || [];
        // 工具列表只展示名称与描述；参数定义由 AI 在调用前通过 get_tool_params 自行查询。
        // 这样 prompt 体积随工具数增长可控，也避免 AI 凭直觉臆造参数名
        // （不同工具参数名不统一，如 list_dir 用 target_directory、read_file 用 filePath）。
        const listLines = tools.map((t, i) => {
          return `${i + 1}. ${t.name} — ${t.description}`;
        }).join('\n');
        return `本会话通过「AI 工具调用镜像插件」与本地工具服务联动。

【工具调用格式】
当你需要调用工具时，请在一个独立的代码块中返回 JSON，代码块语言标记为 tool：
\`\`\`tool
{
  "tool": "工具名称",
  "parameters": { "参数名": "参数值" }
}
\`\`\`
插件会自动提取该代码块、调用本地服务执行，并把执行结果作为下一条消息回传给你，请据此继续完成任务。

【执行结果回传格式】
插件回传的结果形如（你无需再次调用，直接基于结果继续）：
\`\`\`
[TOOL_RESULT]
工具: 名称
成功: true
结果: ...
[/TOOL_RESULT]
\`\`\`

【支持的工具】
${listLines}

【工具参数查询】
工具的完整参数定义（参数名、类型、必填性、说明）不直接列在此处。
调用任何工具前，请先用 get_tool_params 工具查询该工具的参数定义（传入参数 tool_id = 工具名称），获得完整 schema 后再用正确的参数名调用。

【异常与自愈】
工具调用可能失败或返回"成功但明显不对"的结果，请按下面流程处置，不要盲目重试：
1. 若返回「成功: false」，看错误分类 origin：
   - origin=parameter：这是参数问题（缺失/类型错/取值非法）。先调用 get_tool_params 核对该工具的准确参数名，再用正确参数重试；不要去改工具代码。
   - origin=environment：路径/权限问题，确认路径与权限后重试；不要去改工具代码。
   - origin=tool_internal：这是本地工具代码自身缺陷，反复改参数无效。直接走第 3 步自愈。
2. 若返回「成功: true」但结果与你的请求明显不符（例如：你请求的路径 ≠ 返回的 directory、应为空却非空/应为非空却空、参数像被忽略），先怀疑是参数名写错：
   - 立即调用 get_tool_params 核对准确参数名，若你用了别名（如把 target_directory 写成 path），用正确参数名重试即可——这属于 parameter 问题，不是代码缺陷，不要用 hot_reload_fix。
3. 确认为工具代码缺陷（tool_internal）时，执行自愈：
   - 调用 read_tool_source（参数 tool=出问题的工具名）读取其当前源码，定位缺陷函数；
   - 调用 hot_reload_fix（参数 old_str/new_str 或 content）对 tools_impl.py 打补丁，服务会自动热重载，失败会回滚；
   - 热重载完成后，用「原参数」重新调用该工具验证。不要反复改参数。

请在涉及文件读取、搜索、写入、删除等需求时，主动使用上述工具，并始终以 tool 代码块格式发起调用。`;
      },
      onPageMessage(e) {
        const d = e.data;
        if (!d || !d.type) return;
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
          if (obj && typeof obj === 'object' && obj.tool) {
            return { tool: String(obj.tool), parameters: obj.parameters || {} };
          }
        } catch (e) { /* 不是工具调用，按普通代码块渲染 */ }
        return null;
      },
      ingestMessages(messages) {
        const conv = this.curConv;
        log('ingestMessages 收到', (messages || []).length, '条消息（会话=' + this.activeConv + '）');
        conv.messages = messages || [];
        conv.messages.forEach((m) => {
          (m.blocks || []).forEach((b) => {
            if (b.type !== 'code' || !b.id) return;
            // 已存在：保留执行状态（结果 / 错误 / 是否已执行过）
            if (conv.cardMap[b.id]) return;
            // 只把「助手回答」里的代码块当成可执行的工具调用。
            // 用户消息里的 System Prompt 自带 ```tool 示例块，绝不能生成卡片。
            const call = m.role === 'assistant' ? this.parseToolCall(b) : null;
            conv.cardMap[b.id] = {
              id: b.id,
              lang: b.lang || '',
              code: b.code || '',
              isTool: !!call,
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
              hint: ''
            };
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
      // 回传给 AI 的结果文本。失败时务必带上「错误分类 + 完整堆栈」，
      // 让 AI 能一眼分清是「参数写错」还是「本地工具代码缺陷」。
      resultText(card) {
        const ok = card.status === 'done';
        if (ok) {
          return `[TOOL_RESULT]\n工具: ${card.tool}\n成功: true\n结果:\n${this.fmt(card.result)}\n[/TOOL_RESULT]`;
        }
        const lines = [
          '[TOOL_RESULT]',
          '工具: ' + card.tool,
          '成功: false',
          '错误分类: ' + (card.origin || 'unknown') +
          '（parameter=参数问题，改参数重试即可；environment=路径/权限问题；' +
          'tool_internal=本地工具代码缺陷，必须用 hot_reload_fix 修代码，改参数无效）'
        ];
        if (card.errorType) lines.push('异常类型: ' + card.errorType);
        if (card.error) lines.push('错误信息: ' + card.error);
        const loc = card.location;
        if (loc && loc.file) {
          lines.push('出错位置: ' + loc.file + ':' + loc.line + ' 函数 ' + loc.function);
          if (loc.source) lines.push('  源码: ' + loc.source);
        }
        if (card.hint) lines.push('处置建议: ' + card.hint);
        if (card.stack) lines.push('完整堆栈:\n' + card.stack);
        lines.push('[/TOOL_RESULT]');
        return lines.join('\n');
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
            isTool ? h('span', { class: 'badge ' + card.status }, this.statusText(card.status)) : null
          ])
        ];
        if (isTool) {
          kids.push(h('pre', { class: 'params-json' }, JSON.stringify(card.parameters, null, 2)));
          kids.push(h('div', { class: 'row' }, [
            h('button', { onClick: () => this.executeCard(card), disabled: card.status === 'running' },
              card.executed ? '重新执行' : '执行'),
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

      const messageItem = (m, i) => {
        const mKey = (m.role || 'msg') + '-' + i;
        const isUser = m.role === 'user';
        return h('div', { class: 'msg ' + (isUser ? 'user' : 'assistant'), key: mKey }, [
          h('div', { class: 'avatar' }, isUser ? '我' : 'AI'),
          h('div', { class: 'bubble' }, [
            h('div', { class: 'who' }, m.name || (isUser ? '用户' : 'AI')),
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

      // 已安装的自定义工具名集合：内置工具列表需排除它们，避免「上线后」与自定义列表重复出现两条同名
      const customNames = new Set(this.customTools.map((t) => t.name));
      // 3) 设置面板：配置统一由后端 config.yaml 管理（不从浏览器存储）
      const settings = this.settingsOpen ? h('div', { class: 'settings' }, [
        h('div', { class: 'settings-bar' }, [
          h('span', '设置'),
          h('button', { class: 'close', onClick: () => { this.settingsOpen = false; } }, '关闭 ✕')
        ]),
        h('div', { class: 'settings-body' }, [
          // h('div', { class: 'site-note' },
          //   '当前站点：' + (this.siteKey || '（尚未连接网页）') + '　·　对话记录按站点独立保存，互不串改'),
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
        // 当前站点规则：按域名自动识别，无需手动配置
        // h('label', ['当前站点规则', h('div', { class: 'ro' }, (this.profileId || 'glm'))]),
        // 工具（内置 + 自定义）：合并「支持的工具」与「后端工具上 / 下线」，
        // 开关写回后端，立即影响 System Prompt。
        h('div', { class: 'sp-block' }, [
          h('div', { class: 'card-head' }, [
            h('span', '工具（内置 + 自定义；点名称展开参数，开关控制是否上线到 System Prompt）'),
            h('button', { onClick: () => { this.toolsOpen = !this.toolsOpen; } }, this.toolsOpen ? '收起' : '展开')
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
        (!this.flaskOk) ? h('div', { class: 'flask-warn' }, '⚠ 无法连接 Flask 服务（' + this.flaskError + '），当前使用内置工具目录。') : null,
          systemPromptBlock
        ]),
      ]) : null;

      // 4) 主界面只保留网页对话镜像
      const mirrorBlock = h('section', { class: 'card' }, [
        h('div', { class: 'card-head' }, [
          h('span', '网页对话镜像（' + this.messages.length + '）'),
          h('span', { class: 'head-actions' }, [
            h('button', { onClick: () => this.reparse() }, '重新解析'),
            h('button', { onClick: () => this.copyConversationJson() }, '复制JSON')
          ])
        ]),
        this.curConv.title ? h('div', { class: 'conv-title' }, '当前会话：' + this.curConv.title) : null,
        this.messages.length
          ? h('div', { class: 'mirror' }, this.messages.map((m, i) => messageItem(m, i)))
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
            h('button', { title: '设置', onClick: () => { this.settingsOpen = !this.settingsOpen; } }, '⚙')
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
