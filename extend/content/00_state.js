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
    lastPageKey: '',         // 上一次推送的结构化快照键，避免重复推送
    scanTimer: null,         // 静默扫描计时器：DOM 停止变动满静默期后才解析
    containerRetry: 0,       // 对话容器查找重试次数
    currentConvId: '',       // 当前会话 id（切换左侧会话时变化）
    currentSel: '',          // 当前生效的对话容器选择器
    buttonTimer: null,       // 发送按钮状态轮询定时器
    isGenerating: false,     // 网页 AI 是否正在生成：生成期间暂停静默扫描，避免抓取造成卡顿
    scrollHandler: null,     // 滚动监听处理器（捕获阶段）：虚拟列表滚动可能不增删节点，靠它感知
    dialogHidden: true,      // 对话框是否隐藏；页面加载默认隐藏
    active: false,           // 面板是否处于打开（激活）状态：未打开时不做解析、推送与轮询
    siteKey: '',             // 当前网站标识
    profileId: '',           // 当前生效的站点规则（glm / deepseek）
    panelSide: 'right',      // 抽屉挂靠侧：right / left
    theme: 'light'           // 宿主页面明暗主题：light / dark（由 detectHostTheme 判定）
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
  // 选择器表达式解析：兼容纯选择器与完整调用写法（点击 / 采集共用）
  A.resolveSelectorExpr = window.AIMirrorDomUtils.resolveSelectorExpr;

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
      inputSelector: '#search-input-box textarea, textarea.scroll-display-none',  // 网页 AI 输入框
      // GLM 无独立的「发送/停止」按钮，生成态信号写在对话区容器的类名上：
      // 生成中时 .enter.is-main-chat 会带上 m-three-row（多行输出）或 searching（联网搜索），
      // 空闲时这两个类都不出现。命中任一即视为「AI 正在说话」。
      generatingSelectors: ['.enter.is-main-chat.m-three-row', '.enter.is-main-chat.searching']
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
      inputSelector: 'textarea._27c9245, textarea[name="search"]',  // 网页 AI 输入框
      // 发送 / 停止按钮：生成中与空闲态共用同一元素，仅图标变化。
      // 其状态由内部图标 SVG 的 path 签名判定，不依赖易变的哈希类名。
      // 发送按钮：必须限定 --primary。
      // 仅用 .ds-button--circle 会同时命中「向上滚动后出现的定位到底部按钮」
      // （--outlinedNeutral --floating），它在 DOM 中可能排在发送按钮之前，
      // querySelector 只取第一个，于是轮询长期读错元素、永远判定不出生成态翻转，
      // 导致 generate 来源永不触发、最新卡片停在待执行。
      sendButton: 'div[role="button"].ds-button--primary.ds-button--circle',
      // 「滚动到底部」按钮：用户向上翻看历史时出现，点它回到最新；已在底部时隐藏。
      // 用途：滚动轮次里判断视口是否停在最新消息处，作为「回滚误触发」的排除条件。
      // 两个选择器均经页面验证有效，逐条匹配、任一命中即算「按钮存在」。
      // 语义约定：按钮存在 = 不在底部；按钮不存在 = 已在底部。
      scrollToBottomButton: [
        'div[role="button"].ds-button--circle.ds-button--outlinedNeutral.ds-button--floating',
        'div[role="button"].ds-button--floating'
      ],
      // 生成中（AI 说话）时按钮换成「停止」方块图标，其 path 以此片段开头；
      // 空闲时为发送箭头。用它直接判定生成中，避免依赖「首帧恰为空闲」这一假设。
      sendButtonStopMark: 'M2 4.88C2 3.68009'
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

  // 注意：本文件与 05_index.js 的主题判定 / 监听逻辑，与另一个独立扩展
  // （skills/debug_chrome/extension/content/02_drawer.js）存在同源实现。
  // 两者是各自独立的 Chrome 扩展，运行时无法共用文件，只能人工保持同步：
  // 调整亮度阈值、回退策略或监听的属性列表时，务必同步修改另一侧。

  /**
   * 解析颜色的感知亮度；无法判断时返回 null。
   * 网页常把 <html> 底色设为透明，此时返回 null，交给调用方回退到 <body>。
   * @param {string} color CSS 颜色字符串（rgb / rgba）
   * @returns {number|null} 0-255 的亮度值
   */
  function colorLuminance(color) {
    const m = /rgba?\(([^)]+)\)/.exec(color || '');
    if (!m) return null;
    const parts = m[1].split(',').map(function (s) { return parseFloat(s); });
    if (parts.length < 3) return null;
    // alpha 为 0 表示无底色，视为「读不到」，交由调用方回退
    if (parts.length === 4 && parts[3] === 0) return null;
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2];
  }

  /**
   * 读取宿主 <html> 的实际底色，判断明暗主题。
   * <html> 无有效底色时回退到 <body>；两者都读不到时默认亮色，避免误伤。
   * @returns {'dark'|'light'}
   */
  A.detectHostTheme = function () {
    // 1) 属性信号优先：暗色 class / data-theme / data-color-mode / color-scheme。
    //    不少站点只靠 class 或 data-theme 切主题，<html> / <body> 自身背景色透明
    //    或恒为浅色，若只看背景色会永远判成亮色。
    const root = document.documentElement;
    const body = document.body;
    const themeAttr = String(
      (root && (root.getAttribute('data-theme') || root.getAttribute('data-color-mode'))) ||
      (body && (body.getAttribute('data-theme') || body.getAttribute('data-color-mode'))) || ''
    );
    const cls = String((root && root.className) || '') + ' ' + String((body && body.className) || '');
    const cs = root ? String(getComputedStyle(root).colorScheme || '') : '';
    // class 用「分隔符边界」匹配：命中 dark / dark-mode / theme-dark / dark_theme，
    // 又不误伤 darken 这类只是以 dark 开头的无关类名。
    const darkSignal = /dark/i.test(themeAttr) || /(^|[\s_-])dark([\s_-]|$)/i.test(cls) || /dark/i.test(cs);
    const lightSignal = /light/i.test(themeAttr) || /(^|[\s_-])light([\s_-]|$)/i.test(cls) || /light/i.test(cs);
    if (darkSignal && !lightSignal) return 'dark';
    if (lightSignal && !darkSignal) return 'light';
    // 2) 背景色兜底：属性信号缺失或互相矛盾时，按底色亮度判定。
    let lum = root ? colorLuminance(getComputedStyle(root).backgroundColor) : null;
    if (lum === null && body) {
      lum = colorLuminance(getComputedStyle(body).backgroundColor);
    }
    if (lum === null) return 'light';
    return lum < 128 ? 'dark' : 'light';
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
  // 面板底色分亮 / 暗两套，运行时按宿主页面明暗择一使用。
  // 分别对应 styles/00_tokens.css 的 --cb-bg-page 亮暗两值，改外观时三处必须同步。
  A.PANEL_BG_LIGHT = '#f5f6f8';                    // 亮色宿主下的面板底
  A.PANEL_BG_DARK = '#1c2029';                     // 暗色宿主下的面板底
  A.PANEL_RADIUS_RIGHT = '12px 0 0 12px';          // 右侧挂靠：只圆左侧悬浮边
  A.PANEL_RADIUS_LEFT = '0 12px 12px 0';           // 左侧挂靠：只圆右侧悬浮边
  A.PANEL_SHADOW_RIGHT = '-4px 0 16px rgba(0,0,0,.25)';  // 右侧挂靠：向左投影
  A.PANEL_SHADOW_LEFT = '4px 0 16px rgba(0,0,0,.25)';    // 左侧挂靠：向右投影
  A.PANEL_Z = 2147483647;                          // 取层级上限，确保不被宿主网页元素遮挡

  // 普通聊天页需要渲染时间，会正常重试；非聊天页永远找不到，
  // 因此限制总次数，且重试过程只打 info 级日志。
  A.MAX_CONTAINER_RETRY = 80; // 约 2 分钟

  // 对话容器的「静默期」：DOM 停止变动达到此时长，才认为网页 AI 生成结束，
  // 此时才做一次结构化解析。网页 AI 逐字输出期间 DOM 持续变动，防抖会被反复
  // 重置，因此生成不结束就不会触发解析，从根本上避免「一边生成一边全量扫描」。
  // 滚动浏览时该值决定停手后多久出快照，取 1000ms：网页 AI 逐字输出与虚拟列表
  // 重排都可能出现短暂停顿，500ms 会在生成未真正结束时误判为静默、提前解析。
  A.GENERATE_IDLE_MS = 1000;

  // 发送按钮状态轮询周期：读按钮图标判定 AI 是否在生成，进而决定何时触发解析。
  // 取 500ms：比静默期更灵敏，能更早发现「生成刚结束」并触发一次解析；
  // 代价仅是每 500ms 读一次按钮元素，开销可忽略。
  A.BUTTON_POLL_MS = 500;

  // 会话切换巡检周期。该巡检只做会话 id 比对（代价很低），
  // 不做任何全量内容解析，因此可以保持较高频率以及时发现切会话。
  A.CONV_POLL_MS = 700;

  return A;
})();
