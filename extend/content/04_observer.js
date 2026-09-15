// 模块：extend/content/04_observer.js
// 用途：对话容器与左侧会话列表的监听、重新探测、以及扩展卸载时的清理。
// 依赖：content/00_state.js、content/01_panel.js、content/03_bridge.js
(function () {
  'use strict';
  const A = window.AIMirrorContent;

  /**
   * 绑定对话容器监听。找不到时按固定间隔重试，超过上限则放弃。
   * 非聊天页永远找不到容器，因此限制总次数，且重试过程只打 info 级日志，
   * 避免在非聊天页把 console 刷成告警。
   * @param {string} sel 对话容器选择器
   */
  A.startObserver = function (sel) {
    A.state.currentSel = sel;
    const container = document.querySelector(sel);
    if (!container) {
      A.state.containerRetry += 1;
      // 仅在开始时提示一次（info），不按次刷 warn，避免非聊天页告警刷屏
      if (A.state.containerRetry === 1) {
        A.log('startObserver: 未找到对话容器，开始重试…', sel);
      } else if (A.state.containerRetry === Math.floor(A.MAX_CONTAINER_RETRY / 2)) {
        A.log('startObserver: 约 1 分钟仍未找到对话容器，该页可能不是聊天页；'
          + '可在设置里调整“对话容器选择器”，或点击工具栏图标重新探测');
      }
      if (A.state.containerRetry >= A.MAX_CONTAINER_RETRY) {
        // 真正放弃时才用 warn 提示一次，并说明如何在该页启用
        A.warn('startObserver: 超时未找到对话容器，停止重试（' + sel + '）。'
          + '该页可能不是聊天页；如需启用，请在设置里配置正确的“对话容器选择器”，'
          + '或刷新 / 点击工具栏图标重新探测');
        return; // 不再排程，结束无限循环
      }
      setTimeout(function () { A.startObserver(sel); }, 1500); // 容器尚未渲染，稍后重试
      return;
    }
    // 找到容器：重置重试计数并记录初始文本
    A.state.containerRetry = 0;
    A.state.containerEl = container;
    A.state.lastText = container.innerText || '';
    A.log('startObserver: 找到对话容器', sel, '文本长度=' + A.state.lastText.length);
    A.sendPage();

    // 容器内容变化时（防抖）重新结构化提取并推送
    const onMutate = A.debounce(function () {
      const txt = container.innerText || '';
      if (txt !== A.state.lastText) {
        A.state.lastText = txt;
        A.log('onMutate: 对话文本已更新，长度=' + txt.length);
      }
      A.sendPage(); // 重新结构化提取（含新增代码块）
    }, 600);

    A.state.observer = new MutationObserver(onMutate);
    A.state.observer.observe(container, {
      childList: true,
      subtree: true,
      characterData: true
    });
    A.watchHistory(); // 同时绑定左侧会话列表监听（随预设切换）
  };

  /**
   * 手动重新探测对话容器：点击工具栏图标时调用，
   * 便于聊天页已加载但直接注入时未命中的情况。
   */
  A.reprobe = function () {
    A.state.containerRetry = 0;
    A.getConfig(function (cfg) { A.startObserver(cfg.container); });
  };

  /**
   * 左侧会话列表（侧边栏）监听：把会话切换事件即时反映到记录切换。
   * 各站的侧边栏容器由 activeProfile().historyContainer 决定，
   * 因此「对话容器选择器」切换预设时，这个监听会自动绑定到对应站点的侧边栏。
   */
  A.watchHistory = function () {
    const P = A.activeProfile();
    if (!P.historyContainer) return;
    const el = document.querySelector(P.historyContainer);
    if (!el || el === A.state.historyEl) return; // 未渲染 / 已绑定同一节点，跳过
    if (A.state.historyObserver) { A.state.historyObserver.disconnect(); A.state.historyObserver = null; }
    A.state.historyEl = el;
    // 侧边栏变化时（防抖）检查会话 id 是否切换，切换则强制推送
    A.state.historyObserver = new MutationObserver(A.debounce(function () {
      const id = A.getConversationId();
      if (id && id !== A.state.currentConvId) {
        A.state.currentConvId = id;
        A.log('history: 检测到会话切换 →', id, '标题=' + A.getConversationTitle());
        A.sendPage(true);
      }
    }, 300));
    A.state.historyObserver.observe(el, {
      childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'href']
    });
    A.log('watchHistory: 已监听左侧会话列表（' + P.historyContainer + '）');
  };

  /**
   * 左侧会话切换监听。
   * 关键：切换会话时 chatglm 可能整块替换对话容器节点，原先挂在旧节点上的
   * MutationObserver 会彻底失效（内容再变也不触发），因此必须检测节点更换并重绑。
   */
  A.watchConversation = function () {
    // 1) 侧边栏会话列表监听（随预设切换绑定到对应站点容器）
    A.watchHistory();
    // 2) 对话容器节点是否整块被替换（切会话时 chatglm 会替换节点，旧 observer 失效）
    if (A.state.currentSel) {
      const cur = document.querySelector(A.state.currentSel);
      // 容器被「替换」或「移除」都必须重绑：挂在已脱离文档的节点上的 observer 会彻底失效，
      // 表现为插件记录永久停在某一时刻、之后再也不更新。
      // 注意 cur 为 null（容器被移除）时同样要处理。
      if (cur !== A.state.containerEl) {
        A.log('watch: 对话容器已变更（' + (cur ? '节点被替换' : '节点被移除') + '），重新绑定 observer');
        if (A.state.observer) { A.state.observer.disconnect(); A.state.observer = null; }
        A.state.containerEl = null;
        A.startObserver(A.state.currentSel); // 内部会以新节点重新 sendPage
        return;
      }
    }
    // 会话切换但容器节点未换（仅内容替换）时，靠会话 id 变化补一次强制推送
    const id = A.getConversationId();
    if (id && id !== A.state.currentConvId) {
      A.state.currentConvId = id;
      A.log('watch: 检测到会话切换 →', id, '标题=' + A.getConversationTitle());
      A.sendPage(true);
    }
  };

  /**
   * 判断扩展是否仍然装载：真正被卸载后 chrome.runtime.id 会变为不可用。
   * @returns {boolean} 扩展是否仍存活
   */
  A.isExtensionAlive = function () {
    try {
      return !!(chrome && chrome.runtime && chrome.runtime.id);
    } catch (e) {
      return false;
    }
  };

  /**
   * MV3 清理机制：仅在扩展真正被卸载时移除残留 DOM 与监听器。
   * 注意：service worker 休眠终止同样会触发长连接 onDisconnect，
   * 若不区分就删 UI，会出现“插件凭空消失、点图标也拉不回来、且无任何报错”。
   * @param {string} reason 触发清理的原因（仅用于日志）
   */
  A.cleanup = function (reason) {
    if (A.isExtensionAlive()) {
      A.log('cleanup 跳过（原因=' + reason + '）：扩展仍在，仅 service worker 断连');
      return;
    }
    A.log('cleanup 执行（原因=' + reason + '）');
    if (A.state.iframe && A.state.iframe.parentNode) A.state.iframe.parentNode.removeChild(A.state.iframe);
    A.state.iframe = null;
    if (A.state.observer) { A.state.observer.disconnect(); A.state.observer = null; }
    if (A.state.historyObserver) { A.state.historyObserver.disconnect(); A.state.historyObserver = null; }
    A.state.historyEl = null;
    A.state.containerEl = null;
  };
})();
