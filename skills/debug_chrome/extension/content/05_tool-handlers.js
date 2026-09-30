// 工具命令处理与结果回传
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  // 经提供方通道回传某次工具调用的结果。
  // 走 service worker 代发，原因同心跳：内容脚本在页面源下直连本机地址会被拦截。
  A.postResult = async function (requestId, result) {
    try {
      await A.proxyFetch(`${state.backendUrl}/api/ext/${A.PROVIDER}`, {
        method: 'POST',
        body: { action: 'result', request_id: requestId, result: result },
      });
    } catch (err) {
      // 回传失败由服务端转发超时处理
    }
  };

  // 处理一条待执行命令：{ request_id, tool, params, silent }
  // 普通工具：执行前后向抽屉推送卡片信息，展示工具调用细节。
  // silent 工具（如 push_message）：不生成抽屉卡片；执行结果仍照常回传，
  // 否则调用方只能拿到入队确认，无法得知动作是否真正生效。
  A.handleTask = async function (task) {
    if (!task || !task.request_id) return;
    const silent = !!task.silent;
    const cardId = task.request_id;
    if (!silent) {
      A.postToDrawer({
        type: 'tool-card',
        id: cardId,
        tool: task.tool,
        params: task.params || {},
        status: 'running',
        timestamp: Date.now(),
      });
    }
    const outcome = await A.handleToolRequest(task);
    // 结果一律回传（含 silent 工具），让调用方拿到真实执行状态；
    // silent 仅表示不在抽屉生成工具卡片。
    // 是否把结果再发回网页 AI，由调用方（插件侧 no_reply 参数）决定，不在此处理。
    await A.postResult(task.request_id, outcome);
    if (silent) return;
    A.postToDrawer({
      type: 'tool-card',
      id: cardId,
      tool: task.tool,
      params: task.params || {},
      status: outcome && outcome.success ? 'done' : 'error',
      result: outcome,
      timestamp: Date.now(),
    });
  };

  // 目标页面：工具调用可携带 page_url，把查询路由到元素实际所在的 iframe。
  // 调试扩展的 content script 只运行在顶层文档，子页面内没有它；
  // 因此子页面查询依赖用户已安装的「iframe 点选补丁」代答。
  // 未传 page_url 时，在顶层文档查询。
  //
  // 关键分支：page_url 指向顶层文档本身时必须在顶层查询。
  // findFrameByUrl 只遍历 iframe，顶层文档不在其中，若不先判断就会把
  // 「在当前页面查元素」误判为子页面路由，直接返回 FRAME_NOT_FOUND。
  async function runInTargetPage(params, fnTop, fnFrame) {
    const url = params.page_url || '';
    if (url) {
      if (A.normalizeUrl(url) === A.normalizeUrl(location.href)) return fnTop();
      const frame = A.findFrameByUrl(url);
      if (!frame) {
        return { success: false, error: 'FRAME_NOT_FOUND', page_url: url, available: A.frameUrls() };
      }
      return fnFrame(frame);
    }
    return fnTop();
  }

  // 工具处理函数表：工具名 → 处理函数（签名统一为 (params) => result）。
  // 新增工具只需写一个处理函数并登记到表里，不必改分发逻辑。
  A.TOOL_HANDLERS = {
    get_element_style: (params) => A._toolGetElementStyle(params),
    get_page_snapshot: (params) => A._toolSnapshot(params),
    get_console_logs: (params) => A._toolConsoleLogs(params),
    get_network_logs: (params) => A._toolNetworkLogs(params),
    exec_js: (params) => A._toolExecJs(params),
    push_message: (params) => A._toolPushMessage(params),
    // 抽屉控制类工具：供外部指令（/dbg-* 等）调用，由扩展自己执行
    open_drawer: (params) => A._toolOpenDrawer(params),
    close_drawer: (params) => A._toolCloseDrawer(params),
    switch_drawer_side: (params) => A._toolSwitchSide(params),
    open_settings: (params) => A._toolOpenSettings(params),
    close_settings: (params) => A._toolCloseSettings(params),
  };

  // ---------- 抽屉控制类工具 ----------
  // 这些工具由外部指令（/dbg-open 等）经工具服务入队、扩展轮询取走后执行，
  // 宿主全程不碰扩展内部状态。

  /** 打开调试抽屉；已打开视为成功（幂等）。 */
  A._toolOpenDrawer = function () {
    if (state.drawerIframe) return { success: true, message: '抽屉已打开' };
    A.openDrawer();
    return { success: true, message: '抽屉已打开' };
  };

  /** 关闭调试抽屉；已关闭视为成功（幂等）。 */
  A._toolCloseDrawer = function () {
    if (!state.drawerIframe) return { success: true, message: '抽屉已关闭' };
    A.closeDrawer();
    return { success: true, message: '抽屉已关闭' };
  };

  /** 切换抽屉挂靠侧：参数 side 为 left / right；非法或缺失则在左右之间切换。 */
  A._toolSwitchSide = function (params) {
    const want = (params && params.side) || '';
    const side = (want === 'left' || want === 'right')
      ? want
      : (state.drawerSide === 'left' ? 'right' : 'left');
    A.setDrawerSide(side);
    return { success: true, side: side };
  };

  /** 打开设置页：抽屉未开则先开抽屉、并置待切视图；已开则直接切视图。 */
  A._toolOpenSettings = function () {
    if (!state.drawerIframe) {
      // 先记住要切的视图：抽屉就绪时会消费该标记（见 06_messages.js）。
      state.pendingView = 'settings';
      A.openDrawer();
      return { success: true, message: '抽屉已打开并切到设置页' };
    }
    A.postToDrawer({ type: 'ai-debug-set-view', view: 'settings' });
    return { success: true, message: '已切到设置页' };
  };

  /** 从设置页返回对话视图；抽屉未开时报错。 */
  A._toolCloseSettings = function () {
    if (!state.drawerIframe) {
      return { success: false, error: 'DRAWER_NOT_OPEN', message: '抽屉未打开' };
    }
    A.postToDrawer({ type: 'ai-debug-set-view', view: 'chat' });
    return { success: true, message: '已返回对话' };
  };

  A.handleToolRequest = async function (detail) {
    const fn = A.TOOL_HANDLERS[detail.tool];
    if (!fn) return { success: false, error: 'UNKNOWN_TOOL', tool: detail.tool };
    return await fn(detail.params || {});
  };

  /** 工具 get_element_style：采集元素样式（顶层直接查，子页面交给点选补丁代答）。 */
  A._toolGetElementStyle = function (params) {
    const selector = params.selector;
    // 该工具的职责就是采集样式，故默认强制采集（不再受「采集样式列表」全局开关限制）；
    // 允许用 properties 精确指定要看的属性，或 include_all=true 取全量。
    const properties = Array.isArray(params.properties) ? params.properties : null;
    const includeAll = params.include_all === true;
    const styleFilter = includeAll ? null : (properties || A.DEFAULT_STYLE_PROPS);
    // 顶层文档直接查询
    const queryTop = () => {
      const matches = selector ? document.querySelectorAll(selector) : null;
      if (!matches || matches.length === 0) {
        return { success: false, error: 'ELEMENT_NOT_FOUND', selector, frames: A.frameUrls() };
      }
      if (matches.length > 1) {
        return { success: false, error: 'ELEMENT_NOT_UNIQUE', selector, count: matches.length };
      }
      return { success: true, data: A.buildElementData(matches[0], A.generateSelector(matches[0]), true, styleFilter) };
    };
    // 子页面：交给点选补丁代答
    const queryFrame = async (frame) => {
      try {
        const res = await A.queryFrame(frame, {
          type: 'query-element', selector: selector, wantStyle: true,
          includeAll: includeAll, properties: properties,
        }, 4000);
        return res.result;
      } catch (e) {
        return {
          success: false,
          error: e.message || 'FRAME_QUERY_FAILED',
          selector,
          page_url: params.page_url || '',
          hint: '目标页面内需已安装「iframe 点选补丁」才能查询子页面元素。请在调试抽屉设置页复制补丁，'
            + '并粘贴到该 iframe 的控制台执行，然后请用户确认后重试。'
        };
      }
    };
    return runInTargetPage(params, queryTop, queryFrame);
  };

  /** 工具 get_page_snapshot：只做可见区域截图，链路与 QQ 指令「/sp」一致。 */
  A._toolSnapshot = async function () {
    // 后台 captureVisibleTab 直接取图，回传原图，不做缩放、不读 DOM。
    // 读整页 outerHTML 会把大段字符串经回传链路搬运、在卡片里渲染，页面一大就卡。
    try {
      const shot = await A.requestScreenshot();
      return { success: true, data: { screenshot: shot } };
    } catch (err) {
      return { success: false, error: 'SNAPSHOT_FAILED', message: err.message };
    }
  };

  /** 工具 get_console_logs：读取主世界脚本 hook 捕获的 console 记录。 */
  A._toolConsoleLogs = async function (params) {
    const limit = typeof params.limit === 'number' ? params.limit : 500;
    const level = params.level || '';
    // exec_js 的代码由 async 函数包裹，必须以 return 交出结果；写成自执行函数会返回 undefined
    const res = await A.execJs('return (window.__AI_DEBUG_CONSOLE_LOGS || []);');
    if (!res || !res.success) return { success: false, error: (res && res.error) || 'EXEC_JS_ERROR' };
    let logs = Array.isArray(res.result) ? res.result : [];
    if (level) logs = logs.filter((x) => x && x.level === level);   // 按级别过滤
    logs = logs.slice(-limit);                                      // 只取最近 limit 条
    return { success: true, data: { count: logs.length, logs: logs } };
  };

  /** 工具 get_network_logs：读取 DevTools 采集、service worker 缓存的网络记录。 */
  A._toolNetworkLogs = function (params) {
    const limit = typeof params.limit === 'number' ? params.limit : 300;
    // 需该页 DevTools 打开过，否则缓存为空
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: 'get-devtools-network', limit: limit }, (resp) => {
          if (!resp || !resp.ok) {
            resolve({ success: false, error: 'NETWORK_UNAVAILABLE', hint: '请先在该页面打开 DevTools 面板，网络记录才会被采集。' });
            return;
          }
          resolve({ success: true, data: { count: (resp.entries || []).length, entries: resp.entries || [] } });
        });
      } catch (e) {
        resolve({ success: false, error: String(e) });
      }
    });
  };

  /** 工具 exec_js：在目标页面主世界执行任意 JS（当前仅支持顶层文档）。 */
  A._toolExecJs = async function (params) {
    const code = params.code;
    if (typeof code !== 'string' || code.trim() === '') {
      return { success: false, error: 'MISSING_CODE', hint: 'exec_js 需要非空的 code 参数。' };
    }
    const url = params.page_url || '';
    if (url && A.normalizeUrl(url) !== A.normalizeUrl(location.href)) {
      // 与 FRAME_NOT_FOUND 保持一致：带 available 列出所有可路由文档，调用方据此改用顶层地址重试
      return {
        success: false, error: 'EXEC_JS_TOP_ONLY', page_url: url, available: A.frameUrls(),
        hint: 'exec_js 目前仅支持顶层文档主世界；请传入顶层页面的 URL（见 available 列表）。',
      };
    }
    return await A.execJs(code);
  };

  /** 工具 push_message：把一段文字推送到调试抽屉。 */
  A._toolPushMessage = function (params) {
    // 参数名为 message；为空时显式报错，避免推送空内容后仍返回成功（静默失败）。
    const message = params.message;
    const title = params.title || '';
    if (typeof message !== 'string' || message.trim() === '') {
      return { success: false, error: 'MISSING_MESSAGE', hint: 'push_message 需要非空的 message 参数（推送正文）。' };
    }
    A.postToDrawer({
      type: 'append-reply',
      id: A.generateId ? A.generateId() : String(Date.now()),
      text: (title ? ('【' + title + '】') : '') + message,
      timestamp: Date.now()
    });
    return { success: true, data: { pushed: true } };
  };

  // exec_js 的等待上限（毫秒）：主世界执行可能陷入长循环或死等，
  // 必须有超时兜底，否则会卡住整个轮询循环。
  A.EXEC_JS_TIMEOUT_MS = 15000;

  /**
   * 在页面主世界执行一段 JS，返回 { success, result } 或 { success:false, error }。
   *
   * 为什么要绕主世界：内容脚本运行在隔离世界，读到的 window / document / localStorage
   * 是隔离副本，看不到页面真实内存。主世界脚本（08_injected_main.js）持有真实引用，
   * 由它执行代码、把结果序列化后回传。
   * @param {string} code 待执行代码（可含 await）
   * @returns {Promise<Object>} 执行结果
   */
  A.execJs = function (code) {
    return new Promise((resolve) => {
      const reqId = 'exec-' + Date.now() + '-' + Math.floor(Math.random() * 1e6);
      let done = false;
      const finish = (payload) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        window.removeEventListener('message', listener);
        resolve(payload);
      };
      const listener = (ev) => {
        const d = ev.data;
        if (!d || d.source !== 'ai-debug-main' || d.type !== 'exec-js-result' || d.reqId !== reqId) return;
        if (d.success) finish({ success: true, result: d.result });
        else finish({ success: false, error: d.error || 'EXEC_JS_ERROR' });
      };
      const timer = setTimeout(() => finish({ success: false, error: 'EXEC_JS_TIMEOUT' }), A.EXEC_JS_TIMEOUT_MS);
      window.addEventListener('message', listener);
      // 投递给主世界脚本：内容脚本与主世界同窗口，用 postMessage 通信
      window.postMessage({ source: 'ai-debug-content', type: 'exec-js', reqId: reqId, code: code }, '*');
    });
  };

  // 截图请求的超时上限（毫秒）：后台若因 service worker 休眠、截图失败丢响应
  // 等原因不回传结果，必须自行超时退出，否则等待方会永久挂起，
  // 进而卡死整个轮询循环（见 03_heartbeat.js 的 state.polling 守卫）。
  A.SCREENSHOT_TIMEOUT_MS = 5000;

  A.requestScreenshot = function () {
    return new Promise((resolve, reject) => {
      let done = false;
      const finish = (fn, arg) => {
        if (done) return;
        done = true;
        clearTimeout(timer);
        fn(arg);
      };
      // 超时兜底：后台若因 service worker 休眠等原因不回，回调不会触发，
      // 必须自行超时退出，否则等待方永久挂起、卡死轮询循环。
      const timer = setTimeout(() => finish(reject, new Error('SNAPSHOT_TIMEOUT')), A.SCREENSHOT_TIMEOUT_MS);
      // 关键：后台用 sendResponse 回复，响应只会进 sendMessage 的回调参数，
      // 不会作为一条独立消息触发 onMessage。故这里必须用回调接收，
      // 早先用 onMessage.addListener 等待，永远等不到，必然超时。
      try {
        chrome.runtime.sendMessage({ type: 'capture-visible-tab' }, (resp) => {
          if (chrome.runtime.lastError) {
            finish(reject, new Error(chrome.runtime.lastError.message || 'SEND_FAILED'));
            return;
          }
          if (!resp || !resp.success) {
            finish(reject, new Error((resp && resp.error) || '截图失败'));
            return;
          }
          // 直接用后台返回的原图：不做 canvas 缩放。
          // 缩放需在页面里解码大图再重绘，图大时会长时间占用主线程、
          // 表现为页面卡死；卡片的等比缩放交给显示层用 CSS 完成即可。
          finish(resolve, resp.data.screenshot);
        });
      } catch (e) {
        finish(reject, e);
      }
    });
  };

  A.downscaleImage = function (dataUrl, maxWidth) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        if (!img.width || img.width <= maxWidth) {
          resolve(dataUrl);
          return;
        }
        const canvas = document.createElement('canvas');
        const ratio = maxWidth / img.width;
        canvas.width = maxWidth;
        canvas.height = Math.max(1, Math.round(img.height * ratio));
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', 0.7));
      };
      img.onerror = () => reject(new Error('图片加载失败'));
      img.src = dataUrl;
    });
  };
})();
