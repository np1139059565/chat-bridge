// 命令轮询调度与在线状态
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  A.scheduleNext = function (delay) {
    if (state.pollTimer) clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(A.tick, delay);
  };

  /**
   * 启动命令轮询：抽屉存在期间才轮询取命令。
   * 幂等，重复调用不会叠加定时器。
   */
  A.startPolling = function () {
    state.pollingEnabled = true;
    A.tick();
  };

  /**
   * 停止命令轮询：清掉待触发的定时器并关闭轮询开关。
   * 关闭后本页面不再取任何命令，属于它的命令会逸散到其他页面。
   */
  A.stopPolling = function () {
    state.pollingEnabled = false;
    if (state.pollTimer) {
      clearTimeout(state.pollTimer);
      state.pollTimer = null;
    }
  };

  // 每次心跳即一次命令轮询，并顺带上报本页面工具（抽屉）是否打开。
  // 轮询只在抽屉存在期间进行：抽屉关闭即停止，命令随即逸散到其他页面。
  // 页面失焦（例如用户转头去看网页 AI）不影响轮询，否则网页 AI 通过
  // push_message 主动推送时会因失焦被判离线而失败。
  /**
   * 计算下一次轮询的间隔：先快后慢。
   * 连接状态刚发生变化后的 30 秒内用快速间隔（1 秒），便于尽快确认状态稳定或恢复；
   * 之后回落到常规间隔（5 秒）。状态不变时始终用常规间隔。
   * @returns {number} 下一次轮询的延迟（毫秒）
   */
  A.nextInterval = function () {
    const since = Date.now() - (state.connectedChangedAt || 0);
    return since < A.FAST_POLL_WINDOW_MS ? A.FAST_POLL_INTERVAL_MS : A.POLL_INTERVAL_MS;
  };

  // 单条命令的处理超时（毫秒）。
  // 某些工具（截图、子页面查询）依赖外部回传，若对方不回，handleTask 会一直 await。
  // 这里加硬超时兜底：超时不代表命令取消，只保证轮询循环不被单条命令永久占住，
  // 后续命令与新轮询仍能继续。
  A.TASK_TIMEOUT_MS = 15000;

  /**
   * 给 Promise 加超时：超时后以 TASK_TIMEOUT 拒绝，避免永久挂起。
   * @param {Promise} p 待包裹的 Promise
   * @param {number} ms 超时毫秒
   * @returns {Promise} 原结果或超时拒绝
   */
  A.withTimeout = function (p, ms) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('TASK_TIMEOUT')), ms);
      Promise.resolve(p).then(
        (v) => { clearTimeout(timer); resolve(v); },
        (e) => { clearTimeout(timer); reject(e); }
      );
    });
  };

  A.tick = async function () {
    // 轮询已被关闭（抽屉已关闭）：不再发请求、不再排下一次。
    // 放在最前面判断，确保关闭后即使有残留的在途收尾也不会重新拉起轮询。
    if (!state.pollingEnabled) return;
    // 同一时刻只允许一次轮询在途：手动触发（发送后立即刷新）可能与定时轮询撞车，
    // 两次并发会重复取命令、重复安排定时器。已在途则直接返回，由在途那次收尾。
    if (state.polling) return;
    state.polling = true;
    const interval = A.nextInterval();
    // 用 try/finally 保证无论中途发生什么（含命令永久挂起被超时打断），
    // state.polling 一定被复位并安排下一次轮询。否则一旦某条命令卡住，
    // 守卫会让之后所有轮询都在开头 return，整个扩展永久停止工作。
    try {
      const commands = await A.doHeartbeat();
      state.pollFailCount = 0;
      A.setConnected(true);
      // 只在真的取到命令时打日志：轮询每 5 秒一次，逐次打印会淹没控制台。
      // 收到命令说明本页面被后端判定为「工具打开且是目标页面」，
      // 若本该由本页面执行的命令却始终不出现，看这里即可定位。
      if (commands.length) {
        A.log('取到命令 ' + commands.length + ' 条：',
          commands.map((c) => (c.tool || '') + '@' + (c.request_id || '')).join(', '));
      }
      // 命令处理单独兜底：某条命令执行失败不应牵连连接状态。
      // 处理过程在取命令之后，与「能否连通服务」无关，一条命令报错就把
      // 整体判为离线会误导用户（接口明明正常）。
      for (const cmd of commands) {
        try {
          await A.withTimeout(A.handleTask(cmd), A.TASK_TIMEOUT_MS);
        } catch (err) {
          console.error('[AI-Style-Debug] 命令处理失败：', err);
        }
      }
    } catch (err) {
      state.pollFailCount += 1;
      // 连续失败达到阈值才判定离线：单次失败可能来自瞬时抖动或页面切换，
      // 立刻翻状态会让界面频繁闪断。未达阈值时保持上一次的连接状态。
      if (state.pollFailCount >= A.POLL_FAIL_THRESHOLD) {
        A.setConnected(false);
      }
    } finally {
      state.polling = false;
      // 仅当轮询仍开启时才排下一次；关闭后到此为止，不再自续。
      if (state.pollingEnabled) A.scheduleNext(interval);
    }
  };

  // 轮询请求的超时上限（毫秒）：后端若假死 / 网络层卡住，fetch 可能长时间不返回，
  // 若不设超时，await 会永久挂起，导致 state.polling 永远无法复位（死锁）。
  A.POLL_TIMEOUT_MS = 10000;

  // 调用工具服务的提供方通道：poll 取命令（兼作心跳）
  // isOpen：本页面工具（抽屉）是否打开。后端据此判断「目标页面能否消费命令」，
  // 目标页面工具没打开时，属于它的命令立即逸散到其他页面。
  // @param {boolean} isOpen 工具是否打开；省略时按当前抽屉是否存在判断
  A.doHeartbeat = async function (isOpen) {
    const id = await A.getTabId();
    if (id == null) throw new Error('NO_TAB_ID');
    const open = (typeof isOpen === 'boolean') ? isOpen : !!state.drawerIframe;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), A.POLL_TIMEOUT_MS);
    try {
      const res = await fetch(`${state.backendUrl}/api/ext/${A.PROVIDER}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'poll', tab_id: id, page_url: location.href, is_open: open }),
        signal: ctrl.signal,
      });
      if (!res.ok) throw new Error('POLL_FAILED');
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'POLL_FAILED');
      return data.commands || [];
    } finally {
      clearTimeout(timer);
    }
  };

  /**
   * 上报一次「工具已关闭」，让后端立即注销本页面的打开登记。
   * 关闭抽屉时调用：不取命令（is_open=false），只把状态同步给后端，
   * 这样属于本页面的命令无需等僵尸登记超期，立刻就能逸散到其他页面。
   */
  A.reportClosed = function () {
    A.log('上报「工具已关闭」，注销本页面的接单登记');
    A.doHeartbeat(false).catch(() => { /* 后端不可达时忽略：僵尸登记会由超期机制清理 */ });
  };
})();
