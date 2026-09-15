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
  // silent 工具（如 push_message）：仅执行动作本身，不生成卡片、不回传结果。
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
    if (silent) return;   // 副作用工具：无需回传结果
    await A.postResult(task.request_id, outcome);
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
  async function runInTargetPage(params, fnTop, fnFrame) {
    const url = params.page_url || params.pageUrl || '';
    if (url) {
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
      const snapshotType = params.snapshot_type || 'dom';
      if (snapshotType === 'dom') {
        const snapTop = () => ({ success: true, data: { dom: A.truncate(document.documentElement.outerHTML, A.MAX_SNAPSHOT_CHARS) } });
        const snapFrame = async (frame) => {
          try {
            const res = await A.queryFrame(frame, { type: 'query-dom' }, 4000);
            return res.result;
          } catch (e) {
            return { success: false, error: e.message || 'FRAME_QUERY_FAILED', hint: '目标页面内需已安装「iframe 点选补丁」。' };
          }
        };
        return runInTargetPage(params, snapTop, snapFrame);
      }
      if (snapshotType === 'screenshot') {
        try {
          const shot = await A.requestScreenshot();
          return { success: true, data: { screenshot: shot } };
        } catch (err) {
          return { success: false, error: 'SNAPSHOT_FAILED', message: err.message };
        }
      }
      return { success: false, error: 'INVALID_SNAPSHOT_TYPE' };
    }

    if (tool === 'push_message') {
      const text = params.text || '';
      const title = params.title || '';
      A.postToDrawer({ type: 'append-reply', id: A.generateId ? A.generateId() : String(Date.now()), text: (title ? ('【' + title + '】') : '') + text, timestamp: Date.now() });
      return { success: true, data: { pushed: true } };
    }

    return { success: false, error: 'UNKNOWN_TOOL', tool };
  };

  A.requestScreenshot = function () {
    return new Promise((resolve, reject) => {
      const listener = (msg) => {
        if (!msg || msg.type !== 'screenshot-result') return;
        chrome.runtime.onMessage.removeListener(listener);
        if (msg.success) {
          resolve(A.downscaleImage(msg.data.screenshot, A.MAX_SHOT_WIDTH));
        } else {
          reject(new Error(msg.error || '截图失败'));
        }
      };
      chrome.runtime.onMessage.addListener(listener);
      chrome.runtime.sendMessage({ type: 'capture-visible-tab' });
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
