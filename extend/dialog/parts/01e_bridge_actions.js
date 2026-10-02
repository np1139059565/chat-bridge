// 模块：extend/dialog/parts/01e_bridge_actions.js
// 用途：抽屉命令的执行（后端经卡片总线下发的远程指令）与桥接消息处理。
//       从 01b_bridge.js 抽出，使该文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

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
    // 页面操作类指令：动作执行后自动截一张图回传给 QQ，便于在手机上核对界面结果。
    // 延迟一小会儿再截，等界面（设置面板 / 侧栏切换等）完成重绘。
    if (payload.auto_screenshot && payload.request_id) {
      this._autoScreenshot(payload.request_id);
    }
    // 回执后端：命令已消费，此后不再重复投递
    this.confirmCardDelivered(c.id);
    return true;
  };

  /**
   * 消费一张 QQ 图片卡片：把图片贴进网页 AI 输入框（截图逆向流程）。
   *
   * 后端把 QQ 收到的图片转成 dataURL 放进卡片（type=qq-image）。
   * 本函数取出 dataURL，交给内容脚本复用已有的 pasteImageToWebpageAI 贴图，
   * 不下发网页 AI、不入 externalCards 列表。
   * @param {Object} c 后端下发的卡片
   * @returns {boolean} 是否为图片卡片（是则调用方跳过后续处理）
   */
  M.consumeQqImage = function (c) {
    if (!c || c.type !== 'qq-image') return false;
    const dataUrl = (c.payload && c.payload.data_url) || '';
    // 同消息文字（图文消息）；纯图片时后端已补「用户截图」。
    const text = (c.payload && c.payload.text) || '';
    if (dataUrl) {
      // 交给内容脚本：先贴图，再把文字写进同一输入框，最后只发一次。
      // 经统一发送队列，避免与工具卡片结果、质量告警同时到达互相顶掉。
      D.enqueueSend({ type: 'auto_send_image', dataUrl: dataUrl, text: text });
      this.toast(text ? '已把 QQ 图文贴入网页 AI 输入框' : '已把 QQ 图片贴入网页 AI 输入框');
    } else {
      this.toast('QQ 图片数据缺失，无法贴图');
    }
    // 回执后端：卡片已消费，不再重复投递
    this.confirmCardDelivered(c.id);
    return true;
  };

  /**
   * 执行动作后自动截屏并回传 QQ。
   * 延迟到界面重绘完成再截，避免截到切换过程中的中间态。
   * @param {string} requestId 待回传请求 id
   */
  M._autoScreenshot = function (requestId) {
    setTimeout(() => {
      window.parent.postMessage({
        type: 'bridge_screenshot',
        request_id: requestId || ''
      }, '*');
    }, 600);
  };

  /**
   * 执行一条抽屉命令。
   * @param {string} action 动作名
   * @param {Object} params 动作参数
   * @param {string} requestId 待回传请求 id（需回传结果的指令才有）
   */
  M._runBridgeAction = function (action, params, requestId) {
    // 动作表：action → 处理函数。新增指令只需在表里补一行，不必改分发逻辑。
    const table = {
      clear_all_sessions: () => this._bridgeClearAllSessions(),
      clear_messages: () => this._bridgeClearMessages(),
      copy_system_prompt: () => this._bridgeSendSystemPrompt(),
      toggle_auto_send: () => this._bridgeToggleAuto(),
      set_auto_send: () => this._bridgeSetAuto(!!params.on),
      set_delay: () => this._bridgeSetDelay(params.seconds),
      click_element: () => this._bridgeClickElement(params, requestId),
      list_sessions: () => this._bridgeListSessions(requestId),
      switch_session: () => this._bridgeSwitchSession(params.index),
      screenshot: () => this._bridgeRequestScreenshot(requestId),
      copy_latest: () => this._bridgeCopyLatest(),
      rerun_latest: () => this._bridgeRerunLatest(),
      reparse: () => this.reparse(),
      switch_side: () => this.switchPanelSide(),
      open_settings: () => { this.settingsOpen = true; },
      close_settings: () => { this.settingsOpen = false; },
      reconnect_backend: () => this.initBackend(),
      copy_conversation_json: () => this._bridgeCopyJson(requestId),
      skip_latest: () => this._bridgeSkipLatest(),
      refresh_page: () => this._bridgeRefreshPage(),
      collect_md: () => this._bridgeCollectMd(params.selector || ''),
    };
    const fn = table[action];
    if (fn) fn();
  };

  /** 切换自动回传开关（远程指令无确认框，直接切换）。 */
  M._bridgeToggleAuto = function () {
    this.setAutoSendEnabled(!this.autoSendEnabled);
    this.toast('自动回传已' + (this.autoSendEnabled ? '开启' : '关闭'));
  };

  /** 显式设置自动回传开关（幂等）：/sa on 或 /sa off。 */
  M._bridgeSetAuto = function (on) {
    if (on !== this.autoSendEnabled) this.setAutoSendEnabled(on);
    this.toast('自动回传已' + (on ? '开启' : '关闭'));
  };

  /** 设置自动回传延迟（秒）。 */
  M._bridgeSetDelay = function (seconds) {
    const secs = Number(seconds) || 0;
    if (secs > 0) { this.autoSendDelay = secs * 1000; this.toast('自动回传延迟已设为 ' + secs + ' 秒'); }
  };

  /** 下发点击元素：交给内容脚本在页面上下文执行，带 request_id 供结果回传。 */
  M._bridgeClickElement = function (params, requestId) {
    window.parent.postMessage({
      type: 'bridge_click_element',
      selector: params.selector || '',
      request_id: requestId || ''
    }, '*');
    this.toast('已下发点击：' + (params.selector || ''));
  };

  /** 请求内容脚本截取可见区域，带 request_id 供结果回传。 */
  M._bridgeRequestScreenshot = function (requestId) {
    window.parent.postMessage({ type: 'bridge_screenshot', request_id: requestId || '' }, '*');
    this.toast('正在截取浏览器屏幕…');
  };

  /** 复制当前会话 JSON 并把文本回传 QQ（过长则截断）。 */
  M._bridgeCopyJson = function (requestId) {
    let json = JSON.stringify(this.buildLogJson(), null, 2);
    this.copy(json);
    this.toast('镜像区可见消息已复制为 JSON');
    // QQ 单条文本有长度上限，过长时截断并提示，避免整条发送失败
    if (json.length > 3000) json = json.slice(0, 3000) + '\n…（已截断，完整内容见剪贴板）';
    this._postBridgeResult(requestId, json);
  };

  /** 跳过最新一张卡片。 */
  M._bridgeSkipLatest = function () {
    const card = this._latestCard();
    if (!card) { this.toast('没有可跳过的卡片'); return; }
    this.skipCard(card);
  };

  /** 请求内容脚本刷新页面并自动打开抽屉。 */
  M._bridgeRefreshPage = function () {
    window.parent.postMessage({ type: 'bridge_refresh_page' }, '*');
    this.toast('正在刷新页面…');
  };

  /**
   * 手动采集 Markdown：点复制按钮，内容挂到最新 AI 消息上。
   * @param {string} selector 复制按钮选择器
   */
  M._bridgeCollectMd = function (selector) {
    if (!selector) { this.toast('该采集指令没有绑定选择器'); return; }
    const lastId = this._lastAssistantId();
    if (!lastId) { this.toast('没有可采集的 AI 回复'); return; }
    this.bridgeMdSelector = selector;   // 手动采集用指令里的选择器
    this.captureMarkdown(lastId);
  };

  /**
   * 取当前可见切片里最后一条 assistant 消息的 id（即最新回复）。
   * 供「自动上报前采集 Markdown」与「手动采集 Markdown」共用，避免两处各写一份循环。
   * @returns {string} 消息指纹；没有 assistant 消息返回空串
   */
  M._lastAssistantId = function () {
    const conv = this.curConv || {};
    const tree = conv.msgTree || {};
    const keys = conv.visibleKeys || [];
    for (let i = keys.length - 1; i >= 0; i--) {
      const node = tree[keys[i]];
      if (node && node.role === 'assistant') {
        return window.AIMirrorDomUtils.messageFingerprint(node);
      }
    }
    return '';
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
      // 选择器统一包装成「完整调用表达式」：输入框因此显示为
      // document.querySelectorAll(".a.b")，用户可在其后接 JS 微调。
      // 纯选择器由执行端兼容，故对旧数据无影响。
      const wrapped = d.selector
        ? 'document.querySelectorAll(' + JSON.stringify(d.selector) + ')'
        : '';
      // 处于「修改选择器」模式：直接覆盖对应指令的选择器并保存
      if (this.bridgeEditIdx !== null && this.bridgeEditIdx !== undefined) {
        const cmd = (this.bridgeCommands || [])[this.bridgeEditIdx];
        if (cmd) {
          cmd.selector = wrapped;
          cmd.page_url = d.page_url || '';
          this.saveBridge();
          this.toast('已更新选择器：' + wrapped);
        }
        this.bridgeEditIdx = null;
        return true;
      }
      // 新增模式：记下选择器表达式与所在页面，供新增指令使用
      this.bridgePicked = {
        selector: wrapped,
        page_url: d.page_url || '',
        tag: d.tag || '',
        confidence: d.confidence || ''
      };
      this.toast('已选中：' + (d.tag || '') + ' ' + wrapped);
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

})();
