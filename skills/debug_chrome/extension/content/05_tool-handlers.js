// 工具命令处理与结果回传
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  // 经提供方通道回传某次工具调用的结果
  A.postResult = async function (requestId, result) {
    try {
      await fetch(`${state.backendUrl}/api/ext/${A.PROVIDER}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'result', request_id: requestId, result }),
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

  A.handleToolRequest = async function (detail) {
    const tool = detail.tool;
    const params = detail.params || {};

    if (tool === 'get_element_style') {
      const selector = params.selector;
      // 该工具的职责就是采集样式，故默认强制采集（不再受「采集样式列表」全局开关限制）；
      // 允许用 properties 精确指定要看的属性，或 include_all=true 取全量。
      const properties = Array.isArray(params.properties) ? params.properties : null;
      const includeAll = params.include_all === true;
      const wantStyle = true;
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
            type: 'query-element',
            selector: selector,
            wantStyle: wantStyle,
            includeAll: includeAll,
            properties: properties,
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
    }

    if (tool === 'get_page_snapshot') {
      // 只做可见区域截图，链路与 QQ 指令「/sp」一致：
      // 后台 captureVisibleTab 直接取图，回传原图，不做缩放、不读 DOM。
      // 读整页 outerHTML 会把大段字符串经回传链路搬运、在卡片里渲染，
      // 页面一大就卡；截图链路短、开销小，保留它。
      try {
        const shot = await A.requestScreenshot();
        return { success: true, data: { screenshot: shot } };
      } catch (err) {
        return { success: false, error: 'SNAPSHOT_FAILED', message: err.message };
      }
    }

    if (tool === 'get_console_logs') {
      // console 记录由主世界脚本 hook 捕获，存在页面内存里，
      // 这里用 exec_js 通道把它读回来。
      const limit = typeof params.limit === 'number' ? params.limit : 500;
      const level = params.level || '';
      const code = '(function(){'
        + 'var logs = window.__AI_DEBUG_CONSOLE_LOGS || [];'
        + 'return logs;'
        + '})()';
      const res = await A.execJs(code);
      if (!res || !res.success) return { success: false, error: (res && res.error) || 'EXEC_JS_ERROR' };
      let logs = Array.isArray(res.result) ? res.result : [];
      // 按级别过滤（level 为空则全部）
      if (level) logs = logs.filter((x) => x && x.level === level);
      // 只取最近 limit 条
      logs = logs.slice(-limit);
      return { success: true, data: { count: logs.length, logs: logs } };
    }

    if (tool === 'get_network_logs') {
      // 网络记录由 devtools.js 采集、service_worker 缓存。
      // 需该页 DevTools 打开过，否则缓存为空。
      const limit = typeof params.limit === 'number' ? params.limit : 300;
      return await new Promise((resolve) => {
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
    }

    if (tool === 'exec_js') {
      // 在目标页面主世界执行任意 JS。
      // 主世界脚本（08_injected_main.js）只注入顶层文档，
      // 因此目前仅支持顶层页面；子页面（iframe）暂不路由。
      const code = params.code;
      if (typeof code !== 'string' || code.trim() === '') {
        return { success: false, error: 'MISSING_CODE', hint: 'exec_js 需要非空的 code 参数。' };
      }
      const url = params.page_url || '';
      if (url && A.normalizeUrl(url) !== A.normalizeUrl(location.href)) {
        return {
          success: false,
          error: 'EXEC_JS_TOP_ONLY',
          page_url: url,
          hint: 'exec_js 目前仅支持顶层文档主世界；请传入顶层页面的 URL。',
        };
      }
      return await A.execJs(code);
    }

    if (tool === 'push_message') {
      // 参数名为 message；为空时显式报错，避免推送空内容后仍返回成功（静默失败）。
      const message = params.message;
      const title = params.title || '';
      if (typeof message !== 'string' || message.trim() === '') {
        return { success: false, error: 'MISSING_MESSAGE', hint: 'push_message 需要非空的 message 参数（推送正文）。' };
      }
      A.postToDrawer({ type: 'append-reply', id: A.generateId ? A.generateId() : String(Date.now()), text: (title ? ('【' + title + '】') : '') + message, timestamp: Date.now() });
      return { success: true, data: { pushed: true } };
    }

    return { success: false, error: 'UNKNOWN_TOOL', tool };
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
        chrome.runtime.onMessage.removeListener(listener);
        fn(arg);
      };
      const listener = (msg) => {
        if (!msg || msg.type !== 'screenshot-result') return;
        if (msg.success) {
          // 直接用后台返回的原图：不做 canvas 缩放。
          // 缩放需在页面里解码大图再重绘，图大时会长时间占用主线程、
          // 表现为页面卡死；卡片的等比缩放交给显示层用 CSS 完成即可。
          finish(resolve, msg.data.screenshot);
        } else {
          finish(reject, new Error(msg.error || '截图失败'));
        }
      };
      const timer = setTimeout(() => finish(reject, new Error('SNAPSHOT_TIMEOUT')), A.SCREENSHOT_TIMEOUT_MS);
      chrome.runtime.onMessage.addListener(listener);
      try {
        chrome.runtime.sendMessage({ type: 'capture-visible-tab' });
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
