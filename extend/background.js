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
