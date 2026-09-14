// 配置加载与连接状态
(function () {
  const A = window.AIStyleDebug;

  // 从本地存储读取配置：仅保留与调试能力相关的项，连接地址指向工具服务
  A.loadConfig = async function () {
    const stored = await chrome.storage.local.get(['aistyleCfg', 'backendUrl', 'aistyleDrawerSide']);
    const cfg = stored.aistyleCfg || {};
    A.state.backendUrl = stored.backendUrl || cfg.backend_url || A.DEFAULT_BACKEND_URL;
    A.state.screenshotEnabled = cfg.screenshot_enabled === true;
    A.state.styleListEnabled = cfg.style_list_enabled === true;
    A.state.pollIntervalMs = A.POLL_INTERVAL_MS;
    // 挂靠侧：持久化读取，刷新后保持上次选择
    A.state.drawerSide = stored.aistyleDrawerSide === 'left' ? 'left' : 'right';
  };

  A.setConnected = function (connected) {
    if (A.state.connected === connected) return;
    A.state.connected = connected;
    A.postToDrawer({ type: 'connection-state', connected });
  };

  A.isActivePage = function () {
    return document.visibilityState === 'visible' && document.hasFocus();
  };

  A.getTabId = function () {
    if (A.state.tabId != null) return Promise.resolve(A.state.tabId);
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: 'get-tab-id' }, (res) => {
        A.state.tabId = res && typeof res.tabId === 'number' ? res.tabId : null;
        resolve(A.state.tabId);
      });
    });
  };
})();
