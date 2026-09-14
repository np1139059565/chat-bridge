// 命令轮询调度与在线状态
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  A.scheduleNext = function (delay) {
    if (state.pollTimer) clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(A.tick, delay);
  };

  // 每次心跳即一次命令轮询；抽屉未展开或页面非活动时不轮询
  A.tick = async function () {
    if (!state.drawerOpen || !A.isActivePage()) {
      A.scheduleNext(state.pollIntervalMs);
      return;
    }
    try {
      const commands = await A.doHeartbeat();
      state.pollFailCount = 0;
      A.setConnected(true);
      for (const cmd of commands) {
        await A.handleTask(cmd);
      }
      A.scheduleNext(state.pollIntervalMs);
    } catch (err) {
      state.pollFailCount += 1;
      A.setConnected(false);
      A.scheduleNext(state.pollIntervalMs);
    }
  };

  // 调用工具服务的提供方通道：poll 取命令（兼作心跳）
  A.doHeartbeat = async function () {
    const id = await A.getTabId();
    if (id == null) throw new Error('NO_TAB_ID');
    const res = await fetch(`${state.backendUrl}/api/ext/${A.PROVIDER}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'poll', tab_id: id, page_url: location.href }),
    });
    if (!res.ok) throw new Error('POLL_FAILED');
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'POLL_FAILED');
    return data.commands || [];
  };
})();
