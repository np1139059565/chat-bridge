// 后台脚本：截图、标签页 ID 获取、点击图标切换抽屉
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

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const { type } = message || {};
  if (type === 'capture-visible-tab') {
    handleCaptureScreenshot(sender, sendResponse);
    return true;
  }
  if (type === 'get-tab-id') {
    sendResponse({ tabId: sender.tab ? sender.tab.id : null });
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
