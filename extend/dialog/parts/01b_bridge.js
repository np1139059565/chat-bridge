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
      this.bridgeConnected = !!st.connected;
    } catch (e) {
      // 桥接未启用 / 后端不可达：保持默认值，不打扰用户
      this.bridgeConnected = false;
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
      const data = await D.apiFetch(this, '/api/bridge/config', {
        method: 'POST',
        body: {
          enabled: this.bridgeEnabled,
          app_id: this.bridgeAppId,
          app_secret: this.bridgeAppSecret,
          push: this.bridgePush,
          commands: this.bridgeCommands
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

  /** 进入元素选择模式：请求内容脚本开始选元素。 */
  M.startPickElement = function () {
    this.bridgePicking = true;
    window.parent.postMessage({ type: 'picker_start' }, '*');
    this.toast('请在页面上点击要绑定的元素（Esc 取消）');
  };

  /** 停止元素选择模式。 */
  M.stopPickElement = function () {
    this.bridgePicking = false;
    window.parent.postMessage({ type: 'picker_stop' }, '*');
  };

  /**
   * 新增一条 QQ 指令。
   * 必须已经通过「选择元素」拿到选择器，指令才有可执行的目标。
   */
  M.addBridgeCommand = function () {
    const name = (this.bridgeNewCmdName || '').trim();
    const label = (this.bridgeNewCmdLabel || '').trim();
    const picked = this.bridgePicked;
    if (!name || !label) { this.toast('命令名与显示名必填'); return; }
    if (!name.startsWith('/')) { this.toast('命令名需以 / 开头'); return; }
    if (!picked || !picked.selector) { this.toast('请先选择要点击的元素'); return; }
    // 命令名去重
    if ((this.bridgeCommands || []).some((c) => (c.name || '').toLowerCase() === name.toLowerCase())) {
      this.toast('该命令名已存在');
      return;
    }
    this.bridgeCommands.push({
      name: name,
      label: label,
      selector: picked.selector,
      page_url: picked.page_url || ''
    });
    // 复位录入状态
    this.bridgeNewCmdName = '';
    this.bridgeNewCmdLabel = '';
    this.bridgePicked = null;
    this.saveBridge();
    this.toast('已添加指令：' + name);
  };

  /** 删除一条 QQ 指令。 */
  M.removeBridgeCommand = function (idx) {
    this.bridgeCommands.splice(idx, 1);
    this.saveBridge();
  };

  /**
   * 修改某条已有指令的选择器：进入选元素模式，选中后覆盖该指令的选择器。
   * @param {number} idx 指令下标
   */
  M.editBridgeCommandSelector = function (idx) {
    this.bridgeEditIdx = idx;
    this.bridgePicking = true;
    window.parent.postMessage({ type: 'picker_start' }, '*');
    this.toast('请点击新的目标元素（Esc 取消）');
  };

  /**
   * 把当前可见切片上报给远程桥接层（QQ ↔ 网页 AI）。
   *
   * 注意：上报的是**全量可见切片**，不是「本轮新增」——
   * sendPage 每次都全量推送，桥接层自己与「已推送集合」比对取差集。
   * 抽屉在这里只是「小喇叭」：把看见的消息喊给桥接层，
   * 分类、去重、往 QQ 推全由桥接层完成。抽屉不用懂 QQ。
   *
   * 只推 generate 来源：那是「AI 刚说完新话」的时刻；
   * scroll / switch / manual 都是用户回看历史或切上下文，不该推。
   * @param {string} [reason] 触发来源
   */
  M.reportToBridge = function (reason) {
    // 只推 generate：其余来源是回看 / 切换，推了会刷屏
    if (reason !== 'generate') return;
    // 面板未打开时不推：关闭抽屉就代表用户此刻不需要远程工作
    if (!this.panelVisible) return;
    const conv = this.curConv || {};
    const tree = conv.msgTree || {};
    const messages = [];
    (conv.visibleKeys || []).forEach((k) => {
      const node = tree[k];
      if (!node || node.deleted) return;
      const id = window.AIMirrorDomUtils.messageFingerprint(node);
      messages.push({ id: id, role: node.role, blocks: node.blocks || [] });
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
  };

  /**
   * 列出会话列表并回传到 QQ。
   * 序号与 convList 的顺序一致，供 /ss 按序号切换时使用。
   * @param {string} requestId 待回传请求 id
   */
  M._bridgeListSessions = function (requestId) {
    const list = this.convList || [];
    if (!list.length) {
      this._postBridgeResult(requestId, '（暂无会话）');
      return;
    }
    const lines = list.map((c, i) => {
      const cur = c.id === this.activeConv ? ' [当前]' : '';
      const title = c.title || '（未命名）';
      const count = c.msgCount || 0;
      const date = c.updatedAt ? new Date(c.updatedAt).toLocaleDateString() : '';
      return (i + 1) + '.' + cur + ' ' + title
        + '\n   id: ' + c.id + '  ' + count + ' 条 ' + date;
    });
    this._postBridgeResult(requestId, '会话列表（用 /ss 序号 切换）：\n' + lines.join('\n'));
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
   * 把点击结果翻译成给人看的文案。
   * 找不到或不唯一都要明确提示，让用户在 QQ 里知道失败原因。
   * @param {Object} d 内容脚本回传的结果
   * @returns {string} 提示文本
   */
  M._clickResultText = function (d) {
    const sel = d.selector || '';
    if (d.ok) return '已点击：' + sel;
    if (d.reason === 'not_found') {
      return '点击失败：页面上找不到元素\n' + sel + '\n（页面结构可能已变，请重新选择元素）';
    }
    if (d.reason === 'not_unique') {
      return '点击失败：该选择器命中 ' + (d.count || 0) + ' 个元素，无法确定点哪个\n' + sel
        + '\n（请重新选择更精确的元素）';
    }
    if (d.reason === 'invalid_selector') {
      return '点击失败：选择器语法无效\n' + sel;
    }
    if (d.reason === 'empty_selector') {
      return '点击失败：该指令没有绑定选择器';
    }
    return '点击失败：' + sel;
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
