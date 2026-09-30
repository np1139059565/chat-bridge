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
      this.bridgePush = Object.assign({ user: true, tool: true, ai: true, thinking: false }, cfg.push || {});
      this.bridgeCommands = cfg.commands || [];
      // Markdown 采集选择器：来自配置（对应内置指令 /md）。
      // 它是配置项而非自定义指令——内置指令本就不可由用户增删。
      this.bridgeMdSelector = cfg.md_selector || '';
      this.bridgeConnected = !!st.connected;
    } catch (e) {
      // 桥接未启用 / 后端不可达：保持默认值，不打扰用户
      this.bridgeConnected = false;
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

  /** 刷新桥接连接状态（轻量请求，仅取状态）。 */
  M.refreshBridgeStatus = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/status', {
        headers: { 'Accept': 'application/json' }
      });
      this.bridgeConnected = !!data.connected;
      this.bridgeLastEvent = data.lastEvent || '';
      this.bridgeIntents = data.intents || 0;
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
          md_selector: this.bridgeMdSelector,
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

  /** 切换某类消息的推送开关（用户 / 工具 / AI / 思考）。 */
  M.toggleBridgePush = function (kind) {
    this.bridgePush[kind] = !this.bridgePush[kind];
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

  // ---------- 抽屉命令：后端下发的远程指令，在浏览器侧执行 ----------

  /**
   * 消费一张抽屉命令卡片。
   *
   * 后端通过卡片总线（type=drawer-command）下发远程指令，
   * 内容形如 {action, params}。这类卡片不下发网页 AI，直接在抽屉里执行，
   * 执行完回执后端、不入 externalCards 列表。
   * @param {Object} c 后端下发的卡片
   * @returns {boolean} 是否为命令卡片（是则调用方跳过后续处理）
   */
  M.consumeBridgeCommand = function (c) {
    if (!c || c.type !== 'drawer-command') return false;
    let payload = c.payload || {};
    // payload 可能未解析，退回解析 content
    if (!payload.action) {
      try { payload = JSON.parse(c.content || '{}'); } catch (e) { payload = {}; }
    }
    // request_id 在 payload 顶层（需回传结果的指令才有），单独传给动作处理
    this._runBridgeAction(payload.action, payload.params || {}, payload.request_id || '');
    // 回执后端：命令已消费，此后不再重复投递
    this.confirmCardDelivered(c.id);
    return true;
  };

  /**
   * 执行一条抽屉命令。
   * @param {string} action 动作名
   * @param {Object} params 动作参数
   * @param {string} requestId 待回传请求 id（需回传结果的指令才有）
   */
  M._runBridgeAction = function (action, params, requestId) {
    if (action === 'clear_all_sessions') { this._bridgeClearAllSessions(); return; }
    if (action === 'clear_messages') { this._bridgeClearMessages(); return; }
    if (action === 'copy_system_prompt') { this._bridgeSendSystemPrompt(); return; }
    if (action === 'toggle_auto_send') {
      // 远程指令没有确认框，直接切换自动回传开关
      this.setAutoSendEnabled(!this.autoSendEnabled);
      this.toast('自动回传已' + (this.autoSendEnabled ? '开启' : '关闭'));
      return;
    }
    if (action === 'set_auto_send') {
      // 显式设置自动回传开关（幂等）：/sa on 或 /sa off
      const on = !!params.on;
      if (on !== this.autoSendEnabled) this.setAutoSendEnabled(on);
      this.toast('自动回传已' + (on ? '开启' : '关闭')); return;
    }
    if (action === 'set_delay') {
      const secs = Number(params.seconds) || 0;
      if (secs > 0) { this.autoSendDelay = secs * 1000; this.toast('自动回传延迟已设为 ' + secs + ' 秒'); }
      return;
    }
    if (action === 'click_element') {
      // 点击动作在页面上下文执行：交给内容脚本处理。
      // 带上 request_id，内容脚本执行后原样回传，抽屉据此把结果发回 QQ。
      window.parent.postMessage({
        type: 'bridge_click_element',
        selector: params.selector || '',
        request_id: requestId || ''
      }, '*');
      this.toast('已下发点击：' + (params.selector || ''));
      return;
    }
    if (action === 'list_sessions') {
      this._bridgeListSessions(requestId);
      return;
    }
    if (action === 'switch_session') {
      this._bridgeSwitchSession(params.index);
      return;
    }
    if (action === 'screenshot') {
      // 截屏在页面上下文执行：请求内容脚本抓取可见区域
      window.parent.postMessage({
        type: 'bridge_screenshot',
        request_id: requestId || ''
      }, '*');
      this.toast('正在截取浏览器屏幕…');
      return;
    }
    if (action === 'copy_latest') {
      // 复制最新结果：走倒计时回传流程（与卡片「复制结果」同一机制）
      this._bridgeCopyLatest();
      return;
    }
    if (action === 'rerun_latest') {
      // 重新执行最新卡片：倒计时执行 → 自动回传
      this._bridgeRerunLatest();
      return;
    }
    if (action === 'reparse') {
      // 重新解析当前网页对话
      this.reparse();
      return;
    }
    if (action === 'switch_side') {
      // 抽屉左右切换：复用界面现成的 switchPanelSide（外框位置由内容脚本负责）
      this.switchPanelSide();
      return;
    }
    if (action === 'open_settings') {
      // 打开设置面板：置位界面开关即可
      this.settingsOpen = true;
      return;
    }
    if (action === 'close_settings') {
      // 从设置返回对话镜像
      this.settingsOpen = false;
      return;
    }
    if (action === 'reconnect_backend') {
      // 重新发现并连接后端（等价界面「重新连接后端」按钮）
      this.initBackend();
      return;
    }
    if (action === 'copy_conversation_json') {
      // 复制当前会话 JSON（等价镜像区「复制」按钮）
      this.copyConversationJson();
      return;
    }
    if (action === 'skip_latest') {
      // 跳过最新一张卡片：取最新卡片后复用现成的 skipCard
      const card = this._latestCard();
      if (!card) { this.toast('没有可跳过的卡片'); return; }
      this.skipCard(card);
      return;
    }
    if (action === 'refresh_page') {
      // 刷新页面并自动打开抽屉：交给内容脚本执行（它掌控页面生命周期）。
      // 先记下「下次加载要自动打开抽屉」的标记，刷新后由内容脚本读取。
      window.parent.postMessage({ type: 'bridge_refresh_page' }, '*');
      this.toast('正在刷新页面…');
      return;
    }
    if (action === 'collect_md') {
      // 手动采集：点按钮取 Markdown，挂到最新 AI 消息上。
      // 自动采集由 reportToBridgeWithMd 在生成结束时触发，
      // 这里是用户主动发指令时的入口。
      this._bridgeCollectMd(params.selector || '');
      return;
    }
  };

  /**
   * 手动采集 Markdown：点复制按钮，内容挂到最新 AI 消息上。
   * @param {string} selector 复制按钮选择器
   */
  M._bridgeCollectMd = function (selector) {
    if (!selector) { this.toast('该采集指令没有绑定选择器'); return; }
    const conv = this.curConv || {};
    const tree = conv.msgTree || {};
    const keys = conv.visibleKeys || [];
    let lastId = '';
    for (let i = keys.length - 1; i >= 0; i--) {
      const node = tree[keys[i]];
      if (node && node.role === 'assistant') {
        lastId = window.AIMirrorDomUtils.messageFingerprint(node);
        break;
      }
    }
    if (!lastId) { this.toast('没有可采集的 AI 回复'); return; }
    this.bridgeMdSelector = selector;   // 手动采集用指令里的选择器
    this.captureMarkdown(lastId);
  };

  /**
   * 取最新一张工具卡片（按消息树顺序，末位即最新）。
   * @returns {Object|null} 卡片对象
   */
  M._latestCard = function () {
    const map = this.allCards ? this.allCards() : {};
    let latest = null;
    Object.keys(map).forEach((id) => {
      const c = map[id];
      if (c && c.isTool) latest = c;
    });
    return latest;
  };

  /** 复制最新卡片结果：走倒计时回传流程，与卡片上的「复制结果」按钮一致。 */
  M._bridgeCopyLatest = function () {
    const card = this._latestCard();
    if (!card) { this.toast('没有可复制的卡片'); return; }
    if (card.result == null && !card.error) { this.toast('最新卡片还没有结果'); return; }
    // 与 onResultClick 的倒计时分支一致：进入 send 阶段，倒计时结束回传
    this.scheduleAutoSend(card);
    this.toast('已开始回传最新结果…');
  };

  /** 重新执行最新卡片：倒计时执行，执行完自动回传（与「自动」开关下的行为一致）。 */
  M._bridgeRerunLatest = function () {
    const card = this._latestCard();
    if (!card) { this.toast('没有可执行的卡片'); return; }
    // 清掉旧状态，让它重新进入执行流程
    card.skipped = false;
    this.executeCard(card, true);
    this.toast('已开始重新执行…');
  };

  /**
   * 按序号切换会话。序号来自 /sessions 的输出（从 1 开始）。
   * @param {number} index 序号
   */
  M._bridgeSwitchSession = function (index) {
    const list = this.convList || [];
    const idx = Number(index) - 1;
    if (!(idx >= 0 && idx < list.length)) {
      this.toast('序号超出范围：' + index);
      return;
    }
    this.selectConversation(list[idx].id);
    this.toast('已切换到：' + (list[idx].title || list[idx].id));
  };

  /**
   * 处理桥接相关的窗口消息（元素选择 / 点击 / 截屏结果）。
   *
   * 从 05_messages.js 的 onPageMessage 中抽出来，避免该文件过长，
   * 也让「桥接的消息」集中在一处。
   * @param {Object} d 消息体
   * @returns {boolean} 是否已处理（true 则调用方直接返回）
   */
  M.handleBridgeMessage = function (d) {
    if (d.type === 'clip_copied') {
      // 页面复制按钮写入剪贴板的内容（主世界 hook 截获后回传）：
      // 挂到目标消息节点，推 QQ 时优先用它。
      this._onClipCopied(d.text || '');
      return true;
    }
    if (d.type === 'picker_result') {
      this.bridgePicking = false;
      // 处于「修改选择器」模式：直接覆盖对应指令的选择器并保存
      if (this.bridgeEditIdx !== null && this.bridgeEditIdx !== undefined) {
        const cmd = (this.bridgeCommands || [])[this.bridgeEditIdx];
        if (cmd) {
          cmd.selector = d.selector || '';
          cmd.page_url = d.page_url || '';
          this.saveBridge();
          this.toast('已更新选择器：' + (d.selector || ''));
        }
        this.bridgeEditIdx = null;
        return true;
      }
      // 新增模式：记下选择器与所在页面，供新增指令使用
      this.bridgePicked = {
        selector: d.selector || '',
        page_url: d.page_url || '',
        tag: d.tag || '',
        confidence: d.confidence || ''
      };
      this.toast('已选中：' + (d.tag || '') + ' ' + (d.selector || ''));
      return true;
    }
    if (d.type === 'picker_stopped') {
      this.bridgePicking = false;
      return true;
    }
    if (d.type === 'click_result') {
      // QQ 指令「点击元素」的执行结果：成功与失败都回传 QQ
      const msg = this._clickResultText(d);
      this._postBridgeResult(d.request_id, msg);
      this.toast(msg);
      return true;
    }
    if (d.type === 'screenshot_result') {
      // QQ 指令「截屏」的执行结果：把图片回传后端
      if (d.ok && d.dataUrl) {
        D.apiFetch(this, '/api/bridge/result', {
          method: 'POST',
          body: { request_id: d.request_id || '', image: d.dataUrl }
        }).catch(function () { /* 忽略 */ });
      } else {
        this._postBridgeResult(d.request_id, '截屏失败：' + (d.error || '未知原因'));
      }
      this.toast(d.ok ? '已截取屏幕' : '截屏失败');
      return true;
    }
    return false;
  };

  /**
   * 把指令执行结果回传到后端，由后端转发到 QQ。
   * @param {string} requestId 待回传请求 id
   * @param {string} text 结果文本
   */
  M._postBridgeResult = function (requestId, text) {
    if (!requestId) return;
    D.apiFetch(this, '/api/bridge/result', {
      method: 'POST',
      body: { request_id: requestId, text: text }
    }).catch(function () { /* 忽略 */ });
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
