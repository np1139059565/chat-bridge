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

  // 待命轮询：页面加载后即常驻运行，抽屉关闭时也不停。
  // 目的：抽屉关闭时仍能收到「唤醒类」命令（如 open_drawer），
  // 否则「打开抽屉」需要一个已打开的抽屉来接，形成死锁。
  // 上报的 is_open 由抽屉是否存在自动判定（见 doHeartbeat）。
  A.startPolling();

  /**
   * 检查镜像侧留下的「刷新后自动开抽屉」标记。
   * 镜像扩展在执行 /rf（刷新页面）时会把 sessionStorage.aiDebugAutoOpen 置 1，
   * 然后刷新；刷新后本扩展内容脚本重新注入，在此读该标记自动打开抽屉，
   * 读完立即删除，保证只对本次刷新生效，不会长期驻留。
   * sessionStorage 按页面源共享，两个扩展的内容脚本读的是同一份。
   */
  (function checkAutoOpen() {
    let flag = null;
    try { flag = sessionStorage.getItem('aiDebugAutoOpen'); } catch (e) { return; }
    if (!flag) return;
    try { sessionStorage.removeItem('aiDebugAutoOpen'); } catch (e) { /* 忽略 */ }
    A.openDrawer();
  })();
})();
