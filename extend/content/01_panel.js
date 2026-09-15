// 模块：extend/content/01_panel.js
// 用途：悬浮对话框 iframe 的注入、定位、显隐，以及站点配置读取。
// 依赖：content/00_state.js（命名空间 A）、lib/dom-utils.js
(function () {
  'use strict';
  const A = window.AIMirrorContent;

  /**
   * 读取当前站点配置并回调。
   * 站点规则按 hostname 自动识别（无需浏览器存储配置，配置统一由后端 config.yaml 管理）。
   * 容器选择器完全由预设规则决定——之前暴露的「自定义 class 选择器」无法稳定工作
   * （各站 class 含易变哈希），已撤销。
   * @param {Function} cb 回调，入参 { profile, container, profileLabel }
   */
  A.getConfig = function (cb) {
    A.state.siteKey = A.currentHost() || 'unknown-site';
    A.state.profileId = A.guessProfile(A.state.siteKey);
    const prof = A.PROFILES[A.state.profileId] || A.PROFILES.glm;
    A.log('getConfig: 站点=' + A.state.siteKey, '规则=' + A.state.profileId, '容器=' + prof.container);
    cb({ profile: A.state.profileId, container: prof.container, profileLabel: prof.label });
  };

  /**
   * 计算面板定位样式。
   * 右侧挂靠 right:0，左侧挂靠 left:0；圆角与投影方向随挂靠侧翻转。
   * @returns {string} 可直接赋给 style.cssText 的样式串
   */
  A.panelPositionCss = function () {
    if (A.state.panelSide === 'left') {
      return 'position:fixed;top:0;left:0;width:' + A.panelWidth() +
        ';height:100vh;border:0;border-radius:' + A.PANEL_RADIUS_LEFT +
        ';box-shadow:' + A.PANEL_SHADOW_LEFT +
        ';background:' + A.PANEL_BG +
        ';z-index:' + A.PANEL_Z + ';';
    }
    return 'position:fixed;top:0;right:0;width:' + A.panelWidth() +
      ';height:100vh;border:0;border-radius:' + A.PANEL_RADIUS_RIGHT +
      ';box-shadow:' + A.PANEL_SHADOW_RIGHT +
      ';background:' + A.PANEL_BG +
      ';z-index:' + A.PANEL_Z + ';';
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
    if (f) f.style.cssText = A.panelPositionCss();
  };

  /**
   * 注入悬浮对话框 iframe。
   * 会先清理上一轮残留（扩展重导入 / 旧实例未移除），否则 id 守卫会误判“已存在”而跳过注入。
   */
  A.inject = function () {
    const IFRAME_SRC = chrome.runtime.getURL('dialog/dialog.html');
    // 清理上一轮残留的 iframe，避免 id 守卫误判“已存在”而跳过注入
    const old = document.getElementById('ai-mirror-iframe');
    if (old) { A.log('inject: 移除遗留 iframe'); old.remove(); }
    A.log('inject: 开始注入', IFRAME_SRC);
    const iframe = document.createElement('iframe');
    iframe.id = 'ai-mirror-iframe';
    iframe.src = IFRAME_SRC;
    // 高度必须显式给出，不能用 top/bottom 双向拉伸：iframe 是替换元素，
    // height:auto 会退化成内在高度（默认 150px），此时 top 与 bottom 过度约束，
    // 浏览器会忽略 bottom，面板只剩一条窄带。
    iframe.style.cssText = A.panelPositionCss();
    // 尊重上一次的关闭状态：用户关掉后刷新页面不应自动弹回来
    iframe.style.display = A.state.dialogHidden ? 'none' : '';
    document.body.appendChild(iframe);
    A.state.iframe = iframe;
    A.log('inject: 注入完成（显示=' + !A.state.dialogHidden + '）');
    // 窗口尺寸变化时重新计算宽度与挂靠方向
    window.addEventListener('resize', function () {
      A.applyPanelSide();
    });
  };

  /**
   * 显隐切换：仅作用于当前页面会话，不做持久化。
   * 刷新 / 新开页面一律回到默认关闭状态。
   * @param {boolean} visible 是否显示
   */
  A.setDialogVisible = function (visible) {
    A.state.dialogHidden = !visible;
    const f = A.state.iframe || document.getElementById('ai-mirror-iframe');
    if (f) f.style.display = visible ? '' : 'none';
    A.log('setDialogVisible: visible=' + visible);
  };

  /**
   * 向对话框 iframe 发送消息。
   * @param {Object} msg 消息体，至少含 type 字段
   */
  A.post = function (msg) {
    const iframe = A.state.iframe;
    if (iframe && iframe.contentWindow) {
      A.log('post →', msg.type, msg.type === 'page_blocks' ? '消息数=' + (msg.messages || []).length : '');
      iframe.contentWindow.postMessage(msg, '*');
    } else {
      A.warn('post 失败：iframe 未就绪，消息被丢弃 →', msg && msg.type);
    }
  };
})();
