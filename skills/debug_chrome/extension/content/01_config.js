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
    // 轮询间隔取常量默认值；快速间隔与其窗口同样取默认，不对外暴露配置。
    A.state.pollIntervalMs = A.POLL_INTERVAL_MS;
    // 挂靠侧：持久化读取，刷新后保持上次选择
    A.state.drawerSide = stored.aistyleDrawerSide === 'left' ? 'left' : 'right';
  };

  /**
   * 更新连接状态并广播给抽屉。
   *
   * 这里刻意不做「状态相同就跳过」的去重：内容脚本与抽屉是两个独立文档，
   * 发送方无从得知对端是否真的收到过上一次广播。抽屉 iframe 加载期间尚未
   * 注册监听器，首次心跳的广播会丢失；若按状态去重，后续心跳因状态未变而
   * 不再发送，抽屉就会永久停留在初始的「未连接」，而接口其实一直正常。
   *
   * 去重交给接收方：抽屉侧的 connected 是 ref，重复赋相同值不会触发渲染，
   * 因此重复广播不产生额外开销，也不会让界面闪烁。
   *
   * @param {boolean} connected 当前是否已连通工具服务
   */
  A.setConnected = function (connected) {
    // 状态真的变了才记录时刻：先快后慢的节奏以「变化」为触发，
    // 若每次心跳都刷新时刻，快速窗口会被无限延长，等于一直每秒轮询。
    if (A.state.connected !== connected) {
      A.state.connectedChangedAt = Date.now();
    }
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
