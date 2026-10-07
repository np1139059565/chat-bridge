// 模块：extend/dialog/parts/01b_bridge.js
// 用途：远程桥接（QQ ↔ 网页 AI）的全部前端逻辑。
//       从 01_backend.js（后端交互）与 05_messages.js（消息处理）中抽出，
//       使各文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 说明：这些方法原本挂在 D.methods 上，抽出后仍挂在同一命名空间，
//       调用方式不变（app.js 装配时统一并入 Vue 实例）。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 取某内置指令的某个参数值（内置指令参数的通用读取口）。
   *
   * 前端不写死指令名与参数键：二者都来自后端参数声明。
   * @param {Object} ctx Vue 实例
   * @param {string} cmd 指令名（不带 /）
   * @param {string} key 参数键
   * @returns {string} 参数值；无则空串
   */
  D.cmdParam = function (ctx, cmd, key) {
    const p = ((ctx && ctx.bridgeCmdParams) || {})[cmd] || {};
    return p[key] || '';
  };

  /**
   * 提取卡片结果里的本地图片路径；没有则返回空串。
   * 截图结果结构：{ data: { screenshot: '...', saved: { name, path } } }
   * @param {Object} result 卡片结果
   * @returns {string} 本地路径
   */
  function cardImagePath(result) {
    if (!result || typeof result !== 'object') return '';
    const d = result.data;
    if (!d || typeof d !== 'object') return '';
    const saved = d.saved;
    if (!saved || typeof saved !== 'object') return '';
    return saved.path || '';
  }

  /**
   * 提取一条消息上「需要额外推送 QQ」的卡片结果。
   *
   * 为什么只提截图：文本结果经「回传网页 AI → 成为一条消息 → 镜像抓取」
   * 本来就能到 QQ，若在此再推一次会重复。而截图经 auto_send_image 贴进
   * 输入框后，镜像只抓文本块、抓不到图片，必须由这里额外推。
   * @param {Object} node 消息树节点
   * @returns {Array} 待推结果 [{id, tool, status, path}]
   */
  function extractCardResults(node) {
    const cards = (node && node.cards) || {};
    const out = [];
    Object.keys(cards).forEach((k) => {
      const c = cards[k];
      if (!c || !c.isTool) return;
      // 只推已出结果的卡片；pending / running 尚无结果
      if (c.status !== 'done' && c.status !== 'error') return;
      // 只挑出含本地图片路径的结果
      const path = cardImagePath(c.result);
      if (!path) return;
      out.push({ id: c.id || k, tool: c.tool || '', status: c.status, path: path });
    });
    return out;
  }

  /**
   * 加载远程桥接配置与状态。
   * 凭证（AppID / AppSecret）从后端读回，供设置页回填。
   */
  M.loadBridge = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/config', {
        headers: { 'Accept': 'application/json' }
      });
      const cfg = data.config || {};
      const st = data.status || {};
      this.bridgeEnabled = !!cfg.enabled;
      this.bridgeAppId = cfg.app_id || '';
      this.bridgeAppSecret = cfg.app_secret || '';
      // 以唯一默认值为基底合并后端配置：后端缺某字段时落到「默认开/默认关」，
      // 而不是未定义。此前基底漏掉 check_* 四个键，导致它们恒为 undefined，
      // 开关显示成「关」（真值判定）、检测却照跑（!== false 判定），出现「没开也告警」。
      this.bridgePush = Object.assign({}, D.DEFAULT_BRIDGE_PUSH, cfg.push || {});
      this.bridgeCommands = cfg.commands || [];
      // 内置指令参数：来自配置，键为指令名（不带 /），值为该指令的参数字典。
      // 走通用机制，不针对某条指令特殊化（如 /md 的 selector 就在这里）。
      this.bridgeCmdParams = cfg.command_params || {};
      this.bridgeConnected = !!st.connected;
      // 参数声明（有哪些内置指令有参数）：从后端拉取，前端不写死指令名。
      try {
        const pd = await D.apiFetch(this, '/api/bridge/command_params', {
          headers: { 'Accept': 'application/json' }
        });
        this.bridgeCmdParamDefs = (pd && pd.defs) || [];
      } catch (e) {
        this.bridgeCmdParamDefs = [];
      }
      // 标记配置已成功加载：状态轮询据此判断是否需要重试加载。
      this._bridgePushLoaded = true;
    } catch (e) {
      // 后端不可达：本次配置未取到，开关停留在默认值。
      // 标记未加载，交由状态轮询自动重试，直至取到后端配置——
      // 否则初始化时后端未就绪，开关会永久停在默认值，出现
      // 「后端已关某检测、前端仍按默认开跑」的错位。
      this.bridgeConnected = false;
      this._bridgePushLoaded = false;
      log('桥接配置加载失败（将由状态轮询重试）：' + e);
    }
    // 指令说明文本从后端拉取（与 /h 同源），避免设置页手写说明与指令表漂移。
    try {
      const hd = await D.apiFetch(this, '/api/bridge/help', {
        headers: { 'Accept': 'application/json' }
      });
      this.bridgeHelpText = (hd && hd.help) || '';
    } catch (e) {
      this.bridgeHelpText = '';
    }
  };

  /**
   * 启动桥接状态轮询（幂等）。
   *
   * 为什么需要轮询：loadBridge 只在抽屉初始化时读一次状态，
   * 而那一刻 QQ 长连接往往还在建立中，读到的是「未连接」。
   * 之后连接成功了界面也不会再读，于是永远停在「未连接」。
   * 轮询让指示灯能反映真实状态变化。
   */
  M.startBridgeStatusPoll = function () {
    if (this._bridgeStatusTimer) return;
    this._bridgeStatusTimer = setInterval(() => this.refreshBridgeStatus(), 5000);
    this.refreshBridgeStatus();
  };

  /** 停止桥接状态轮询。 */
  M.stopBridgeStatusPoll = function () {
    if (this._bridgeStatusTimer) {
      clearInterval(this._bridgeStatusTimer);
      this._bridgeStatusTimer = null;
    }
  };

  /** 刷新桥接连接状态（轻量请求，仅取状态）。
   *
   * 兼作「配置加载失败」的兜底重试：初始化时后端可能尚未就绪，
   * loadBridge 会失败、开关停在默认值且永不更新。此处借每 5 秒的心跳，
   * 在检测到配置从未成功加载时重新拉取一次，直到取到后端真值为止。
   */
  M.refreshBridgeStatus = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/status', {
        headers: { 'Accept': 'application/json' }
      });
      this.bridgeConnected = !!data.connected;
      this.bridgeLastEvent = data.lastEvent || '';
      this.bridgeIntents = data.intents || 0;
      // 配置从未成功加载：借心跳补拉一次（成功后 _bridgePushLoaded 置真，不再重试）
      if (this._bridgePushLoaded === false) {
        await this.loadBridge();
      }
    } catch (e) {
      this.bridgeConnected = false;
    }
  };

  /**
   * 保存远程桥接配置：写回后端并重启桥接。
   * 凭证或开关变化需要重建长连接，因此保存后后端会自动重启。
   */
  M.saveBridge = async function () {
    try {
      // 注意：这里不传 commands。saveBridge 是全量覆盖式保存，
      // 若把 bridgeCommands 一起提交，抽屉重建时它先为空数组，
      // 用户一旦在配置读回前碰了开关，就会用空数组覆盖掉已存的指令。
      // 指令的增删改走 /api/bridge/commands 独立接口（见下）。
      const data = await D.apiFetch(this, '/api/bridge/config', {
        method: 'POST',
        body: {
          enabled: this.bridgeEnabled,
          app_id: this.bridgeAppId,
          app_secret: this.bridgeAppSecret,
          // 内置指令参数：通用字段，不针对某条指令特殊化
          command_params: this.bridgeCmdParams,
          push: this.bridgePush
        }
      });
      const st = data.status || {};
      this.bridgeConnected = !!st.connected;
      this.toast(this.bridgeEnabled ? '桥接已保存并重启' : '桥接已关闭');
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

  /** 切换某类消息的推送开关（用户 / 工具 / AI / 思考 / 语音）。
   *
   * 语音开关会改变 System Prompt（是否注入朗读文本约定），
   * 故切换后必须重建 prompt，否则界面显示已开、prompt 里却没有对应约定。
   */
  M.toggleBridgePush = function (kind) {
    this.bridgePush[kind] = !this.bridgePush[kind];
    if (kind === 'voice') {
      this.systemPrompt = this.generateSystemPrompt();
    }
    this.saveBridge();
  };

  // 指令的增删改与元素选择入口已移到 01c_bridge_cmd.js，
  // 便于控制本文件长度，并让指令管理集中在一处。

  /**
   * 把当前可见切片上报给远程桥接层（QQ ↔ 网页 AI）。
   *
   * 注意：上报的是**全量可见切片**，不是「本轮新增」——
   * sendPage 每次都全量推送，桥接层自己与「已推送集合」比对取差集。
   * 抽屉在这里只是「小喇叭」：把看见的消息喊给桥接层，
   * 分类、去重、往 QQ 推全由桥接层完成。抽屉不用懂 QQ。
   *
   * 推送来源：
   *  - generate：AI 刚说完新话，必推；
   *  - tool：工具卡片刚出结果，也要推——否则 QQ 端只看得到工具调用、看不到结果；
   *  - scroll / switch / manual：用户回看历史或切上下文，不推（推了会刷屏）。
   * @param {string} [reason] 触发来源
   */
  M.reportToBridge = function (reason) {
    if (reason !== 'generate' && reason !== 'tool') return;
    // 面板未打开时不推：关闭抽屉就代表用户此刻不需要远程工作
    if (!this.panelVisible) return;
    const conv = this.curConv || {};
    const tree = conv.msgTree || {};
    const messages = [];
    (conv.visibleKeys || []).forEach((k) => {
      const node = tree[k];
      if (!node || node.deleted) return;
      const id = window.AIMirrorDomUtils.messageFingerprint(node);
      // md：AI 回复的 Markdown 原文（由复制按钮采集而来）。
      // 推送时后端优先用它，保格式；没有则退回 blocks 拼的纯文本。
      // cardResults：该消息上工具卡片的执行结果。工具调用块只表达「调了什么」，
      // 结果存在节点的 cards 里，不上报的话 QQ 端只看得到调用、看不到结果。
      messages.push({
        id: id, role: node.role, blocks: node.blocks || [], md: node.md || '',
        // key：消息在树中的 key（pid-id 格式）。供网页版逐条核对消息块是否完整、
        // 有无缺块——它能唯一定位一条消息，比纯文本更可靠。
        key: k,
        // source：来源标记（user / assistant / tool），供后端直接读字段定类，
        // 无需再扫字符串反推。缺字段时后端回退到内容判断。
        source: node.source || '',
        cardResults: extractCardResults(node)
      });
    });
    if (!messages.length) return;
    // 静默上报：失败不打扰用户，桥接层没开时后端直接返回 0
    try {
      D.apiFetch(this, '/api/bridge/report', {
        method: 'POST',
        body: { conversationId: this.activeConv, messages: messages }
      }).catch(function () { /* 桥接未启用时忽略 */ });
    } catch (e) { /* 忽略 */ }
  };


  /**
   * 清空所有会话。
   * 复用界面的 clearAllConversations，传 true 跳过确认框——
   * 远程指令来自 QQ，用户不在电脑前，无法点确认。
   */
  M._bridgeClearAllSessions = function () {
    this.clearAllConversations(true);
  };

  /** 清空当前会话的消息列表（保留外部卡片，供远程指令使用）。 */
  M._bridgeClearMessages = function () {
    const conv = this.curConv;
    if (!conv) return;
    this.eachCard(conv, (c) => { if (c && c._cdTimer) { clearTimeout(c._cdTimer); c._cdTimer = null; } });
    conv.msgTree = {};
    conv.visibleKeys = [];
    conv.branchKeys = [];
    conv.orphanSlice = [];
    Object.keys(this.entryChecked).forEach((k) => { delete this.entryChecked[k]; });
    Object.keys(this.entryOpen).forEach((k) => { delete this.entryOpen[k]; });
    if (this._persist) this._persist();
    this.toast('已清空消息列表');
  };

  /** 复制 System Prompt 并自动粘贴发送给网页 AI。 */
  M._bridgeSendSystemPrompt = function () {
    const text = this.systemPrompt || '';
    if (!text) { this.toast('System Prompt 为空'); return; }
    this.copy(text);
    window.parent.postMessage({ type: 'auto_send', text: text }, '*');
    this.toast('已复制并发送 System Prompt');
  };
})();
