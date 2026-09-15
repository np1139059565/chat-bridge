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
    // 1) 优先从 URL 提取会话 id（各站正则不同，写在 profile 里）
    if (P.convIdUrl) {
      const m = new RegExp(P.convIdUrl).exec(location.href);
      if (m && m[1]) return 'cid:' + m[1];
    }
    // 2) 退回：用左侧被选中会话项的标题做指纹
    const sel = A.selectedHistoryItem();
    if (sel) return 'h:' + A.hashStr(A.textOf(sel));
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
   */
  A.sendPage = function (force) {
    if (!A.state.containerEl) { A.log('sendPage: 对话容器未就绪，跳过推送'); return; }
    const convId = A.getConversationId();
    const convChanged = !!convId && convId !== A.state.currentConvId;
    if (convChanged) A.state.currentConvId = convId;

    const messages = A.extractBlocks(A.state.containerEl);
    const key = convId + '|' + JSON.stringify(messages);
    if (!force && !convChanged && key === A.state.lastPageKey) {
      A.log('sendPage: 内容未变化，跳过重复推送');
      return;
    }
    A.state.lastPageKey = key;
    A.log('sendPage: 推送结构化对话 force=' + !!force, '会话=' + convId, '消息数=' + messages.length);
    A.post({
      type: 'page_blocks',
      messages: messages,
      url: location.href,
      siteKey: A.state.siteKey,                       // 按站点隔离数据与设置
      profileId: A.state.profileId,
      conversationId: convId,
      conversationTitle: A.getConversationTitle()
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
  A.pasteToWebpageAI = function (text) {
    const ta = A.findInputBox();
    if (!ta) {
      A.warn('pasteToWebpageAI: 未找到网页 AI 输入框');
      A.post({ type: 'auto_send_result', ok: false, msg: '未找到网页 AI 输入框' });
      return;
    }
    const value = String(text || '');
    ta.focus();
    // 用原生 setter 写值，触发框架的响应式更新
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')
      .set.call(ta, value);
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    // 等框架状态同步后派发回车，触发发送
    setTimeout(function () {
      const key = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true };
      ta.dispatchEvent(new KeyboardEvent('keydown', key));
      ta.dispatchEvent(new KeyboardEvent('keyup', key));
      A.post({ type: 'auto_send_result', ok: true, msg: '已回传结果到网页 AI' });
    }, 500);
  };
})();
