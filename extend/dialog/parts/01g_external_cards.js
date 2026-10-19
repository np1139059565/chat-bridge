// 模块：extend/dialog/parts/01g_external_cards.js
// 用途：外部卡片轮询与投递——从后端取待投递卡片，按类型分流消费，
//       入列后回执确认，并按全局自动开关决定是否进入倒计时发送。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

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

  /**
   * 缓存卡片携带的 QQ 用户标识（openid）。
   *
   * 后端投递卡片时把 openid 写进 payload；上报消息切片时带上它，
   * 后端即可直接定位推送目标。只存内存：它属于当前这次 QQ 会话，
   * 重启后由下一条 QQ 卡片重新带回。
   * @param {object} vm    对话框实例（提供 _bridgeQQOpenid）
   * @param {Array}  cards 后端返回的卡片数组
   */
  function cacheQQOpenidFromCards(vm, cards) {
    cards.forEach((c) => {
      const oid = c && c.payload && c.payload.openid;
      if (oid && oid !== vm._bridgeQQOpenid) {
        vm._bridgeQQOpenid = oid;
        log('已缓存 QQ 用户标识：' + String(oid).slice(0, 8));
      }
    });
  }

  /**
   * 由后端卡片构造前端卡片对象。
   *
   * anchorKey 记下创建时「当前分支末端」那条消息的树 key，渲染时据此
   * 把卡片插到该消息之后；会话尚无消息时锚点为空，卡片排在最前。
   * key 与消息的 'pid-id' 同构（两段、连字符连接）：左段取锚点消息 id
   * （无锚点用 '0'，与消息树根一致），右段是卡片短 id（'x' + 哈希），
   * 替代 36 字符 UUID，避免巨长。
   * @param {object} c    后端卡片
   * @param {object} conv 目标会话对象（提供 branchKeys）
   * @returns {object} 前端卡片对象
   */
  function buildExternalCard(c, conv) {
    const bk = conv.branchKeys || [];
    const anchorKey = bk.length ? bk[bk.length - 1] : '';
    return {
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
      anchorKey: anchorKey,
      key: (anchorKey ? anchorKey.slice(anchorKey.indexOf('-') + 1) : '0')
        + '-' + ('x' + D.hashStr(c.id)),
      nonce: ''
    };
  }

  /**
   * 处理单张后端卡片：图片卡片与指令卡片就地消费，其余入列待发送。
   *
   * 图片卡片直接把图片贴进输入框（截图逆向流程）；抽屉命令卡片直接执行
   * 本地动作（桥接指令），两者都不下发给网页 AI。
   * 黑名单兜底只拦指令卡片（drawer-command）：卡片总线是开放接口、外部系统
   * 可投任意 type，用白名单会误伤。【隔离铁律】指令卡片一旦漏过消费分支，
   * 这里必须兜住并确认消费，绝不能让它落进 externalCards 被下发 AI。
   * 卡片入列后立即回执后端确认收货；若在回执前中断，后端判为未确认，
   * 下次轮询可再取走，不会出现「取走了却没展示、还再也拿不到」的情况。
   * @param {object} vm    对话框实例
   * @param {object} c     后端卡片
   * @param {object} conv  目标会话对象
   * @param {Array}  added 本轮新入列的卡片收集器
   * @returns {boolean} 是否作为新卡片入列
   */
  function consumeOneCard(vm, c, conv, added) {
    // QQ 图片卡片：不下发网页 AI，直接把图片贴进输入框（截图逆向流程）
    if (vm.consumeQqImage(c)) return false;
    // 抽屉命令卡片：不下发网页 AI，直接执行本地动作（桥接指令）
    if (vm.consumeBridgeCommand(c)) return false;
    if (c.type === 'drawer-command') {
      vm.confirmCardDelivered(c.id);
      log('拦截指令卡片（防泄露）：id=' + c.id);
      return false;
    }
    if (vm.externalCards.some((x) => x.id === c.id)) return false;
    const card = buildExternalCard(c, conv);
    vm.externalCards.push(card);
    added.push(card);
    vm.confirmCardDelivered(c.id);
    log('外部卡片已投递', card.id, card.title);
    return true;
  }

  /**
   * 轮询后端待投递卡片；新卡片入列，并按全局自动开关决定是否进入倒计时。
   * 面板不可见时不取卡片：关闭的面板不该再消费外部卡片，把它留给其他打开的页面。
   */
  M.pollExternalCards = async function () {
    if (!this.panelVisible) return;
    try {
      const data = await D.apiFetch(this, '/api/cards/pending', {
        headers: { 'Accept': 'application/json' }
      });
      const cards = (data && data.cards) || [];
      // 只在真取到卡片时打印：轮询每 5 秒一次，逐次打印会淹没控制台。
      if (cards.length) log('取到外部卡片 ' + cards.length + ' 张：', cards.map((c) => c.id).join(', '));
      cacheQQOpenidFromCards(this, cards);
      // 确保当前会话对象存在再写入：curConv 在会话未建立时会回退到共享的
      // EMPTY_CONV，直接 push 会把卡片写进这个全局空壳，随后创建真实会话对象时
      // 读不到，表现为「卡片莫名消失」。
      const conv = this.ensureConv(this.activeConv);
      const added = [];
      cards.forEach((c) => consumeOneCard(this, c, conv, added));
      // 仅当全局自动开关开启时自动发送，且本轮只发最新一张：
      // 积压多张时不全部触发，其余等待用户手动发送。
      // 从响应式列表末位回读（Vue 代理），改它才会驱动界面刷新。
      if (this.autoSendEnabled && added.length) {
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
    // 外部用户消息到达（QQ 文本卡 / 指令卡等）：先中止当前进行中的工具卡片，
    // 避免其回传结果与这条用户新消息交错，导致「结果与问题对不上」。
    this.abortActiveCards('外部卡片到达');
    // 图片卡片：发送动作 = 贴图而非发信封；具体实现在 01e_bridge_actions.js。
    // 返回 true 表示已处理，需提前结束本函数，不再走下面的信封路径。
    if (this.sendQqImageCard(card)) return;
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
})();
