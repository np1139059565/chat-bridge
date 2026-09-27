// 模块：extend/content/injected_clipboard.js
// 运行世界：MAIN（页面主世界）
// 用途：hook navigator.clipboard.writeText，截获页面自身写入剪贴板的内容。
//
// 为什么需要它：
//  - 内容脚本运行在隔离世界，patch 不到页面主世界的 navigator.clipboard；
//  - 主世界脚本无法直接用 chrome.* 通信，因此用 window.postMessage 把内容
//    回传给内容脚本（06_picker.js 负责接收）。
//  - 相比直接读剪贴板，hook 不依赖页面聚焦——用户离开电脑、页面在后台时，
//    readText 会失败，而 writeText 的截获照常工作。
(function () {
  'use strict';
  try {
    const clip = navigator.clipboard;
    if (!clip || typeof clip.writeText !== 'function') return;
    const orig = clip.writeText.bind(clip);
    clip.writeText = function (text) {
      // 把页面写入的内容原样回传；不阻断原行为，页面复制照常生效
      try {
        window.postMessage({
          source: 'ai-mirror-clip',
          type: 'copied',
          text: String(text == null ? '' : text)
        }, '*');
      } catch (e) { /* 忽略 */ }
      return orig(text);
    };
  } catch (e) { /* 环境不支持则静默退出 */ }
})();
