// 内容脚本入口：初始化并启动
(function () {
  if (window.__AI_STYLE_DEBUG_INITIALIZED__) return;
  window.__AI_STYLE_DEBUG_INITIALIZED__ = true;

  const A = window.AIStyleDebug;

  /**
   * 向页面主世界注入脚本，暴露 window.selectAiDebugElement(el)。
   * 内容脚本运行在隔离世界，直接写 window 主世界看不到，必须用 <script> 注入；
   * 脚本列为 web_accessible_resources，可被页面通过 chrome-extension:// 加载。
   * 注入后立即移除 <script> 标签，避免在页面留下痕迹。
   */
  (function injectMainWorld() {
    try {
      const s = document.createElement('script');
      s.src = chrome.runtime.getURL('content/08_injected_main.js');
      s.onload = function () { s.remove(); };
      (document.head || document.documentElement).appendChild(s);
    } catch (e) {
      console.warn('[AI Style Debug] 主世界脚本注入失败', e);
    }
  })();

  // 只注册与「开关抽屉」「与抽屉通信」相关的常驻监听；
  // 主题监听与页面级交互监听不在这里绑定——它们随抽屉开关
  // attach / detach（见 02_drawer.js），抽屉关闭后页面上不留任何活动代码。
  A.initEventListeners();

  A.loadConfig().then(() => {
    chrome.storage.onChanged.addListener(() => A.loadConfig());
  });
})();
