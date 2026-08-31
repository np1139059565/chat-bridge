// 内容脚本：注入悬浮对话框 iframe，并监听网页 AI 对话容器，
// 把网页对话内容同步到插件对话框；并按会话 id 隔离记录（切换左侧会话时同步切换）。
// 关键：AI 返回的工具调用是「渲染后的代码块」，并非字面 ```tool 围栏。
// 在 chatglm 等页面中，它的结构是：
//   <div class="language language-tool" lang="tool"><pre class="hljs"><code>{...}</code></pre></div>
// 因此从 innerText 里用正则找 ```tool 是找不到的，必须直接读取代码块 DOM。
(function () {
  const IFRAME_SRC = chrome.runtime.getURL('dialog/dialog.html');
  let iframe = null;
  let containerEl = null;
  let observer = null;
  let historyObserver = null;  // 监听左侧会话列表（侧边栏），随预设切换绑定到对应容器
  let historyEl = null;
  let lastText = '';
  let lastPageKey = '';
  let containerRetry = 0;
  let currentConvId = '';   // 当前会话 id（切换左侧会话时变化）
  let currentSel = '';      // 当前生效的对话容器选择器，供切换后重新绑定
  let dialogHidden = false;  // 对话框是否被用户关闭（持久化，刷新后不再自动弹出）
  let siteKey = '';          // 当前网站标识（按站点隔离数据与设置）
  let profileId = '';        // 当前生效的站点规则（glm / deepseek / custom）

  // 调试日志：统一前缀，便于在网页控制台用 [AI-Mirror] 过滤
  const DEBUG = true;
  function log() {
    if (!DEBUG) return;
    console.log.apply(console, ['[AI-Mirror][content]'].concat(Array.prototype.slice.call(arguments)));
  }
  function warn() {
    if (!DEBUG) return;
    console.warn.apply(console, ['[AI-Mirror][content]'].concat(Array.prototype.slice.call(arguments)));
  }

  // 站点规则表：不同模型的网页结构完全不同，无法用一套选择器通用。
  // 只使用各站点稳定的类名，绝不用 db183363 / _63c77b1 这类 CSS-Module 哈希（随时会变）。
  const PROFILES = {
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
      historySelectedMark: '.selected'              // 选中项额外带的类
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
      historySelectedMark: ''                       // 靠 href 与当前路径匹配判定选中
    }
  };

  // 按 hostname 猜测站点规则（用户未手动指定时）
  function guessProfile(host) {
    const h = String(host || '').toLowerCase();
    const ids = Object.keys(PROFILES);
    for (let i = 0; i < ids.length; i++) {
      const p = PROFILES[ids[i]];
      for (let j = 0; j < p.hosts.length; j++) {
        if (h === p.hosts[j] || h.endsWith('.' + p.hosts[j])) return ids[i];
      }
    }
    return 'glm';
  }

  function currentHost() {
    try { return location.hostname || ''; } catch (e) { return ''; }
  }

  // 读取「当前站点」的规则：站点规则按 hostname 自动识别（无需浏览器存储配置，
  // 配置统一由后端 config.yaml 管理）。容器选择器完全由预设规则决定——
  // 之前暴露的「自定义 class 选择器」无法稳定工作（各站 class 含易变哈希），已撤销。
  function getConfig(cb) {
    siteKey = currentHost() || 'unknown-site';
    profileId = guessProfile(siteKey);
    const prof = PROFILES[profileId] || PROFILES.glm;
    log('getConfig: 站点=' + siteKey, '规则=' + profileId, '容器=' + prof.container);
    cb({ profile: profileId, container: prof.container, profileLabel: prof.label });
  }

  function activeProfile() {
    return PROFILES[profileId] || PROFILES.glm;
  }

  function debounce(fn, ms) {
    let t;
    return function () {
      const args = arguments;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  /* ===== 面板外观常量 =====
   * 悬浮面板是注入到宿主网页里的 iframe，运行在页面上下文，读不到
   * dialog/style.css 的 CSS 变量，所以外框外观只能用常量写在这里。
   * 每个常量注明它在 style.css 中的对应令牌，改外观时两边必须同步，
   * 否则外框与面板内部会脱节。
   */
  const PANEL_W = '420px';                             // 常态宽度。style.css 窄屏断点取 419px 正是据此推定
  const PANEL_NARROW = 480;                            // 宿主窗口窄于此值时，面板改为铺满宽度
  const PANEL_BG = '#f5f6f8';                          // 对应 style.css 的 --cb-bg-page
  const PANEL_RADIUS = '12px 0 0 12px';                // 只圆左侧悬浮边：面板贴顶贴底，圆四角会在视口边缘露出网页背景
  const PANEL_SHADOW = '-4px 0 16px rgba(0,0,0,.25)';  // 向左投影，强化抽屉式悬浮感
  const PANEL_Z = 2147483647;                          // 取层级上限，确保不被宿主网页元素遮挡

  function panelWidth() {
    return window.innerWidth < PANEL_NARROW ? '100%' : PANEL_W;
  }

  function inject() {
    // 清理上一轮残留（扩展重导入 / 旧实例未移除）的 iframe，
    // 否则 id 守卫会误判“已存在”而跳过注入，导致对话框失效
    const old = document.getElementById('ai-mirror-iframe');
    if (old) { log('inject: 移除遗留 iframe'); old.remove(); }
    log('inject: 开始注入', IFRAME_SRC);
    iframe = document.createElement('iframe');
    iframe.id = 'ai-mirror-iframe';
    iframe.src = IFRAME_SRC;
    // 高度必须显式给出，不能用 top/bottom 双向拉伸：iframe 是替换元素，
    // height:auto 会退化成内在高度（默认 150px），此时 top 与 bottom 过度约束，
    // 浏览器会忽略 bottom，面板只剩一条窄带。
    iframe.style.cssText =
      'position:fixed;top:0;right:0;width:' + panelWidth() +
      ';height:100vh;border:0;border-radius:' + PANEL_RADIUS +
      ';box-shadow:' + PANEL_SHADOW +
      ';background:' + PANEL_BG +
      ';z-index:' + PANEL_Z + ';';
    // 尊重上一次的关闭状态：用户关掉后刷新页面不应自动弹回来
    iframe.style.display = dialogHidden ? 'none' : '';
    document.body.appendChild(iframe);
    log('inject: 注入完成（显示=' + !dialogHidden + '）');
    window.addEventListener('resize', () => {
      iframe.style.width = panelWidth();
    });
  }

  // 显隐状态持久化：关闭后刷新 / 新开标签页都保持关闭，直到用户再点图标
  function setDialogVisible(visible) {
    dialogHidden = !visible;
    const f = iframe || document.getElementById('ai-mirror-iframe');
    if (f) f.style.display = visible ? '' : 'none';
    try {
      chrome.storage.local.set({ aiMirrorHidden: dialogHidden });
      log('setDialogVisible: visible=' + visible + '（已持久化）');
    } catch (e) {
      warn('setDialogVisible: 持久化失败', e && e.message);
    }
  }

  function post(msg) {
    if (iframe && iframe.contentWindow) {
      log('post →', msg.type, msg.type === 'page_blocks' ? '消息数=' + (msg.messages || []).length : '');
      iframe.contentWindow.postMessage(msg, '*');
    } else {
      warn('post 失败：iframe 未就绪，消息被丢弃 →', msg && msg.type);
    }
  }

  // 稳定 id：同一段代码内容在页面重绘后保持同一张卡片（保留执行结果）。
  // 注意不能掺入下标，否则新消息插入会导致下标整体位移、卡片状态错位。
  function hashStr(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  }

  function textOf(el) {
    return (el && (el.innerText || el.textContent) || '').trim();
  }

  // 语言：优先 lang 属性，其次 language-xxx 类名，最后取代码块工具条上的语言名
  function codeLangOf(host) {
    if (!host || !host.getAttribute) return '';
    const attr = host.getAttribute('lang');
    if (attr) return attr;
    const m = /language-([a-zA-Z0-9_+#-]+)/.exec(String(host.className || ''));
    if (m) return m[1];
    const pre = host.matches('pre') ? host : host.querySelector('pre');
    if (pre) {
      const mm = /language-([a-zA-Z0-9_+#-]+)/.exec(String(pre.className || ''));
      if (mm) return mm[1];
    }
    const box = host.closest ? host.closest('.code-no-artifacts') : null;
    if (box) {
      const lp = box.querySelector('.top-outer .language');
      if (lp) return textOf(lp);
    }
    return '';
  }

  // 判断一个元素是否「本质上就是一个代码块」。
  // 关键：代码块外层常包着工具条（语言名 / 复制按钮），这些装饰不算正文，
  // 必须排除，否则整段回答会被误判成一个代码块而丢掉段落文本。
  function findCodeRoot(el) {
    if (!el || el.nodeType !== 1) return null;
    if (el.matches('div.language[lang], pre')) return el;
    const code = el.querySelector('div.language[lang], pre');
    if (!code) return null;
    const BLOCK_SEL = 'p, ul, ol, h1, h2, h3, h4, h5, h6, blockquote, table, li';
    const others = Array.prototype.filter.call(el.querySelectorAll(BLOCK_SEL), (n) => {
      if (code.contains(n) || n.contains(code)) return false;
      if (n.closest && n.closest('.top-outer')) return false;       // 工具条
      if (n.classList && n.classList.contains('language')) return false; // 语言名
      return true;
    });
    return others.length === 0 ? code : null;
  }

  function tableRows(t) {
    const rows = [];
    Array.prototype.forEach.call(t.querySelectorAll('tr'), (tr) => {
      const cells = [];
      Array.prototype.forEach.call(tr.children, (c) => cells.push(textOf(c)));
      if (cells.length) rows.push(cells);
    });
    return rows;
  }

  // 把一个内容节点解析成结构化的块列表（段落 / 标题 / 列表 / 代码 / 引用 / 表格）
  function parseBlocks(node, out) {
    out = out || [];
    Array.prototype.forEach.call(node.children || [], (el) => {
      if (el.nodeType !== 1) return;
      // chatglm 等站点代码块上方的工具条（语言名 + 复制按钮），不参与正文
      if (el.matches && el.matches('.top-outer')) return;
      // 思考区单独成块处理，禁止在正文解析里再次被当作段落重复收入
      // （按站点规则取：GLM 是 .advance-thinking，DeepSeek 是 .ds-think-content）
      const thinkSel = activeProfile().thinking;
      if (thinkSel && el.matches && el.matches(thinkSel)) return;
      const tag = el.tagName;

      const codeHost = findCodeRoot(el);
      if (codeHost) {
        const inner = codeHost.matches('pre') ? codeHost : (codeHost.querySelector('pre code') || codeHost.querySelector('code') || codeHost);
        const lang = codeLangOf(codeHost) || '';
        const code = textOf(inner);
        out.push({ type: 'code', lang: lang, code: code, id: 'c' + hashStr(lang + '|' + code) });
        return;
      }
      if (tag === 'P') {
        const t = textOf(el);
        if (t) out.push({ type: 'paragraph', text: t });
        return;
      }
      if (/^H[1-6]$/.test(tag)) {
        const t = textOf(el);
        if (t) out.push({ type: 'heading', level: Number(tag.charAt(1)), text: t });
        return;
      }
      if (tag === 'UL' || tag === 'OL') {
        const items = [];
        Array.prototype.forEach.call(el.children, (li) => {
          const t = textOf(li);
          if (t) items.push(t);
        });
        if (items.length) out.push({ type: 'list', ordered: tag === 'OL', items: items });
        return;
      }
      if (tag === 'BLOCKQUOTE') {
        const t = textOf(el);
        if (t) out.push({ type: 'quote', text: t });
        return;
      }
      if (tag === 'TABLE') {
        const rows = tableRows(el);
        if (rows.length) out.push({ type: 'table', rows: rows });
        return;
      }
      if (el.children.length) { parseBlocks(el, out); return; }
      const t = textOf(el);
      if (t) out.push({ type: 'paragraph', text: t });
    });
    return out;
  }

  // 结构化提取整段对话：按「站点规则」区分角色与内容块，GLM / DeepSeek 结构完全不同
  function extractBlocks(root) {
    const messages = [];
    const base = root || document;
    const P = activeProfile();
    const items = base.querySelectorAll(P.item);
    const scopes = items.length ? items : [base];
    const pushedQ = new Set(); // 本轮提取内去重；不可跨调用保留在 DOM 上，否则用户消息会被永久丢弃

    scopes.forEach((item) => {
      // —— 模式 A：一个消息项就是一条消息，用标记区分角色（DeepSeek）——
      if (!P.split) {
        const isAsst = !!(P.assistantMark && item.querySelector(P.assistantMark));
        messages.push(isAsst ? makeAssistant(item, P) : makeUser(item, P));
        return;
      }

      // —— 模式 B：一个 item 内同时含「提问」与「回答」两个子块（GLM）——
      // 用户提问：每个对话项各取一次，不依赖写在 DOM 元素上的粘性标记
      const q = item.querySelector(P.userItem);
      if (q && !pushedQ.has(q)) {
        pushedQ.add(q);
        messages.push(makeUser(q, P));
      }

      Array.prototype.forEach.call(item.querySelectorAll(P.assistantItem), (ans) => {
        messages.push(makeAssistant(ans, P));
      });
    });

    log('extractBlocks: 结构化提取到', messages.length, '条消息');
    return messages;
  }

  function makeUser(el, P) {
    const nameEl = P.userName ? el.querySelector(P.userName) : null;
    const bodyEl = P.userContent ? (el.querySelector(P.userContent) || el) : el;
    return { role: 'user', name: textOf(nameEl) || '用户', blocks: parseBlocks(bodyEl) };
  }

  function makeAssistant(el, P) {
    const blocks = [];

    // 思考区（GLM 的「深度思考」/ DeepSeek 的「已思考」）单独成块，且只取一次
    const think = P.thinking ? el.querySelector(P.thinking) : null;
    if (think) {
      const area = P.thinkingArea ? (think.querySelector(P.thinkingArea) || think) : think;
      const t = textOf(area);
      if (t) blocks.push({ type: 'thinking', text: t });
    }

    // 真正的回答正文。两个坑，缺一不可：
    // 1) 思考区内部往往也有正文容器（GLM 的 .answer-content-wrap /
    //    DeepSeek 的 .ds-markdown），必须排除，否则会把思考内容当正文、
    //    又和上面独立的 thinking 块重复。
    // 2) 一个回答常被拆成多个容器（例如文字一段、代码块另起一段）。
    //    只取第一个会把代码块整段漏掉 —— 表现为「插件记录落后于网页」，
    //    更严重的是：AI 的 tool 代码块提取不到 → 不生成卡片 → 无法执行 →
    //    没有 [TOOL_RESULT] 回传，自愈流程直接断在这里。
    let wraps = [];
    if (P.answerWrap) {
      const host = P.answerContent ? (el.querySelector(P.answerContent) || el) : el;
      Array.prototype.forEach.call(host.querySelectorAll(P.answerWrap), (w) => {
        if (!w.closest(P.thinking)) wraps.push(w);
      });
    }
    if (!wraps.length) {
      // DeepSeek 这类没有 wrap 概念的站点：直接用正文容器选择器。
      // 必须用完整类名精确定位，否则会命中思考区内部的同类容器。
      const c = P.assistantContent ? (el.querySelector(P.assistantContent) || el) : el;
      wraps = [c];
    }
    // 去掉被其它待解析容器包裹的嵌套容器，避免内容重复解析
    wraps = wraps.filter((w) => !wraps.some((o) => o !== w && o.contains(w)));
    wraps.forEach((w) => parseBlocks(w, blocks));

    const nameEl = P.assistantName ? el.querySelector(P.assistantName) : null;
    return { role: 'assistant', name: textOf(nameEl) || 'AI', blocks: blocks };
  }

  // ---------- 会话身份识别（切换左侧历史会话时同步切换记录） ----------
  // 不同站点的「会话 id 来源」与「选中项判定」完全不同，全部由 activeProfile() 驱动：
  //   - GLM    ：URL 带 ?cid=...；选中项是带 .selected 类的 .history-item
  //   - DeepSeek：URL 路径为 /a/chat/s/<uuid>；选中项 = href 与当前 location.pathname 一致的 <a>
  function hrefMatchesPath(href, path) {
    if (!href || !path) return false;
    if (href === path) return true;
    // 用 URL 解析把相对 / 绝对 href 统一成 pathname 再比（DeepSeek 的会话项是 <a> 链接）
    try {
      return new URL(href, location.href).pathname === path;
    } catch (e) {
      return href.indexOf(path) !== -1;
    }
  }

  function selectedHistoryItem() {
    const P = activeProfile();
    if (!P.historyItem) return null;
    const items = document.querySelectorAll(P.historyItem);
    if (!items.length) return null;
    const path = location.pathname;
    // 优先：href 与当前路径一致（DeepSeek 这类用 <a> 承载会话的站点，完全不依赖易变的哈希类）
    for (let i = 0; i < items.length; i++) {
      const href = items[i].getAttribute && items[i].getAttribute('href');
      if (hrefMatchesPath(href, path)) return items[i];
    }
    // 其次：带选中标记类（GLM 的 .selected）
    if (P.historySelectedMark) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].matches && items[i].matches(P.historySelectedMark)) return items[i];
      }
    }
    return null;
  }

  function getConversationId() {
    const P = activeProfile();
    // 1) 优先从 URL 提取会话 id（各站正则不同，写在 profile 里）
    if (P.convIdUrl) {
      const m = new RegExp(P.convIdUrl).exec(location.href);
      if (m && m[1]) return 'cid:' + m[1];
    }
    // 2) 退回：用左侧被选中会话项的标题做指纹
    const sel = selectedHistoryItem();
    if (sel) return 'h:' + hashStr(textOf(sel));
    return '';
  }

  function getConversationTitle() {
    const sel = selectedHistoryItem();
    return sel ? textOf(sel).slice(0, 80) : '';
  }

  function sendPage(force) {
    if (!containerEl) { log('sendPage: 对话容器未就绪，跳过推送'); return; }
    // 每次推送都重新算会话 id：避免切会话后内容仍被归到上一个会话名下
    const convId = getConversationId();
    const convChanged = !!convId && convId !== currentConvId;
    if (convChanged) currentConvId = convId;

    const messages = extractBlocks(containerEl);
    const key = convId + '|' + JSON.stringify(messages);
    if (!force && !convChanged && key === lastPageKey) {
      log('sendPage: 内容未变化，跳过重复推送');
      return;
    }
    lastPageKey = key;
    log('sendPage: 推送结构化对话 force=' + !!force, '会话=' + convId, '消息数=' + messages.length);
    post({
      type: 'page_blocks',
      messages: messages,
      url: location.href,
      siteKey: siteKey,                       // 按站点隔离数据与设置
      profileId: profileId,
      conversationId: convId,
      conversationTitle: getConversationTitle()
    });
  }

  // 普通聊天页需要渲染时间，会正常重试；非聊天页（如本例 aipay）永远找不到，
  // 因此限制总次数，且重试过程只打 info 级日志，避免在非聊天页把 console 刷成告警。
  const MAX_CONTAINER_RETRY = 80; // 约 2 分钟；超过则停止重试，避免在非聊天页无限刷告警

  function startObserver(sel) {
    currentSel = sel;
    const container = document.querySelector(sel);
    if (!container) {
      containerRetry += 1;
      // 仅在开始时提示一次（info），不按次刷 warn，避免非聊天页告警刷屏
      if (containerRetry === 1) {
        log('startObserver: 未找到对话容器，开始重试…', sel);
      } else if (containerRetry === Math.floor(MAX_CONTAINER_RETRY / 2)) {
        log('startObserver: 约 1 分钟仍未找到对话容器，该页可能不是聊天页；'
          + '可在设置里调整“对话容器选择器”，或点击工具栏图标重新探测');
      }
      if (containerRetry >= MAX_CONTAINER_RETRY) {
        // 真正放弃时才用 warn 提示一次，并说明如何在该页启用
        warn('startObserver: 超时未找到对话容器，停止重试（' + sel + '）。'
          + '该页可能不是聊天页；如需启用，请在设置里配置正确的“对话容器选择器”，'
          + '或刷新 / 点击工具栏图标重新探测');
        return; // 不再排程，结束无限循环
      }
      setTimeout(() => startObserver(sel), 1500); // 容器尚未渲染，稍后重试
      return;
    }
    containerRetry = 0;
    containerEl = container;
    lastText = container.innerText || '';
    log('startObserver: 找到对话容器', sel, '文本长度=' + lastText.length);
    sendPage();

    const onMutate = debounce(() => {
      const txt = container.innerText || '';
      if (txt !== lastText) {
        lastText = txt;
        log('onMutate: 对话文本已更新，长度=' + txt.length);
      }
      sendPage(); // 重新结构化提取（含新增代码块）
    }, 600);

    observer = new MutationObserver(onMutate);
    observer.observe(container, {
      childList: true,
      subtree: true,
      characterData: true
    });
    watchHistory(); // 同时绑定左侧会话列表监听（随预设切换）
  }

  // 手动重新探测对话容器：点击工具栏图标时调用，便于聊天页已加载但直接注入时未命中的情况
  function reprobe() {
    containerRetry = 0;
    getConfig((cfg) => startObserver(cfg.container));
  }

  // 左侧会话列表（侧边栏）监听：把会话切换事件即时反映到记录切换。
  // 各站的侧边栏容器由 activeProfile().historyContainer 决定，因此「对话容器选择器」切换预设时，
  // 这个监听会自动绑定到对应站点的侧边栏（DeepSeek 的 .ds-scroll-area / GLM 的 aside.aside-container）。
  function watchHistory() {
    const P = activeProfile();
    if (!P.historyContainer) return;
    const el = document.querySelector(P.historyContainer);
    if (!el || el === historyEl) return; // 未渲染 / 已绑定同一节点，跳过
    if (historyObserver) { historyObserver.disconnect(); historyObserver = null; }
    historyEl = el;
    historyObserver = new MutationObserver(debounce(() => {
      const id = getConversationId();
      if (id && id !== currentConvId) {
        currentConvId = id;
        log('history: 检测到会话切换 →', id, '标题=' + getConversationTitle());
        sendPage(true);
      }
    }, 300));
    historyObserver.observe(el, {
      childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'href']
    });
    log('watchHistory: 已监听左侧会话列表（' + P.historyContainer + '）');
  }

  // 左侧会话切换监听。
  // 关键：切换会话时 chatglm 可能整块替换对话容器节点，原先挂在旧节点上的
  // MutationObserver 会彻底失效（内容再变也不触发），因此必须检测节点更换并重绑。
  function watchConversation() {
    // 1) 侧边栏会话列表监听（随预设切换绑定到对应站点容器）
    watchHistory();
    // 2) 对话容器节点是否整块被替换（切会话时 chatglm 会替换节点，旧 observer 失效）
    if (currentSel) {
      const cur = document.querySelector(currentSel);
      // 容器被「替换」或「移除」都必须重绑：挂在已脱离文档的节点上的 observer 会彻底失效，
      // 表现为插件记录永久停在某一时刻、之后再也不更新。
      // 注意 cur 为 null（容器被移除）时同样要处理，不能写成 `cur && cur !== containerEl`。
      if (cur !== containerEl) {
        log('watch: 对话容器已变更（' + (cur ? '节点被替换' : '节点被移除') + '），重新绑定 observer');
        if (observer) { observer.disconnect(); observer = null; }
        containerEl = null;
        startObserver(currentSel); // 内部会以新节点重新 sendPage
        return;
      }
    }
    // 会话切换但容器节点未换（仅内容替换）时，靠会话 id 变化补一次强制推送
    const id = getConversationId();
    if (id && id !== currentConvId) {
      currentConvId = id;
      log('watch: 检测到会话切换 →', id, '标题=' + getConversationTitle());
      sendPage(true);
    }
  }
  setInterval(watchConversation, 700);

  // 来自对话框（iframe）的消息
  window.addEventListener('message', (e) => {
    const d = e.data;
    if (!d || !d.type) return;
    log('收到 iframe 消息 ←', d.type);
    if (d.type === 'request_page') sendPage(true);
  });

  // 来自后台（工具栏点击）的消息：切换悬浮对话框显隐（background.js 注释语义）
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === 'toggle_dialog') {
      let f = document.getElementById('ai-mirror-iframe');
      // 界面被清理 / 旧实例残留 / 注入失败时，点图标应先重新拉起，而不是直接隐藏一个不存在的元素
      if (!f) {
        log('toggle_dialog: 未找到 iframe，尝试重新注入');
        inject();
        f = document.getElementById('ai-mirror-iframe');
      }
      if (!f) {
        warn('toggle_dialog: 重新注入后仍无 iframe');
        return;
      }
      // 真正的 toggle：当前可见 → 隐藏；当前隐藏（display:none）→ 显示并重新探测对话容器
      if (f.style.display === 'none') {
        setDialogVisible(true);
        log('toggle_dialog: 显示对话框并重新探测对话容器');
        reprobe();
      } else {
        setDialogVisible(false);
        log('toggle_dialog: 隐藏对话框');
      }
    }
  });

  // 判断扩展是否仍然装载：真正被卸载后 chrome.runtime.id 会变为不可用
  function isExtensionAlive() {
    try {
      return !!(chrome && chrome.runtime && chrome.runtime.id);
    } catch (e) {
      return false;
    }
  }

  // MV3 清理机制：仅在扩展真正被卸载时移除残留 DOM 与监听器。
  // 注意：service worker 休眠终止同样会触发长连接 onDisconnect，
  // 若不区分就删 UI，会出现“插件凭空消失、点图标也拉不回来、且无任何报错”。
  function cleanup(reason) {
    if (isExtensionAlive()) {
      log('cleanup 跳过（原因=' + reason + '）：扩展仍在，仅 service worker 断连');
      return;
    }
    log('cleanup 执行（原因=' + reason + '）');
    if (iframe && iframe.parentNode) iframe.parentNode.removeChild(iframe);
    iframe = null;
    if (observer) { observer.disconnect(); observer = null; }
    if (historyObserver) { historyObserver.disconnect(); historyObserver = null; }
    historyEl = null;
    containerEl = null;
  }

  try {
    const port = chrome.runtime.connect({ name: 'ai-mirror-cleanup' });
    port.onDisconnect.addListener(() => cleanup('port_disconnect'));
  } catch (e) {
    warn('cleanup: 建立长连接失败（扩展可能已卸载）', e && e.message);
  }

  // 前进/后退缓存（bfcache）恢复时内容脚本不会重跑，需要补注入，否则界面消失
  window.addEventListener('pageshow', (e) => {
    if (e.persisted && !document.getElementById('ai-mirror-iframe')) {
      log('pageshow: bfcache 恢复，补注入 iframe');
      getConfig((cfg) => { inject(); startObserver(cfg.container); });
    }
  });

  log('content.js 已加载', location.href);

  getConfig((cfg) => {
    // 先取回关闭状态，再注入：否则用户关掉后一刷新又会自动弹出来
    chrome.storage.local.get('aiMirrorHidden', (res) => {
      dialogHidden = !!(res && res.aiMirrorHidden);
      log('初始化：读取到关闭状态 =', dialogHidden);
      inject();
      startObserver(cfg.container);
    });
  });
})();
