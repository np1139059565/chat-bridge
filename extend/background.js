// 后台服务：
// 1. 点击工具栏图标时切换悬浮对话框的显隐
// 2. 远程桥接的截屏请求：captureVisibleTab 只能在后台调用，
//    内容脚本收到请求后转发到此处，抓取当前可见标签页。
// 3. 转发内容脚本的诊断日志到本地工具服务。
//
//    为什么必须由后台转发：内容脚本跑在网页的源里（如 https://chat.deepseek.com），
//    而工具服务是 http://127.0.0.1:5000。HTTPS 页面请求 HTTP 接口会被浏览器
//    的混合内容策略直接拦截，请求根本发不出去——这正是「工具接口能通、
//    日志接口不通」的原因：工具请求由抽屉（chrome-extension:// 页面）发出，
//    不受该策略限制。后台 service worker 运行在扩展上下文，同样不受限制。
chrome.action.onClicked.addListener((tab) => {
  if (!tab.id) return;
  chrome.tabs.sendMessage(tab.id, { type: 'toggle_dialog' }).catch(() => {});
});

// 截屏请求：来自内容脚本，抓取当前窗口可见区域后原样回传 dataURL
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // 转发内容脚本的诊断日志：内容脚本受混合内容策略限制发不出 HTTP 请求，
  // 交由后台转发（见文件头说明）。不关心结果，失败直接丢弃。
  // 兜底转发：本页没有抽屉时，内容脚本的日志走这里。
  // 后台运行在扩展上下文，不受混合内容策略限制。
  // 必须返回 true 保持通道，直到 fetch 完成——MV3 的 worker 没待处理事件会被回收，
  // 直接 return 会让请求半路中断。
  if (msg && msg.type === 'ext_remote_log') {
    /**
     * 拿到后端地址后转发。
     *
     * 地址优先取存储里的 aiMirrorFlaskUrl（抽屉探测后写入），
     * 取不到才用默认值——端口可能被用户改过，硬编码会打错地方。
     *
     * @param {string} saved 存储里的地址，可为空
     */
    const send = function (saved) {
      const base = (msg.baseUrl || saved || 'http://127.0.0.1:5000').replace(/\/+$/, '');
      fetch(base + '/api/web/client_log', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(msg.body || [])
      }).then(function (r) {
        sendResponse({ ok: r.ok });
      }).catch(function (e) {
        sendResponse({ ok: false, error: String((e && e.message) || e) });
      });
    };
    try {
      chrome.storage.local.get(['aiMirrorFlaskUrl'], function (r) {
        send((r && r.aiMirrorFlaskUrl) || '');
      });
    } catch (e) {
      send('');
    }
    return true;   // 保持通道
  }
  // 站点档案拉取中转：内容脚本跑在网页源里（多为 HTTPS），直连本地
  // http://127.0.0.1:5000 会被混合内容策略拦截；后台运行在扩展上下文不受限。
  // 档案真源在后端配置文件（GET /profiles 轻量接口），前端零缓存：回传后由
  // 内容脚本进内存即用，不落任何存储。
  if (msg && msg.type === 'profiles_fetch') {
    /**
     * 拿到后端地址后转发（与日志转发同模式：优先存储里抽屉探测到的实际
     * 可连通地址，取不到用默认值，避免端口被改后打错地方）。
     * @param {string} saved 存储里的地址，可为空
     */
    const fetchProfiles = function (saved) {
      const base = (saved || 'http://127.0.0.1:5000').replace(/\/+$/ , '');
      fetch(base + '/profiles', { headers: { 'Accept': 'application/json' } })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function (data) {
          sendResponse({ ok: true, profiles: (data && data.profiles) || {} });
        })
        .catch(function (e) {
          sendResponse({ ok: false, error: String((e && e.message) || e) });
        });
    };
    try {
      chrome.storage.local.get(['aiMirrorFlaskUrl'], function (r) {
        fetchProfiles((r && r.aiMirrorFlaskUrl) || '');
      });
    } catch (e) {
      fetchProfiles('');
    }
    return true;   // 异步回包：保持消息通道开启
  }
  if (!msg || msg.type !== 'bridge_capture_tab') return;
  // windowId 取发送方所在窗口，保证抓到的是用户正在看的那个窗口
  const windowId = sender.tab ? sender.tab.windowId : undefined;
  chrome.tabs.captureVisibleTab(windowId, { format: 'png' }, (dataUrl) => {
    if (chrome.runtime.lastError) {
      sendResponse({ ok: false, error: chrome.runtime.lastError.message });
      return;
    }
    sendResponse({ ok: true, dataUrl: dataUrl || '' });
  });
  // 异步回包：返回 true 保持消息通道开启
  return true;
});
