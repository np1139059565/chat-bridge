// 模块：extend/content/04_observer.js
// 用途：对话容器与左侧会话列表的监听、重新探测、以及扩展卸载时的清理。
// 依赖：content/00_state.js、content/01_panel.js、content/03_bridge.js
(function () {
  'use strict';
  const A = window.AIMirrorContent;

  /**
   * 安排一次「静默期后」的结构化扫描。
   * 每次调用都会重置计时器：只要 DOM 还在变动（网页 AI 正在生成），
   * 扫描就一直不触发；直到停止变动满 GENERATE_IDLE_MS 才真正解析一次。
   * 这样把「生成中的高频扫描」压缩为「生成结束后的一次扫描」，
   * 显著降低网页 AI 生成期间的强制布局与全量解析开销。
   * @param {string} [reason] 触发来源：默认 'scroll'（滚动 / 可视区变化）；
   *   首次绑定容器时传 'manual'，保持完整解析行为（含建卡）。
   */
  A.scheduleScan = function (reason) {
    // 面板未打开：不做任何解析与推送，避免隐藏状态下空转
    if (!A.state.active) return;
    // 生成期间不抓取：网页 AI 说话时页面持续变动（含滚动条），此时解析既无意义又卡顿。
    // 生成结束由发送按钮轮询负责触发，因此这里直接放弃本次静默扫描。
    if (A.state.isGenerating) {
      if (A.state.scanTimer) { clearTimeout(A.state.scanTimer); A.state.scanTimer = null; }
      return;
    }
    // 触发来源：默认按「滚动 / 可视区变化」处理；
    // 首次绑定容器时传入 'manual'，保持原有的完整解析行为（含建卡）。
    const src = reason || 'scroll';
    if (A.state.scanTimer) clearTimeout(A.state.scanTimer);
    A.state.scanTimer = setTimeout(function () {
      A.state.scanTimer = null;
      A.sendPage(false, src);
    }, A.GENERATE_IDLE_MS);
  };

  /**
   * 监听对话区滚动。
   * 背景：DeepSeek 等站点用虚拟列表，向上滚动历史时靠 transform / 定位移动已有节点，
   * 不增删 DOM，MutationObserver 收不到任何通知，导致滚动不触发快照。
   * 因此改用滚动事件感知：在 document 上以捕获阶段监听，凡滚动目标与对话容器
   * 存在包含关系（容器自身、其祖先、其后代）即视为对话区滚动。
   * 侧边栏等无关区域的滚动不满足该关系，会被排除。
   * @param {Element} container 对话容器
   */
  A.startScrollWatch = function (container) {
    // 先解绑旧监听，避免切换容器 / 重复绑定时叠加
    if (A.state.scrollHandler) {
      document.removeEventListener('scroll', A.state.scrollHandler, true);
      A.state.scrollHandler = null;
    }
    const c = container;
    A.state.scrollHandler = function (e) {
      const t = e.target;
      if (!t || t.nodeType !== 1) return;
      // 仅当滚动目标与对话容器存在包含关系时才处理
      const related = (t === c) || (t.contains && t.contains(c)) || (c.contains && c.contains(t));
      if (!related) return;
      // 滚动触发快照（来源默认 'scroll'）：scheduleScan 内部会重置静默计时器，
      // 滚动期间持续重置，停手满静默期后才真正解析一次
      A.scheduleScan('scroll');
    };
    document.addEventListener('scroll', A.state.scrollHandler, true);
  };

  /**
   * 绑定对话容器监听。找不到时按固定间隔重试，超过上限则放弃。
   * 非聊天页永远找不到容器，因此限制总次数，且重试过程只打 info 级日志，
   * 避免在非聊天页把 console 刷成告警。
   * @param {string} sel 对话容器选择器
   */
  A.startObserver = function (sel) {
    // 幂等：档案热更新（applyProfiles → reprobe）或抽屉重开都会再次调用本函数。
    // 先拆掉上一轮观察器与轮询，避免同一个容器挂多份监听导致重复解析、
    // 同一事件触发多次推送（历史上「卡片双执行」一类问题的温床）。
    if (A.state.observer) {
      try { A.state.observer.disconnect(); } catch (e) { /* 已被销毁则忽略 */ }
      A.state.observer = null;
    }
    A.state.currentSel = sel;
    const container = document.querySelector(sel);
    if (!container) {
      A.state.containerRetry += 1;
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
    // 找到容器：重置重试计数
    A.state.containerRetry = 0;
    A.state.containerEl = container;
    // 首次解析延后到静默期后，与后续更新走同一条路径，
    // 避免刚绑定就立刻做一次全量解析（此时内容通常还在渲染）。
    // 来源标记为手动：首次进入需完整处理（含为已有卡片建卡）。
    A.scheduleScan('manual');

    // 容器内容变化时，重置静默计时器；只有 DOM 停止变动达到 GENERATE_IDLE_MS
    // 才真正做一次结构化解析。网页 AI 逐字输出期间 mutation 持续触发，
    // 计时器被反复重置，因此生成结束前不会扫描。
    A.state.observer = new MutationObserver(function () {
      A.scheduleScan();
    });
    A.state.observer.observe(container, {
      childList: true,
      subtree: true,
      characterData: true
    });
    A.startScrollWatch(container); // 监听滚动：虚拟列表滚动可能不增删节点，MutationObserver 收不到
    A.watchHistory(); // 同时绑定左侧会话列表监听（随预设切换）
    A.startButtonWatch(); // 启动发送按钮状态轮询（生成结束即解析）
    A.startRiskIdleWatch(); // 风控恢复的空闲态低频兜底（翻转被错过时补上）
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
        A.sendPage(true, 'switch');
      }
    }, 300));
    A.state.historyObserver.observe(el, {
      childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'href']
    });
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
        if (A.state.observer) { A.state.observer.disconnect(); A.state.observer = null; }
        A.state.containerEl = null;
        A.startObserver(A.state.currentSel); // 内部会以新节点重新安排扫描
        return;
      }
    }
    // 会话切换但容器节点未换（仅内容替换）时，靠会话 id 变化补一次强制推送。
    // 这是「用户主动切会话」，必须立即反映，不能等静默期。
    const id = A.getConversationId();
    if (id && id !== A.state.currentConvId) {
      A.state.currentConvId = id;
      A.log('watch: 检测到会话切换 →', id, '标题=' + A.getConversationTitle());
      A.sendPage(true, 'switch');
    }
  };

  /**
   * 按「生成中图标特征」判断按钮是否处于生成态。
   * 原理：AI 说话时按钮换成「停止」方块图标，其 path 含固定片段
   * （profile.sendButtonStopMark）；空闲时为发送箭头，不含该片段。
   * 不依赖首帧基准，因此扩展在任意时刻注入都能得到正确结果。
   * @param {Element} btn 发送按钮元素
   * @param {Object} P 站点规则
   * @returns {boolean} 是否处于生成中
   */
  A.isStopButton = function (btn, P) {
    if (!btn || !btn.querySelectorAll || !P.sendButtonStopMark) return false;
    const paths = btn.querySelectorAll('svg path');
    for (let i = 0; i < paths.length; i++) {
      const d = paths[i].getAttribute('d') || '';
      if (d.indexOf(P.sendButtonStopMark) !== -1) return true;
    }
    return false;
  };

  /**
   * 判断当前视口是否停在对话最新处（底部）。
   * 原理：站点用「滚动到底部」按钮的显隐表达该状态——向上翻看历史时按钮出现，
   * 已回到最新时隐藏。故「按站点规则查不到该按钮」即视为已在底部。
   * 站点未配置 scrollToBottomButton 时保守返回 false：宁可不让滚动轮次自动执行，
   * 也不能因判定缺失而误执行历史卡片。
   * @returns {boolean} 是否已在底部
   */
  A.isAtBottom = function () {
    const P = A.activeProfile();
    // 底部判定开关（档案字段 atBottomCheck，默认开启）：
    // 某些站点的「滚动到底部」按钮不可靠或根本不存在，判定恒为「不在底部」，
    // 导致滚动轮次的自动执行与风控恢复被永久拦住。关闭该开关后直接返回 true，
    // 视为「始终在底部」，不再用底部状态限制自动执行。
    // 默认开启：字段缺省（undefined / 空串）都按开启处理，只有显式 false 才关闭。
    if (P && P.atBottomCheck === false) return true;
    const sels = P && P.scrollToBottomButton;
    if (!sels || !sels.length) return false;   // 未配置：保守判定为「不在底部」
    for (let i = 0; i < sels.length; i++) {
      // 任一选择器命中即表示按钮存在 = 用户不在底部。
      // 选择器的精确性由站点规则保证（见 00_state.js 的 scrollToBottomButton 注释）：
      // 只配同时带三条类名的精确选择器，不配宽泛的兜底选择器，
      // 否则会误伤「继续生成」之类的其它浮动按钮。
      if (document.querySelector(sels[i])) return false;
    }
    return true;
  };

  /**
   * 生成结束后触发解析：以 generate 来源推送一次。
   * generate 是「AI 新增对话」的正式来源，会为本轮最新卡片安排自动执行。
   */
  A.triggerGenerate = function () {
    if (!A.state.active) return;
    A.sendPage(true, 'generate'); A._flushPendingPaste('flip');
  };

  /**
   * 生成态轮询：按 BUTTON_POLL_MS 周期判定「AI 是否正在说话」，维护 state.isGenerating。
   * 两条判定路径，按站点规则择一：
   *  · 选择器判定：站点配了 generatingSelectors 时，任一选择器命中即为生成中（GLM 走此路径）。
   *  · 图标判定：站点配了 sendButton + sendButtonStopMark 时，按钮内停止图标特征命中即为生成中
   *    （DeepSeek 走此路径）。
   * 两种方式都不依赖首帧基准，扩展在任意时刻注入都能判对。
   * 由「生成中」翻回「空闲」即生成刚结束，触发一次全量解析；两条路径都未配置时不轮询。
   */
  A.startButtonWatch = function () {
    const P = A.activeProfile();
    const bySelector = !!(P.generatingSelectors && P.generatingSelectors.length);
    const byButton = !!(P.sendButton && P.sendButtonStopMark);
    if (!bySelector && !byButton) return;      // 无可用判定方式，跳过
    if (A.state.buttonTimer) clearInterval(A.state.buttonTimer);
    A.state.buttonTimer = setInterval(function () {
      let nowGen = false;
      if (bySelector) {
        // 任一生成态选择器命中 → 正在生成
        for (let i = 0; i < P.generatingSelectors.length; i++) {
          if (document.querySelector(P.generatingSelectors[i])) { nowGen = true; break; }
        }
        // GLM 专项（2026-11-08 事故修复）：m-three-row 在「输入框有多行内容」时同样出现
        //（输入区随内容变高），选择器命中≠生成中。站点配了 generatingRequireEmptyInput
        // 时，命中后还需输入框为空才算生成中——生成中输入框必为空（文本已随发送清空）。
        // 代价与取舍：生成期间用户手动输入会使判定翻回空闲（假阴性），此时粘贴不挂起；
        // GLM 生成中本就允许输入排队发送，假阴性危害远小于死锁，可接受。
        if (nowGen && P.generatingRequireEmptyInput) {
          const ta = document.querySelector(P.inputSelector);
          if (ta && String(ta.value || '').trim() !== '') nowGen = false;
        }
      } else {
        const btn = document.querySelector(P.sendButton);
        if (!btn) return;
        nowGen = A.isStopButton(btn, P);
      }
      if (nowGen !== A.state.isGenerating) {
        // 翻转点是风控恢复的唯一入口，必须留痕。
        // 若日志里连这条都没有，说明生成态判定本身失效（按钮选择器读错等），
        // 那风控恢复根本不会被触发，排查方向应立即转向生成态判定。
        A.log && A.log('[生成态] 翻转 ' + A.state.isGenerating + ' → ' + nowGen);
        A.state.isGenerating = nowGen;
        // 由「生成中」回到「空闲」= 生成刚结束 → 触发一次全量解析
        // 面板未打开时不解析：sendPage 内部已有守卫，这里提前返回省掉判断开销
        if (!nowGen) {
          A.triggerGenerate();
          // 记录翻转时刻：空闲兜底据此判断「这一轮是否已被翻转路径处理过」
          A.state.lastFlipAt = Date.now();
          // 风控恢复：这个翻转点也可能是「被风控掐断」而非正常说完（实现见 07_stopped_watch.js）。
          // 挂在这里而不是轮询特征，是因为特征会随恢复正常而消失，轮询必然漏检或误触发。
          //
          // 必须是「多次递增复查」，不能只查一次。
          //
          // 原因（2026-11-07 实机）：「服务器暂时不可用」这类状态文字渲染晚于
          // 按钮翻转，原先固定等 800ms 只查一次，结果那一刻文字还没出现，
          // 检查落空后再无第二次机会。快照证实该提示确实存在于消息容器内，
          // 判定逻辑本身没错，错在只给了一次机会、且给得太早。
          //
          // 改为 0.8/1.6/3.2/5.6 秒四次递增复查，累计约 10 秒：
          // 越早越密，因为多数情况下文字很快就出现；后面拉长间隔覆盖慢渲染。
          // 任一命中即停，避免恢复动作被重复触发。
          A.recheckStopped(0);
        }
      }
    }, A.BUTTON_POLL_MS);
  };

  /**
   * 风控恢复的空闲态兜底检查：低频、仅在空闲时执行。
   *
   * 为什么需要它：翻转触发是快路径，但只在那一个瞬间执行一次。
   * 若生成态判定本身失效（按钮选择器读错、站点改版），isGenerating 可能
   * 永远不翻转，快路径一次也不会触发。此兜底与翻转并存，负责补上这类缺口。
   *
   * 为什么低频：风控恢复不紧急，晚几秒无实际损失；而检查本身要读 DOM、
   * 跑一遍消息解析，查得越勤越拖慢页面，也让「持续被脚本扫描」的特征更明显。
   *
   * 三重跳过，避免无谓开销：
   *  · 面板未激活（用户没在看）——不介入；
   *  · 正在生成——那时页面在输出，既没必要也最费资源；
   *  · 距上次翻转不足一个周期——该轮已由快路径处理过，不重复。
   */
  /**
   * 风控恢复的多次递增复查。
   *
   * 为什么需要：状态文字（尤其「服务器暂时不可用」）渲染晚于按钮翻转，
   * 原先固定等 800ms 只查一次，那一刻文字还没出现，检查落空后再无第二次机会。
   * 2026-11-07 实机快照证实判定逻辑本身没错，错在只给了一次机会且给得太早。
   *
   * 间隔取 0.8/1.6/3.2/5.6 秒，累计约 10 秒：越早越密（多数情况文字很快出现），
   * 后面拉长覆盖慢渲染。任一次命中即停，避免恢复动作被重复触发。
   *
   * @param {number} idx 当前复查序号
   */
  const RECHECK_DELAYS = [800, 1600, 3200, 5600];
  A.recheckStopped = function (idx) {
    if (idx >= RECHECK_DELAYS.length) {
      A.log && A.log('[风控恢复] 多次复查均未命中停止形态，放弃本轮');
      return;
    }
    setTimeout(function () {
      if (!A.recoverIfStopped) {
        // 恢复函数不存在说明 07_stopped_watch.js 没加载成功。
        // 这种情况此前完全静默，会让人误以为「检测了但没命中」，
        // 实际是「函数根本不存在」。记一条以便区分，且不再重试。
        A.warn && A.warn('[风控恢复] 恢复函数未定义，07_stopped_watch.js 可能未加载');
        return;
      }
      // 返回 true 表示已识别到形态（或本轮无需再查），停止复查
      if (A.recoverIfStopped() === true) return;
      A.recheckStopped(idx + 1);
    }, RECHECK_DELAYS[idx]);
  };

  A.startRiskIdleWatch = function () {
    if (A.state.riskIdleTimer) clearInterval(A.state.riskIdleTimer);
    A.state.riskIdleTimer = setInterval(function () {
      if (!A.state.active) return;              // 面板未打开，不介入
      if (A.state.isGenerating) return;         // 生成中，跳过
      const since = Date.now() - (A.state.lastFlipAt || 0);
      // 刚翻转过：快路径已处理，跳过本轮兜底
      if (A.state.lastFlipAt && since < A.RISK_IDLE_CHECK_MS) return;
      if (A.recoverIfStopped) A.recoverIfStopped();
    }, A.RISK_IDLE_CHECK_MS);
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
    if (A.isExtensionAlive()) return;
    if (A.state.iframe && A.state.iframe.parentNode) A.state.iframe.parentNode.removeChild(A.state.iframe);
    A.state.iframe = null;
    // 一并解绑 resize 监听与主题监听，避免卸载后仍有回调挂在 window 上
    if (A.state.resizeHandler) {
      window.removeEventListener('resize', A.state.resizeHandler);
      A.state.resizeHandler = null;
    }
    if (A.stopConvWatch) A.stopConvWatch();
    if (A.stopThemeWatch) A.stopThemeWatch();
    // 取消待执行的静默扫描，避免清理后仍触发一次解析
    if (A.state.scanTimer) { clearTimeout(A.state.scanTimer); A.state.scanTimer = null; }
    // 取消未走完的空快照复查，避免清理后仍触发一次强制重推
    if (A.cancelEmptyRetry) A.cancelEmptyRetry();
    if (A.state.buttonTimer) { clearInterval(A.state.buttonTimer); A.state.buttonTimer = null; }
    if (A.state.riskIdleTimer) { clearInterval(A.state.riskIdleTimer); A.state.riskIdleTimer = null; }
    if (A.state.observer) { A.state.observer.disconnect(); A.state.observer = null; }
    if (A.state.historyObserver) { A.state.historyObserver.disconnect(); A.state.historyObserver = null; }
    if (A.state.scrollHandler) {
      document.removeEventListener('scroll', A.state.scrollHandler, true);
      A.state.scrollHandler = null;
    }
    A.state.historyEl = null;
    A.state.containerEl = null;
  };
})();
