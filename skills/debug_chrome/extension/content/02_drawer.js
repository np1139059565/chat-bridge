// 抽屉 iframe 注入与 postMessage 通信
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  const SHAPE_BASE = 'position:fixed;border:none;background:transparent;z-index:2147483647;';

  // 折叠态：贴右下角（右侧挂靠）/ 左下角（左侧挂靠）的小圆钮
  function foldShape(side) {
    return side === 'left'
      ? SHAPE_BASE + 'top:auto;bottom:24px;left:24px;right:auto;width:48px;height:48px;'
      : SHAPE_BASE + 'top:auto;bottom:24px;right:24px;left:auto;width:48px;height:48px;';
  }

  // 展开态：整高抽屉，贴右 / 贴左
  function openShape(side) {
    return side === 'left'
      ? SHAPE_BASE + 'top:0;left:0;right:auto;bottom:auto;width:380px;height:100vh;'
      : SHAPE_BASE + 'top:0;right:0;left:auto;bottom:auto;width:380px;height:100vh;';
  }

  A.applyDrawerShape = function (open) {
    if (!state.drawerIframe) return;
    const side = state.drawerSide === 'left' ? 'left' : 'right';
    state.drawerIframe.style.cssText = open ? openShape(side) : foldShape(side);
  };

  // 切换挂靠侧：更新状态并重新应用当前形状
  A.setDrawerSide = function (side) {
    state.drawerSide = side === 'left' ? 'left' : 'right';
    A.applyDrawerShape(state.drawerOpen);
  };

  A.armDrawerWatchdog = function () {
    if (state.drawerWatchdogTimer) clearTimeout(state.drawerWatchdogTimer);
    state.drawerWatchdogTimer = setTimeout(() => {
      if (state.drawerReady || !state.drawerIframe) return;
      state.drawerIframe.style.display = 'none';
      console.error(
        '[AI-Style-Debug] 抽屉在 ' + A.DRAWER_READY_TIMEOUT_MS + 'ms 内未就绪，已隐藏悬浮入口以免遮挡页面点击。'
      );
    }, A.DRAWER_READY_TIMEOUT_MS);
  };

  A.markDrawerReady = function () {
    state.drawerReady = true;
    if (state.drawerWatchdogTimer) {
      clearTimeout(state.drawerWatchdogTimer);
      state.drawerWatchdogTimer = null;
    }
    if (state.drawerIframe) state.drawerIframe.style.display = '';
  };

  A.initShadowDrawer = function () {
    if (document.getElementById(A.SHADOW_HOST_ID)) return;
    const host = document.createElement('div');
    host.id = A.SHADOW_HOST_ID;
    host.style.cssText = 'position:fixed;top:0;left:0;width:0;height:0;z-index:2147483647;';
    document.documentElement.appendChild(host);
    state.shadowRoot = host.attachShadow({ mode: 'open' });
    const drawerUrl = chrome.runtime.getURL('drawer.html');
    state.drawerIframe = document.createElement('iframe');
    state.drawerIframe.src = drawerUrl;
    A.applyDrawerShape(false);
    state.shadowRoot.appendChild(state.drawerIframe);
    A.armDrawerWatchdog();
  };

  A.postToDrawer = function (payload) {
    if (state.drawerIframe && state.drawerIframe.contentWindow) {
      state.drawerIframe.contentWindow.postMessage(
        Object.assign({}, payload, { source: 'ai-debug-content', pageUrl: location.href }),
        '*'
      );
    }
  };

  A.showToast = function (text) {
    const toast = document.createElement('div');
    toast.textContent = text;
    toast.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:8px 16px;border-radius:4px;font-size:13px;z-index:2147483646;';
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2500);
  };
})();
