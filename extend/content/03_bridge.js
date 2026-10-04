// 模块：extend/content/03_bridge.js
// 用途：会话身份识别、结构化对话推送、以及把文本回传到网页 AI 输入框。
// 依赖：content/00_state.js、content/02_blocks.js（extractBlocks）
(function () {
  'use strict';
  const A = window.AIMirrorContent;

  /**
   * 判断链接是否与当前路径对应。
   * 用 URL 解析把相对 / 绝对 href 统一成 pathname 再比（DeepSeek 的会话项是 <a> 链接）。
   * @param {string} href 链接地址
   * @param {string} path 当前 location.pathname
   * @returns {boolean} 是否匹配
   */
  A.hrefMatchesPath = function (href, path) {
    if (!href || !path) return false;
    if (href === path) return true;
    try {
      return new URL(href, location.href).pathname === path;
    } catch (e) {
      return href.indexOf(path) !== -1;
    }
  };

  /**
   * 找出左侧会话列表中当前被选中的那一项。
   * 不同站点的「会话 id 来源」与「选中项判定」完全不同，全部由 activeProfile() 驱动：
   *   - GLM    ：URL 带 ?cid=...；选中项是带 .selected 类的 .history-item
   *   - DeepSeek：URL 路径为 /a/chat/s/<uuid>；选中项 = href 与当前 location.pathname 一致的 <a>
   * @returns {Element|null} 选中项元素
   */
  A.selectedHistoryItem = function () {
    const P = A.activeProfile();
    if (!P.historyItem) return null;
    const items = document.querySelectorAll(P.historyItem);
    if (!items.length) return null;
    const path = location.pathname;
    // 优先：href 与当前路径一致（DeepSeek 这类用 <a> 承载会话的站点，完全不依赖易变的哈希类）
    for (let i = 0; i < items.length; i++) {
      const href = items[i].getAttribute && items[i].getAttribute('href');
      if (A.hrefMatchesPath(href, path)) return items[i];
    }
    // 其次：带选中标记类（GLM 的 .selected）
    if (P.historySelectedMark) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].matches && items[i].matches(P.historySelectedMark)) return items[i];
      }
    }
    return null;
  };

  /**
   * 取当前会话 id。
   * @returns {string} 会话 id；无法判断返回空串
   */
  A.getConversationId = function () {
    const P = A.activeProfile();
    // 会话 id 只从 URL 提取（各站正则不同，写在 profile 里）。
    // 不使用「左侧选中项标题指纹」作为退路：标题文本会随未读标记、时间等变化，
    // 同一会话刷新后会算出不同指纹，存档键随之漂移，导致历史与卡片执行状态
    // 读不回来。取不到 id 时返回空串，由上层落到 __default__，
    // 待 URL 给出真实 id 后再把 __default__ 的记录迁移过去。
    if (P.convIdUrl) {
      const m = new RegExp(P.convIdUrl).exec(location.href);
      if (m && m[1]) return 'cid:' + m[1];
    }
    return '';
  };

  /**
   * 取当前会话标题（截断到 80 字）。
   * @returns {string} 标题；无选中项返回空串
   */
  A.getConversationTitle = function () {
    const sel = A.selectedHistoryItem();
    return sel ? A.textOf(sel).slice(0, 80) : '';
  };

  /**
   * 结构化提取当前对话并推送给对话框。
   * 每次推送都重新算会话 id，避免切会话后内容仍被归到上一个会话名下。
   * @param {boolean} force 是否强制推送（忽略内容未变化判断）
   * @param {string} [reason] 触发来源：'generate'（AI 新增对话）/
   *   'scroll'（可视区滚动）/ 'switch'（切换会话）/ 'manual'（手动解析）。
   *   仅作标签透传给消费端，不改变推送内容本身。
   */
  A.sendPage = function (force, reason) {
    // 面板未打开：不解析也不推送。打开时会由 activate() 主动补一次全量解析。
    if (!A.state.active) return;
    if (!A.state.containerEl) return;
    const convId = A.getConversationId();
    const convChanged = !!convId && convId !== A.state.currentConvId;
    if (convChanged) A.state.currentConvId = convId;

    const messages = A.extractBlocks(A.state.containerEl);
    const key = convId + '|' + JSON.stringify(messages);
    // 内容未变化且非强制推送时直接返回：滚动期间会反复触发，去重可省下大量解析与消息投递
    if (!force && !convChanged && key === A.state.lastPageKey) return;
    A.state.lastPageKey = key;
    // 逐条算消息指纹并打印：与 dialog 侧的 msgId 同源，便于对齐两边日志、
    // 区分「同一会话的多次推送」（仅凭消息条数无法分辨）。
    const fpList = messages.map(function (m) {
      return window.AIMirrorDomUtils.messageFingerprint(m);
    });
    // 视口是否停在最新处：仅滚动轮次的自动执行复检需要，其余来源仅作日志
    const atBottom = A.isAtBottom();
    A.log('sendPage: 推送结构化对话 force=' + !!force, '会话=' + convId,
      '消息数=' + messages.length, 'ids=' + JSON.stringify(fpList),
      'atBottom=' + atBottom);
    A.post({
      type: 'page_blocks',
      messages: messages,
      page_url: location.href,
      siteKey: A.state.siteKey,                       // 按站点隔离数据与设置
      profileId: A.state.profileId,
      conversationId: convId,
      conversationTitle: A.getConversationTitle(),
      reason: reason || 'manual',  // 触发来源标签，供消费端分流
      atBottom: atBottom           // 视口是否在底部（滚动轮次自动执行复检用）
    });
  };

  /**
   * 找到网页 AI 的输入框（选择器按站点规则取）。
   * @returns {Element|null} 输入框元素
   */
  A.findInputBox = function () {
    const sel = A.activeProfile().inputSelector;
    if (!sel) return null;
    return document.querySelector(sel);
  };

  /**
   * 自动回传：把文本写回网页 AI 的输入框并触发发送。
   * 输入框选择器按站点规则取（glm / deepseek 的 DOM 结构不同），
   * 设值走原生 setter（兼容 Vue/React 的响应式），再派发 input 事件，
   * 等状态同步后派发 Enter 键事件触发发送。
   * @param {string} text 要回传的文本
   */
  /**
   * 把文本一次性写入输入框（复制粘贴式写值，非逐字输入）。
   * 用原生 setter 写整个值，触发框架的响应式更新，再派发 input 事件。
   * 抽成公共函数，供「纯文本」与「图文合一」两条路径复用。
   * @param {Element} ta 输入框
   * @param {string} text 文本
   */
  A.writeInputValue = function (ta, text) {
    if (!ta) return;
    const value = String(text || '');
    ta.focus();
    // 用原生 setter 写值，触发框架的响应式更新
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')
      .set.call(ta, value);
    ta.dispatchEvent(new Event('input', { bubbles: true }));
  };

  /**
   * 自动回传：把文本写回网页 AI 的输入框并触发发送。
   * 输入框选择器按站点规则取（glm / deepseek 的 DOM 结构不同），
   * 设值走原生 setter（兼容 Vue/React 的响应式），再派发 input 事件，
   * 等状态同步后派发 Enter 键事件触发发送。
   * @param {string} text 要回传的文本
   * @param {boolean} [autoSend] 是否写完后自动回车发送；false 表示只写值
   *   （图文合一流程自行控制发送时机，避免图文各发一条）
   */
  A.pasteToWebpageAI = function (text, autoSend) {
    const ta = A.findInputBox();
    if (!ta) {
      A.warn('pasteToWebpageAI: 未找到网页 AI 输入框');
      A.post({ type: 'auto_send_result', ok: false, msg: '未找到网页 AI 输入框' });
      return;
    }
    A.writeInputValue(ta, text);
    // 只写值不发送：交给调用方（图文合一）统一回车
    if (autoSend === false) return;
    // 两步走：先等发送按钮就绪，再延迟 500ms，然后回车发送。
    // 就绪信号取发送按钮的 disabled 状态：未就绪时按钮带 ds-button--disabled，
    // 就绪后该类消失。这是框架自己给出的可靠信号，比读输入框值靠谱
    // （值是用原生 setter 直接写进去的，写入即相等，证明不了框架状态已更新）。
    A.waitSendReady(function () {
      setTimeout(function () { A.pressEnter(ta); }, 500);
    });
  };

  /**
   * 轮询等待发送按钮就绪：按钮不再带 disabled 类即回调，超时（3 秒）也回调。
   *
   * 就绪信号取站点规则里的 sendButton 元素：未就绪时它带 ds-button--disabled，
   * 就绪后该类消失。这是框架自己给出的可靠信号，比读输入框值靠谱——值是用
   * 原生 setter 直接写进去的，写入即相等，证明不了框架内部状态已更新。
   * @param {Function} done 就绪（或超时）后的回调
   */
  A.waitSendReady = function (done) {
    const profile = A.activeProfile();
    const sel = profile.sendButton;
    // 站点没配发送按钮选择器：无从判断，直接放行，由后续延时兜底。
    if (!sel) { done(); return; }
    const deadline = Date.now() + 3000;
    (function check() {
      let btn = null;
      try { btn = document.querySelector(sel); } catch (e) { btn = null; }
      // 按钮不存在，或仍带 disabled 类：都视为未就绪，继续等
      const disabled = !btn || (btn.className && String(btn.className).indexOf('ds-button--disabled') >= 0);
      if (!disabled || Date.now() > deadline) { done(); return; }
      setTimeout(check, 100);
    })();
  };

  /**
   * 派发 Enter 键，触发网页 AI 发送。
   * @param {Element} ta 输入框
   */
  A.pressEnter = function (ta) {
    const key = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true };
    ta.dispatchEvent(new KeyboardEvent('keydown', key));
    ta.dispatchEvent(new KeyboardEvent('keyup', key));
  };

  /**
   * 把图片贴进网页 AI 输入框并发送。
   * 做法：把 dataURL 转成 File，构造带该文件的 DataTransfer，
   * 再在输入框上派发 paste 事件——多数支持图片上传的输入框会据此接收图片。
   * 图片写入依赖站点实现，失败时回传提示，由用户手动粘贴。
   * @param {string} dataUrl 图片 dataURL
   */
  /** 把单个 dataURL 转成 File 对象；非图片或解析失败返回 null。 */
  A._dataUrlToFile = function (dataUrl, idx) {
    try {
      const parts = String(dataUrl).split(',');
      const mime = (parts[0].match(/:(.*?);/) || [])[1] || 'image/png';
      const bin = atob(parts[1] || '');
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const ext = mime.indexOf('jpeg') >= 0 ? 'jpg' : 'png';
      return new File([arr], 'image_' + idx + '.' + ext, { type: mime });
    } catch (e) {
      return null;
    }
  };

  /**
   * 把一或多张图片贴进网页 AI 输入框并发送，可附一段文字。
   * 多张图放在同一个 paste 事件里一次性贴入（站点会按多图处理），
   * 随后写入文字、只回车一次，保证「图文合一、多图一条消息」。
   * @param {string|string[]} dataUrlOrList 单张 dataURL 或 dataURL 数组
   * @param {string} text 随图文字（可空）
   */
  A.pasteImageToWebpageAI = function (dataUrlOrList, text) {
    const ta = A.findInputBox();
    if (!ta) {
      A.warn('pasteImageToWebpageAI: 未找到网页 AI 输入框');
      A.post({ type: 'auto_send_result', ok: false, msg: '未找到网页 AI 输入框' });
      return;
    }
    // 统一成数组：兼容单张字符串与多张数组两种入参
    const list = Array.isArray(dataUrlOrList) ? dataUrlOrList : (dataUrlOrList ? [dataUrlOrList] : []);
    if (!list.length) {
      A.post({ type: 'auto_send_result', ok: false, msg: '没有可粘贴的图片' });
      return;
    }
    try {
      // 逐张依次粘贴，而不是一次贴多张。
      // 原因：部分站点（如 DeepSeek）的粘贴处理只取剪贴板里的第一个文件，
      // 一次塞多张最终只会成一张。改成逐张单独派发 paste 事件、留出间隔，
      // 让每张都各自被接收一次，从而累积成多张。
      const GAP = 800;      // 每张贴图之间的间隔（毫秒）
      const TAIL = 1500;    // 全部贴完后、写文字之前的等待（等预览/上传就绪）
      ta.focus();
      let idx = 0;
      let added = 0;
      const step = function () {
        if (idx >= list.length) {
          // 全部贴完：等预览就绪后写文字，再等发送按钮就绪、回车发送一次
          setTimeout(function () {
            if (text) A.writeInputValue(ta, text);
            A.waitSendReady(function () {
              setTimeout(function () { A.pressEnter(ta); }, 300);
            });
          }, TAIL);
          return;
        }
        const file = A._dataUrlToFile(list[idx], idx);
        idx++;
        if (!file) { step(); return; }
        const dt = new DataTransfer();
        dt.items.add(file);
        ta.focus();
        ta.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
        added++;
        setTimeout(step, GAP);
      };
      step();
      A.post({ type: 'auto_send_result', ok: true, msg: text ? '已尝试粘贴图文并发送' : '已尝试粘贴图片并发送' });
    } catch (e) {
      A.warn('pasteImageToWebpageAI 失败', e && e.message);
      A.post({ type: 'auto_send_result', ok: false, msg: '粘贴图片失败：' + (e && e.message) });
    }
  };
})();
