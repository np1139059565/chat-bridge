// 模块：extend/dialog/parts/01j_card_consume.js
// 用途：卡片消费——把后端经卡片总线下发的各类卡片在抽屉侧处理掉。
//       含抽屉命令卡片（执行本地动作）、QQ 图片卡片（贴图进网页 AI）。
//       从 01e_bridge_actions.js 抽出：该文件已顶满行数上限，
//       而本组函数带有「指令绝不流向 AI」的隔离铁律，独立成文件更利于保护。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 消费一张抽屉命令卡片。
   *
   * 后端通过卡片总线（type=drawer-command）下发远程指令，
   * 内容形如 {action, params}。这类卡片不下发网页 AI，直接在抽屉里执行，
   * 执行完回执后端、不入 externalCards 列表。
   *
   * 【隔离铁律】指令卡片（drawer-command）只能在此消费、只能执行本地动作，
   * 其结果经 /api/bridge/result 回执给 QQ / 网页，【绝不】流向 AI。
   * 本函数返回 true 即代表「这张卡片已按指令处理完毕」；调用方见到 true
   * 必须直接跳过，不得再把它当消息下发给网页 AI。详见
   * docs/command-tool-isolation.md。
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
   * 后端把收到的图片转成 dataURL 放进卡片（type=qq-image）。
   * 本函数把卡片转为「外部卡片」入列，与普通外部卡片一致：
   * 受「自动」开关控制、可手动发送/跳过；发送时由 sendQqImageCard 贴图。
   * 旧行为是入列前直接贴图（绕过了自动开关），已改为入列受控。
   * @param {Object} c 后端下发的卡片
   * @returns {boolean} 是否为图片卡片（是则调用方跳过后续处理）
   */
  M.consumeQqImage = function (c) {
    if (!c || c.type !== 'qq-image') return false;
    // 多图：优先取数组 data_urls；兼容旧单张 data_url。
    let urls = (c.payload && c.payload.data_urls) || [];
    if (!Array.isArray(urls) || !urls.length) {
      const one = (c.payload && c.payload.data_url) || '';
      urls = one ? [one] : [];
    }
    // 同消息文字（图文消息）；纯图片时后端已补「用户截图」。
    const text = (c.payload && c.payload.text) || '';
    if (!urls.length) {
      this.toast('图片数据缺失，无法贴图');
      this.confirmCardDelivered(c.id);
      return true;
    }
    // 去重：后端确认前卡片可被反复取走，已在列表里的不再重复入列。
    if ((this.externalCards || []).some((x) => x.id === c.id)) {
      this.confirmCardDelivered(c.id);
      return true;
    }
    // 关键：图片卡片不再无条件直接贴图，而是入外部卡片列表，
    // 与普通外部卡片一致——受「自动」开关控制、可手动发送/跳过。
    // 入列表前先确保会话对象存在（同 pollExternalCards 的说明）。
    const conv = this.ensureConv(this.activeConv);
    const bk = conv.branchKeys || [];
    const anchorKey = bk.length ? bk[bk.length - 1] : '';
    const card = {
      id: c.id,
      type: c.type || 'qq-image',
      title: c.title || '图片',
      content: text || '（图片）',
      payload: c.payload || {},
      source: c.source || 'external',
      status: 'pending',
      phase: '',
      countdown: 0,
      result: null,
      error: null,
      executed: false,
      skipped: false,
      // 图片卡片专属：贴图所需数据与分支标记
      isQqImage: true,
      dataUrls: urls,
      imgText: text,
      // 图片在服务端的文件名（与收件箱同源）：贴图后据此把图片挂到
      // 对应消息上，抽屉渲染时按名取图，不依赖网页 DOM。
      imageNames: (c.payload && c.payload.image_names) || [],
      anchorKey: anchorKey,
      key: (anchorKey ? anchorKey.slice(anchorKey.indexOf('-') + 1) : '0')
        + '-' + ('x' + D.hashStr(c.id)),
      nonce: ''
    };
    this.externalCards.push(card);
    // 回执后端：卡片已入列，不再重复投递
    this.confirmCardDelivered(c.id);
    D.log('图片卡片已入列', card.id, '张数=' + urls.length);
    // 受「自动」开关控制：开则倒计时后自动贴图；关则停在列表等手动发送。
    if (this.autoSendEnabled) this.scheduleExternalSend(card);
    if (this._persist) this._persist();
    return true;
  };

  /**
   * 发送一张图片卡片：把图片（与文字）贴进网页 AI 输入框。
   *
   * 由 sendExternalCard 调用（图片卡片的「发送」语义是贴图，而非发信封）。
   * 从 01_backend.js 抽出，避免该文件超行数上限。
   * @param {Object} card 外部卡片对象（含 isQqImage 标记）
   * @returns {boolean} 是否为本函数处理的图片卡片
   */
  M.sendQqImageCard = function (card) {
    if (!card || !card.isQqImage) return false;
    const urls = card.dataUrls || [];
    // 方案 2：记录「这条图文消息的文字 → 服务端图片名」关联。
    // 图片随文字贴进网页 AI 后，网页回显的消息文字与 imgText 一致；
    // 待该消息入树时（05_messages._attachPendingImages）按文字匹配把图挂上去。
    try {
      if (card.imageNames && card.imageNames.length) {
        const conv = this.ensureConv(this.activeConv);
        if (!Array.isArray(conv.pendingImages)) conv.pendingImages = [];
        conv.pendingImages.push({ text: (card.imgText || '').trim(), names: card.imageNames.slice() });
        if (this._persist) this._persist();
      }
    } catch (e) { /* 记录失败不影响贴图 */ }
    D.enqueueSend({
      type: 'auto_send_image',
      dataUrls: urls,
      dataUrl: urls[0] || '',
      text: card.imgText || ''
    });
    card.status = 'done';
    card.executed = true;
    card.result = { delivered: true, note: '已把图片贴入网页 AI 输入框' };
    this.toast(card.imgText ? '已把图片与文字贴入网页 AI 输入框' : '已把图片贴入网页 AI 输入框');
    if (this._persist) this._persist();
    return true;
  };

})();
