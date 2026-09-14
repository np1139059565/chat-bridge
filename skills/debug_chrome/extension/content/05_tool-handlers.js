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

  A.handleToolRequest = async function (detail) {
    const tool = detail.tool;
    const params = detail.params || {};

    if (tool === 'get_element_style') {
      const selector = params.selector;
      const matches = selector ? document.querySelectorAll(selector) : null;
      if (!matches || matches.length === 0) {
        return { success: false, error: 'ELEMENT_NOT_FOUND', selector };
      }
      if (matches.length > 1) {
        return { success: false, error: 'ELEMENT_NOT_UNIQUE', selector, count: matches.length };
      }
      return { success: true, data: A.buildElementData(matches[0], A.generateSelector(matches[0])) };
    }

    if (tool === 'get_page_snapshot') {
      const snapshotType = params.snapshot_type || 'dom';
      if (snapshotType === 'dom') {
        return { success: true, data: { dom: A.truncate(document.documentElement.outerHTML, A.MAX_SNAPSHOT_CHARS) } };
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
      A.showToast('收到推送：' + (title || text).slice(0, 40));
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
