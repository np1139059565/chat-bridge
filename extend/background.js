// 后台服务：点击工具栏图标时切换悬浮对话框的显隐
chrome.action.onClicked.addListener((tab) => {
  if (!tab.id) return;
  chrome.tabs.sendMessage(tab.id, { type: 'toggle_dialog' }).catch(() => {});
});
