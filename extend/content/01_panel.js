// 模块：extend/content/01_panel.js
// 用途：悬浮对话框 iframe 的注入、定位、显隐，以及站点配置读取。
// 依赖：content/00_state.js（命名空间 A）、lib/dom-utils.js
(function () {
  'use strict';
  const A = window.AIMirrorContent;

  /**
   * 读取当前站点配置并回调。
   * 站点规则按 hostname 自动识别（无需浏览器存储配置，配置统一由后端配置文件管理）。
   * 容器选择器完全由预设规则决定——之前暴露的「自定义 class 选择器」无法稳定工作
   * （各站 class 含易变哈希），已撤销。
   * @param {Function} cb 回调，入参 { profile, container, profileLabel }
   */
  A.getConfig = function (cb) {
    A.state.siteKey = A.currentHost() || 'unknown-site';
    A.state.profileId = A.guessProfile(A.state.siteKey);
    const prof = A.PROFILES[A.state.profileId] || A.PROFILES.glm;
    cb({ profile: A.state.profileId, container: prof.container, profileLabel: prof.label });
  };

  /**
   * 计算面板定位样式。
   * 右侧挂靠 right:0，左侧挂靠 left:0；圆角与投影方向随挂靠侧翻转。
   * @returns {string} 可直接赋给 style.cssText 的样式串
   */
  /**
   * 当前生效的面板底色：按宿主页面明暗主题择一。
   * 面板底色由外框样式给出（iframe 内部读不到），必须与主题判断保持一致，
   * 否则暗色宿主下会露出亮色底边。
   * @returns {string} 颜色值
   */
  A.panelBg = function () {
    return A.state.theme === 'dark' ? A.PANEL_BG_DARK : A.PANEL_BG_LIGHT;
  };

  A.panelPositionCss = function () {
    if (A.state.panelSide === 'left') {
      return 'position:fixed;top:0;left:0;width:' + A.panelWidth() +
        ';height:100vh;border:0;border-radius:' + A.PANEL_RADIUS_LEFT +
        ';box-shadow:' + A.PANEL_SHADOW_LEFT +
        ';background:' + A.panelBg() +
        ';z-index:' + A.PANEL_Z + ';';
    }
    return 'position:fixed;top:0;right:0;width:' + A.panelWidth() +
      ';height:100vh;border:0;border-radius:' + A.PANEL_RADIUS_RIGHT +
      ';box-shadow:' + A.PANEL_SHADOW_RIGHT +
      ';background:' + A.panelBg() +
      ';z-index:' + A.PANEL_Z + ';';
  };

  /**
   * 重新判定宿主主题并推送给对话框 iframe。
   * 主题变化时面板外框底色与内部令牌都要跟着变，否则外框与内容会脱节。
   */
  A.postTheme = function () {
    const next = A.detectHostTheme();
    A.state.theme = next;
    // 外框底色同步刷新；iframe 内部由 'host_theme' 消息驱动
    A.applyPanelSide();
    A.post({ type: 'host_theme', theme: next });
  };

  /**
   * 计算面板宽度：宿主窗口过窄时铺满，否则用固定宽度。
   * @returns {string} 宽度值（含单位）
   */
  A.panelWidth = function () {
    return window.innerWidth < A.PANEL_NARROW ? '100%' : A.PANEL_W;
  };

  /**
   * 应用挂靠侧到已有 iframe（切换挂靠侧时调用，无需重建）。
   */
  A.applyPanelSide = function () {
    const f = A.state.iframe || document.getElementById('ai-mirror-iframe');
    if (!f) return;
    // cssText 整体赋值会清掉 display，导致隐藏中的对话框被意外显示。
    // 这里先保存 display，赋完定位样式后再恢复。
    const display = f.style.display;
    f.style.cssText = A.panelPositionCss();
    f.style.display = display;
  };

  /**
   * 注入悬浮对话框 iframe。
   * 会先清理上一轮残留（扩展重导入 / 旧实例未移除），否则 id 守卫会误判“已存在”而跳过注入。
   */
  A.inject = function () {
    const IFRAME_SRC = chrome.runtime.getURL('dialog/dialog.html');
    // 清理上一轮残留的 iframe，避免 id 守卫误判“已存在”而跳过注入
    const old = document.getElementById('ai-mirror-iframe');
    if (old) old.remove();
    const iframe = document.createElement('iframe');
    iframe.id = 'ai-mirror-iframe';
    iframe.src = IFRAME_SRC;
    // 高度必须显式给出，不能用 top/bottom 双向拉伸：iframe 是替换元素，
    // height:auto 会退化成内在高度（默认 150px），此时 top 与 bottom 过度约束，
    // 浏览器会忽略 bottom，面板只剩一条窄带。
    iframe.style.cssText = A.panelPositionCss();
    // 注入即显示：iframe 只在用户打开面板时才创建，创建出来就是可见的。
    // 关闭时不做隐藏而是直接销毁（见 destroyPanel），页面加载时也不再预注入。
    iframe.style.display = '';
    document.body.appendChild(iframe);
    A.state.iframe = iframe;
    // 文档加载完成即推送一次宿主主题，避免对话框首屏用默认主题闪一下。
    // 此时 contentWindow 已可用，消息不会丢失。
    iframe.addEventListener('load', function () { A.postTheme(); });
    // 窗口尺寸变化时重新计算宽度与挂靠方向。
    // 只注册一次并记在 state 上：面板可反复开关，若每次 inject 都新增监听，
    // 监听器会随开关次数不断堆积。移除 iframe 时由 destroy 一并解绑。
    if (!A.state.resizeHandler) {
      A.state.resizeHandler = function () { A.applyPanelSide(); };
      window.addEventListener('resize', A.state.resizeHandler);
    }
  };

  /**
   * 销毁悬浮对话框 iframe：从页面移除并解绑其附带监听。
   * 关闭面板时调用——对话框应用随之销毁，不再拉配置、不再轮询，
   * 保证关闭后没有任何活动代码在后台运行。会话数据在 storage 中，不受影响。
   */
  A.destroyPanel = function () {
    const f = A.state.iframe || document.getElementById('ai-mirror-iframe');
    if (f && f.parentNode) f.parentNode.removeChild(f);
    A.state.iframe = null;
    if (A.state.resizeHandler) {
      window.removeEventListener('resize', A.state.resizeHandler);
      A.state.resizeHandler = null;
    }
  };

  /**
   * 显隐切换：仅作用于当前页面会话，不做持久化。
   * 刷新 / 新开页面一律回到默认关闭状态。
   * @param {boolean} visible 是否显示
   */
  A.setDialogVisible = function (visible) {
    A.state.dialogHidden = !visible;
    if (visible) {
      // 打开：iframe 不存在（首次打开 / 上次关闭时已销毁）则创建。
      // 创建后 Vue 应用才会启动、开始拉配置与轮询，属于用户可见的活动。
      if (!A.state.iframe && !document.getElementById('ai-mirror-iframe')) A.inject();
      const f = A.state.iframe || document.getElementById('ai-mirror-iframe');
      if (f) f.style.display = '';
      // 用带兜底探测的激活：选择器尚未就绪时先补读配置再绑定，避免面板空白
      A.activateWithProbe();
    } else {
      // 关闭：先停用活动，再销毁 iframe。对话框应用随 iframe 一起销毁，
      // 不再拉配置、不再轮询；会话数据在 storage 中，不受影响。
      A.deactivate();
      A.destroyPanel();
    }
    // 把可见性同步给对话框：它据此启停外部卡片轮询。
    // 关闭时 iframe 已销毁，此消息无人接收，属预期。
    A.post({ type: 'panel_visible', visible: !!visible });
    A.log('面板显隐：' + (visible ? '打开' : '关闭') + '（关闭即销毁 iframe）');
  };

  /**
   * 激活：面板打开时调用。补一次完整解析，让面板立刻拿到当前对话。
   * 此前面板关闭期间不推送，打开后必须主动补一次，否则界面停在旧内容。
   */
  A.activate = function () {
    A.state.active = true;
    // 打开即重建后台监听：关闭时已全部解绑，这里按当前选择器重新绑定，
    // 并补一次完整解析，让面板立刻拿到当前对话。
    if (A.state.currentSel) A.startObserver(A.state.currentSel);
    else if (A.state.containerEl) A.sendPage(true, 'manual');
    // 会话巡检与主题监听都只在面板打开期间运行：关闭时已清掉，这里重新拉起。
    if (A.startConvWatch) A.startConvWatch();
    if (A.startThemeWatch) A.startThemeWatch();
  };

  /**
   * 面板打开时的兜底探测：若选择器尚未就绪（例如页面刚加载就点开面板，
   * 初始化异步尚未完成），补一次配置读取并绑定观察器，避免面板空白。
   */
  A.activateWithProbe = function () {
    A.state.active = true;
    if (A.state.currentSel) { A.activate(); return; }
    A.getConfig(function (cfg) {
      A.state.currentSel = cfg.container;
      A.activate();
    });
  };

  /**
   * 停用：面板关闭时调用。彻底停掉一切后台活动：
   * 取消待执行扫描、断开对话容器与侧边栏观察器、清除滚动监听、
   * 停止发送按钮轮询。关闭后本扩展在页面上不做任何监听与解析，
   * 只在用户再次打开面板时按需重建（见 activate）。
   * 注意：只停「活动代码」，不动 storage 里的会话数据。
   */
  A.deactivate = function () {
    A.state.active = false;
    // 1) 取消待执行的静默扫描
    if (A.state.scanTimer) { clearTimeout(A.state.scanTimer); A.state.scanTimer = null; }
    // 2) 断开对话容器观察器
    if (A.state.observer) { A.state.observer.disconnect(); A.state.observer = null; }
    A.state.containerEl = null;
    // 3) 断开左侧会话列表观察器
    if (A.state.historyObserver) { A.state.historyObserver.disconnect(); A.state.historyObserver = null; }
    A.state.historyEl = null;
    // 4) 解除对话区滚动监听
    if (A.state.scrollHandler) {
      document.removeEventListener('scroll', A.state.scrollHandler, true);
      A.state.scrollHandler = null;
    }
    // 5) 停止发送按钮状态轮询
    if (A.state.buttonTimer) { clearInterval(A.state.buttonTimer); A.state.buttonTimer = null; }
    A.state.isGenerating = false;
    // 6) 停止会话巡检定时器（仅面板打开期间需要）
    if (A.stopConvWatch) A.stopConvWatch();
    // 7) 停止宿主主题监听（面板关闭后无人消费主题）
    if (A.stopThemeWatch) A.stopThemeWatch();
    A.log('已停用：解绑观察器与定时器，停止一切后台活动');
  };

  /**
   * 向对话框 iframe 发送消息。
   * @param {Object} msg 消息体，至少含 type 字段
   */
  A.post = function (msg) {
    const iframe = A.state.iframe;
    if (iframe && iframe.contentWindow) {
      iframe.contentWindow.postMessage(msg, '*');
    } else {
      A.warn('post 失败：iframe 未就绪，消息被丢弃 →', msg && msg.type);
    }
  };
})();
