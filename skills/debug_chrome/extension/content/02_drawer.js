// 抽屉 iframe 注入与 postMessage 通信
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  const SHAPE_BASE = 'position:fixed;border:none;background:transparent;z-index:2147483647;';

  // 抽屉形状：整高抽屉，贴右 / 贴左。抽屉只有「存在」与「不存在」两种状态，
  // 不存在折叠态；关闭即从页面移除。
  // 外框的投影与圆角必须加在 iframe 元素本身：iframe 会裁剪内部元素，
  // 画在内部 .drawer 上的投影落在 iframe 之外，实际不可见，亮色宿主下
  // 抽屉与页面同为浅色就会糊在一起、分不清边界。取值与镜像面板一致，
  // 见 extend/content/00_state.js 的 PANEL_SHADOW_RIGHT / PANEL_RADIUS_RIGHT。
  function openShape(side) {
    return side === 'left'
      ? SHAPE_BASE + 'top:0;left:0;right:auto;bottom:auto;width:380px;height:100vh;'
        + 'box-shadow:4px 0 16px rgba(0,0,0,.25);border-radius:0 12px 12px 0;'
      : SHAPE_BASE + 'top:0;right:0;left:auto;bottom:auto;width:380px;height:100vh;'
        + 'box-shadow:-4px 0 16px rgba(0,0,0,.25);border-radius:12px 0 0 12px;';
  }

  A.applyDrawerShape = function () {
    if (!state.drawerIframe) return;
    const side = state.drawerSide === 'left' ? 'left' : 'right';
    state.drawerIframe.style.cssText = openShape(side);
  };

  // 切换挂靠侧：更新状态并重新应用形状
  A.setDrawerSide = function (side) {
    state.drawerSide = side === 'left' ? 'left' : 'right';
    A.applyDrawerShape();
  };

  /**
   * 就绪看门狗：抽屉若在时限内未就绪，直接按关闭处理。
   * 不留隐形 iframe——起不来就当没开，同时停掉轮询，避免一个不可见的
   * 页面继续接单。
   */
  A.armDrawerWatchdog = function () {
    if (state.drawerWatchdogTimer) clearTimeout(state.drawerWatchdogTimer);
    state.drawerWatchdogTimer = setTimeout(() => {
      if (state.drawerReady || !state.drawerIframe) return;
      console.error(
        '[AI-Style-Debug] 抽屉在 ' + A.DRAWER_READY_TIMEOUT_MS + 'ms 内未就绪，已按关闭处理。'
      );
      A.closeDrawer();
    }, A.DRAWER_READY_TIMEOUT_MS);
  };

  A.markDrawerReady = function () {
    state.drawerReady = true;
    if (state.drawerWatchdogTimer) {
      clearTimeout(state.drawerWatchdogTimer);
      state.drawerWatchdogTimer = null;
    }
    // 抽屉就绪后立即推送一次宿主主题，避免首屏用默认主题闪一下
    A.postThemeToDrawer();
  };

  /**
   * 打开抽屉：创建 iframe、挂载到页面，并启动本页面的命令轮询。
   * 已打开时直接返回，避免重复创建。
   */
  A.openDrawer = function () {
    if (state.drawerIframe) return;
    const drawerUrl = chrome.runtime.getURL('drawer.html');
    const iframe = document.createElement('iframe');
    iframe.id = A.DRAWER_IFRAME_ID;
    iframe.src = drawerUrl;
    // 抽屉文档加载完成即推送一次宿主主题：此时 iframe 的 contentWindow 已可用，
    // 消息不会丢失，抽屉首屏即按宿主明暗渲染，无需等下一次主题变化。
    iframe.addEventListener('load', () => A.postThemeToDrawer());
    state.drawerIframe = iframe;
    A.applyDrawerShape();
    document.documentElement.appendChild(iframe);
    A.armDrawerWatchdog();
    // 抽屉打开 = 本页面开始接单：启动轮询，开始取属于自己的命令。
    A.startPolling();
    // 打开期间才需要主题监听与页面级交互监听（选择元素等）；
    // 关闭时全部解绑，不在宿主页面留任何活动代码。
    A.watchHostTheme();
    A.attachPageListeners();
    A.log('抽屉已打开：开始接单', '页面=' + location.href);
  };

  /**
   * 关闭抽屉：把抽屉从页面上彻底移除，并停止本页面的命令轮询。
   * 关闭即关闭，不留折叠钮、不留后台轮询；此后属于本页面的命令在独占期
   * 过后会自然逸散到其他页面执行。
   */
  A.closeDrawer = function () {
    // 先向后端上报「工具已关闭」：注销本页面的打开登记，
    // 属于本页面的命令随即可以逸散到其他页面，无需等僵尸登记超期。
    A.reportClosed();
    A.stopPolling();              // 再停轮询，避免移除过程中又取到新命令
    if (state.drawerWatchdogTimer) {
      clearTimeout(state.drawerWatchdogTimer);
      state.drawerWatchdogTimer = null;
    }
    if (state.drawerIframe && state.drawerIframe.parentNode) {
      state.drawerIframe.parentNode.removeChild(state.drawerIframe);
    }
    state.drawerIframe = null;
    state.drawerReady = false;
    // 关闭即拆除一切活动代码：主题监听与页面级交互监听全部解绑，
    // 宿主页面恢复原状，不在背后留任何监听或定时器。
    A.stopWatchHostTheme();
    A.detachPageListeners();
    A.log('抽屉已关闭：停止接单，命令将逸散到其他页面', '页面=' + location.href);
  };

  A.postToDrawer = function (payload) {
    if (state.drawerIframe && state.drawerIframe.contentWindow) {
      state.drawerIframe.contentWindow.postMessage(
        Object.assign({}, payload, { source: 'ai-debug-content', page_url: location.href }),
        '*'
      );
    }
  };

  // 注意：本文件的主题判定与监听逻辑，与另一个独立扩展
  // （extend/content/00_state.js 与 extend/content/05_index.js）存在同源实现。
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
    const parts = m[1].split(',').map((s) => parseFloat(s));
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

  /** 把当前宿主主题推送给抽屉 iframe。 */
  A.postThemeToDrawer = function () {
    A.postToDrawer({ type: 'host-theme', theme: A.detectHostTheme() });
  };

  /**
   * 监听宿主主题变化并持续推送。
   * 网页切换主题通常改 <html> / <body> 的 class 或 style，因此监听这两处的属性变化；
   * 连续变化用定时器节流，避免高频推送。
   * 观察器仅在抽屉打开期间存在（见 openDrawer / closeDrawer）：
   * 关闭后无人消费主题，继续观察纯属后台空转。
   */
  A.watchHostTheme = function () {
    A.postThemeToDrawer();
    // 已在观察则不重复建：重复调用只刷新一次推送
    if (state.themeObserver) return;
    let timer = null;
    const onChange = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => { A.postThemeToDrawer(); }, 200);
    };
    const opts = { attributes: true, attributeFilter: ['class', 'style', 'data-theme', 'data-color-mode'] };
    state.themeObserver = new MutationObserver(onChange);
    state.themeObserver.observe(document.documentElement, opts);
    if (document.body) state.themeObserver.observe(document.body, opts);
  };

  /** 停止宿主主题监听：抽屉关闭时调用，断开观察器，不在后台空转。 */
  A.stopWatchHostTheme = function () {
    if (state.themeObserver) {
      state.themeObserver.disconnect();
      state.themeObserver = null;
    }
  };

  A.showToast = function (text) {
    const toast = document.createElement('div');
    toast.textContent = text;
    toast.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);'
      + 'background:#333;color:#fff;padding:8px 16px;border-radius:4px;'
      + 'font-size:13px;z-index:2147483646;';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2500);
  };
})();
