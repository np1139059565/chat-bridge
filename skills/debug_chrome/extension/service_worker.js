// 后台脚本：截图、标签页 ID 获取、点击图标切换抽屉
// 后端地址默认值：与抽屉设置页输入框默认值一致，用户可手动修改。
// 保留默认值，避免每次都要重新输入；代码别处不再写死端口。
const DEFAULT_BACKEND_URL = 'http://127.0.0.1:5000';

async function getBackendUrl() {
  const stored = await chrome.storage.local.get(['backendUrl', 'aistyleCfg']);
  return stored.backendUrl || (stored.aistyleCfg && stored.aistyleCfg.backend_url) || DEFAULT_BACKEND_URL;
}

async function handleCaptureScreenshot(sender, sendResponse) {
  try {
    const tab = sender.tab;
    if (!tab || tab.id === undefined) {
      sendResponse({ type: 'screenshot-result', success: false, error: 'NO_TAB_CONTEXT' });
      return;
    }
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 70 });
    sendResponse({ type: 'screenshot-result', success: true, data: { screenshot: dataUrl } });
  } catch (err) {
    sendResponse({ type: 'screenshot-result', success: false, error: 'SNAPSHOT_FAILED', message: err.message });
  }
}

// ============ DevTools 网络记录缓存 ============
// devtools.js 实时上报网络记录，这里按 tabId 归类缓存，供内容脚本查询。
// 用内存变量存储：DevTools 打开期间频繁有消息往来，service worker 通常保持活跃。
// 记录上限与 devtools.js 的环形缓冲一致，防止内存无界增长。
const NET_MAX = 300;
const netStore = {};   // tabId -> [entry, ...]

function appendNetwork(tabId, entry) {
  if (tabId === undefined || tabId === null || !entry) return;
  const list = netStore[tabId] || (netStore[tabId] = []);
  list.push(entry);
  if (list.length > NET_MAX) list.splice(0, list.length - NET_MAX);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const { type } = message || {};
  // 代理请求：content script 运行在页面源下，从公网页面访问 127.0.0.1 会被
  // Chrome 的 Private Network Access 拦截（Permission denied for loopback）。
  // service worker 是扩展源，不受此限制，故由它代发并回传结果。
  if (type === 'proxy-fetch') {
    (async () => {
      try {
        const resp = await fetch(message.url, {
          method: message.method || 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: message.body ? JSON.stringify(message.body) : undefined
        });
        const data = await resp.json();
        sendResponse({ ok: true, data: data });
      } catch (e) {
        sendResponse({ ok: false, error: String(e) });
      }
    })();
    return true;
  }
  if (type === 'capture-visible-tab') {
    handleCaptureScreenshot(sender, sendResponse);
    return true;
  }
  if (type === 'get-tab-id') {
    sendResponse({ tabId: sender.tab ? sender.tab.id : null });
    return true;
  }
  // devtools.js 上报一条网络记录
  if (type === 'devtools-network-record') {
    appendNetwork(message.tabId, message.entry);
    sendResponse({ ok: true });
    return true;
  }
  // 页面导航：清空该标签页旧记录
  if (type === 'devtools-network-clear') {
    if (message.tabId !== undefined) delete netStore[message.tabId];
    sendResponse({ ok: true });
    return true;
  }
  // 内容脚本查询本标签页的网络记录
  if (type === 'get-devtools-network') {
    const tabId = sender.tab ? sender.tab.id : null;
    const list = (tabId !== null && netStore[tabId]) ? netStore[tabId] : [];
    const limit = typeof message.limit === 'number' ? message.limit : list.length;
    sendResponse({ ok: true, entries: list.slice(-limit) });
    return true;
  }
  sendResponse({ error: 'UNKNOWN_MESSAGE_TYPE' });
  return true;
});

// 点击插件图标：切换右侧抽屉
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab || tab.id === undefined) return;
  try {
    await chrome.tabs.sendMessage(tab.id, { type: 'ai-debug-toggle-from-action' });
  } catch (e) {}
});
