// 后台服务：
// 1. 点击工具栏图标时切换悬浮对话框的显隐
// 2. 远程桥接的截屏请求：captureVisibleTab 只能在后台调用，
//    内容脚本收到请求后转发到此处，抓取当前可见标签页。
chrome.action.onClicked.addListener((tab) => {
  if (!tab.id) return;
  chrome.tabs.sendMessage(tab.id, { type: 'toggle_dialog' }).catch(() => {});
});

// 截屏请求：来自内容脚本，抓取当前窗口可见区域后原样回传 dataURL
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
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
