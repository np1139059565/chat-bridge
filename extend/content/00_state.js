// 模块：extend/content/00_state.js
// 用途：内容脚本的共享命名空间与全局状态。
//  - 定义 window.AIMirrorContent（下称 A），供后续 content/*.js 分片挂载函数。
//  - 集中存放所有跨分片共享的可变状态（iframe、observer、会话 id 等）。
//  - 提供站点规则表 PROFILES 与基础工具（日志、profile 选择、面板外观常量）。
// 依赖：lib/dom-utils.js（debounce / hashStr / textOf）
//
// 背景：原 content.js 是一个整体 IIFE，所有函数通过闭包共享变量。
// 拆分为多文件后，改为把变量挂在 A.state 上，各分片通过 A.state.xxx 读写，
// 从而在不改变行为的前提下解除对单一闭包的依赖。
window.AIMirrorContent = (function () {
  'use strict';
  const A = {};

  // 跨分片共享的可变状态：与原闭包中的 let 变量一一对应
  A.state = {
    iframe: null,            // 注入的悬浮对话框 iframe 元素
    containerEl: null,       // 当前绑定的对话容器节点
    observer: null,          // 对话容器的 MutationObserver
    historyObserver: null,   // 左侧会话列表的 MutationObserver
    historyEl: null,         // 当前绑定的左侧会话列表节点
    lastText: '',            // 上一次容器文本，用于判断内容是否变化
    lastPageKey: '',         // 上一次推送的结构化快照键，避免重复推送
    containerRetry: 0,       // 对话容器查找重试次数
    currentConvId: '',       // 当前会话 id（切换左侧会话时变化）
    currentSel: '',          // 当前生效的对话容器选择器
    dialogHidden: true,      // 对话框是否隐藏；页面加载默认隐藏
    siteKey: '',             // 当前网站标识
    profileId: '',           // 当前生效的站点规则（glm / deepseek）
    panelSide: 'right'       // 抽屉挂靠侧：right / left
  };

  // 调试日志：统一前缀，便于在网页控制台用 [AI-Mirror] 过滤
  A.DEBUG = true;

  /** 打印调试日志（DEBUG 关闭时不输出）。 */
  A.log = function () {
    if (!A.DEBUG) return;
    console.log.apply(console, ['[AI-Mirror][content]'].concat(Array.prototype.slice.call(arguments)));
  };

  /** 打印告警日志（DEBUG 关闭时不输出）。 */
  A.warn = function () {
    if (!A.DEBUG) return;
    console.warn.apply(console, ['[AI-Mirror][content]'].concat(Array.prototype.slice.call(arguments)));
  };

  // 公共工具：由 lib/dom-utils.js 提供，这里做本地别名，调用点写法保持不变
  A.debounce = window.AIMirrorDomUtils.debounce;
  A.hashStr = window.AIMirrorDomUtils.hashStr;
  A.textOf = window.AIMirrorDomUtils.textOf;

  // 站点规则表：不同模型的网页结构完全不同，无法用一套选择器通用。
  // 只使用各站点稳定的类名，绝不用 db183363 / _63c77b1 这类 CSS-Module 哈希（随时会变）。
  A.PROFILES = {
    glm: {
      label: '智谱清言 GLM',
      hosts: ['chatglm.cn', 'chatglm.com'],
      container: '.detail.chatScrollContainer.conversation-list',
      item: '.conversation-item',
      // GLM：一个 item 内同时含「提问」与「回答」两个子块
      split: true,
      userItem: '.conversation.question, .question, [id^="row-question"]',
      assistantItem: '.answer, [id^="row-answer"]',
      userName: '.user-name',
      userContent: '.question-txt',
      assistantName: '.assistant-name',
      thinking: '.advance-thinking',
      thinkingArea: '.advance-thinking-area',
      answerContent: '.answer-content',
      answerWrap: '.answer-content-wrap',
      // —— 左侧会话列表（切换会话要靠它）——
      convIdUrl: '[?&]cid=([^&]+)',                 // 从 URL 提取会话 id
      historyContainer: 'aside.aside-container, .aside-container',
      historyItem: '.history-item',
      historySelectedMark: '.selected',             // 选中项额外带的类
      inputSelector: '#search-input-box textarea, textarea.scroll-display-none'  // 网页 AI 输入框
    },
    deepseek: {
      label: 'DeepSeek',
      hosts: ['deepseek.com'],
      container: '.ds-virtual-list-visible-items',
      item: '.ds-message',
      // DeepSeek：一条 .ds-message 就是一个消息，用标记区分角色
      split: false,
      assistantMark: '.ds-assistant-message-main-content',
      userContent: '.ds-collapsible-text',
      // 注意：思考区内部也有 .ds-markdown，且在正文之前，
      // 必须用完整类名精确定位正文，否则会把思考内容当正文。
      assistantContent: '.ds-markdown.ds-assistant-message-main-content',
      thinking: '.ds-think-content',
      // —— 左侧会话列表 ——
      // DeepSeek 的会话项是 <a>，href 形如 /a/chat/s/<uuid>，是语义化链接，
      // 因此可以完全不依赖 CSS-Module 哈希类（_546d736 / b64fb9ae 都会变）：
      //   会话 id  = URL 路径里的 uuid
      //   选中判定 = href 与当前 location.pathname 一致
      convIdUrl: '\\/a\\/chat\\/s\\/([^/?#]+)',
      historyContainer: '.ds-scroll-area',
      historyItem: 'a[href*="/a/chat/s/"]',
      historySelectedMark: '',                      // 靠 href 与当前路径匹配判定选中
      inputSelector: 'textarea._27c9245, textarea[name="search"]'  // 网页 AI 输入框
    }
  };

  /** 按 hostname 猜测站点规则（用户未手动指定时）。 */
  A.guessProfile = function (host) {
    const h = String(host || '').toLowerCase();
    const ids = Object.keys(A.PROFILES);
    for (let i = 0; i < ids.length; i++) {
      const p = A.PROFILES[ids[i]];
      for (let j = 0; j < p.hosts.length; j++) {
        if (h === p.hosts[j] || h.endsWith('.' + p.hosts[j])) return ids[i];
      }
    }
    return 'glm';
  };

  /** 读取当前页面 hostname；异常时返回空串。 */
  A.currentHost = function () {
    try { return location.hostname || ''; } catch (e) { return ''; }
  };

  /** 取当前生效的站点规则；未识别时回退 GLM。 */
  A.activeProfile = function () {
    return A.PROFILES[A.state.profileId] || A.PROFILES.glm;
  };

  // 面板外观常量：悬浮面板是注入到宿主网页里的 iframe，运行在页面上下文，读不到
  // dialog/styles/00_tokens.css 的 CSS 变量，所以外框外观只能用常量写在这里。
  // 每个常量注明它在 00_tokens.css 中的对应令牌，改外观时两边必须同步。
  A.PANEL_W = '420px';                             // 常态宽度。styles/05_narrow.css 窄屏断点取 419px 正是据此推定
  A.PANEL_NARROW = 480;                            // 宿主窗口窄于此值时，面板改为铺满宽度
  A.PANEL_BG = '#f5f6f8';                          // 对应 styles/00_tokens.css 的 --cb-bg-page
  A.PANEL_RADIUS_RIGHT = '12px 0 0 12px';          // 右侧挂靠：只圆左侧悬浮边
  A.PANEL_RADIUS_LEFT = '0 12px 12px 0';           // 左侧挂靠：只圆右侧悬浮边
  A.PANEL_SHADOW_RIGHT = '-4px 0 16px rgba(0,0,0,.25)';  // 右侧挂靠：向左投影
  A.PANEL_SHADOW_LEFT = '4px 0 16px rgba(0,0,0,.25)';    // 左侧挂靠：向右投影
  A.PANEL_Z = 2147483647;                          // 取层级上限，确保不被宿主网页元素遮挡

  // 普通聊天页需要渲染时间，会正常重试；非聊天页永远找不到，
  // 因此限制总次数，且重试过程只打 info 级日志。
  A.MAX_CONTAINER_RETRY = 80; // 约 2 分钟

  return A;
})();
