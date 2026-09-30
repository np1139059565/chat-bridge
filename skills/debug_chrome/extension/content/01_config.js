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

  /**
   * 统一的后端请求入口：交给 service worker 代发。
   *
   * 为什么不能直接 fetch：内容脚本运行在页面源下，从公网页面（如 chat.deepseek.com）
   * 访问本机回环地址（127.0.0.1）会被 Chrome 的 Private Network Access 拦截：
   *   Access ... blocked by CORS policy: Permission was denied for this request
   *   to access the `loopback` address space.
   * service worker 是扩展源，不受此限制，故所有后端请求统一由它代发。
   * 内容脚本只保留 DOM 操作，不再直接发网络请求。
   *
   * @param {string} url 完整请求地址
   * @param {Object} [opts] 可选：{ method, body, timeoutMs }
   * @returns {Promise<Object>} 响应 JSON
   */
  A.proxyFetch = function (url, opts) {
    const o = opts || {};
    const timeoutMs = typeof o.timeoutMs === 'number' ? o.timeoutMs : A.PROXY_FETCH_TIMEOUT_MS;
    return new Promise((resolve, reject) => {
      let done = false;
      const finish = (fn, arg) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        fn(arg);
      };
      // 超时兜底：service worker 的 fetch 若挂起，sendMessage 回调不会返回，
      // 不设超时会让调用方永久 await，进而卡死轮询循环。
      const timer = setTimeout(() => finish(reject, new Error('PROXY_TIMEOUT')), timeoutMs);
      try {
        chrome.runtime.sendMessage({
          type: 'proxy-fetch',
          url: url,
          method: o.method || 'POST',
          body: o.body || null
        }, (resp) => {
          if (!resp || !resp.ok) {
            finish(reject, new Error((resp && resp.error) || 'PROXY_FAILED'));
            return;
          }
          finish(resolve, resp.data);
        });
      } catch (e) {
        finish(reject, e);
      }
    });
  };

  // 代理请求的默认超时上限（毫秒）
  A.PROXY_FETCH_TIMEOUT_MS = 15000;
})();
