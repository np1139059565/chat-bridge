// 模块：extend/content/05_index.js
// 用途：内容脚本入口。注册窗口消息监听、工具栏点击监听、定时巡检、
//       扩展卸载清理与 bfcache 补注入，并完成页面初始化。
// 依赖：content/00_state.js ~ 04_observer.js（需按序号先加载）
(function () {
  'use strict';
  const A = window.AIMirrorContent;

  // 来自对话框（iframe）的消息
  window.addEventListener('message', function (e) {
    const d = e.data;
    if (!d || !d.type) return;
    if (d.type === 'request_page') A.sendPage(true, 'manual');
    else if (d.type === 'auto_send') A.pasteToWebpageAI(d.text || '');
    else if (d.type === 'request_theme') {
      // 对话框就绪后主动询问主题，避免 iframe 加载早于主题推送而错过首帧
      A.postTheme();
    }
    else if (d.type === 'request_panel_side') {
      // iframe 就绪后主动询问当前挂靠侧，避免刷新后面板方向与记录不一致
      A.post({ type: 'panel_side', side: A.state.panelSide });
    }
    else if (d.type === 'request_panel_visible') {
      // iframe 就绪后主动询问面板可见性：对话框据此决定是否启动外部卡片轮询
      A.post({ type: 'panel_visible', visible: !A.state.dialogHidden });
    }
    else if (d.type === 'set_panel_side') {
      A.state.panelSide = d.side === 'left' ? 'left' : 'right';
      A.applyPanelSide();
      // 持久化挂靠侧，刷新后保持
      try { chrome.storage.local.set({ aiMirrorPanelSide: A.state.panelSide }); } catch (e) {}
    }
    else if (d.type === 'close_panel') {
      A.setDialogVisible(false);
    }
    else if (d.type === 'picker_start') {
      // 抽屉发起「选择元素」：进入选择模式，选中后回传 picker_result
      A.pickerStart();
    }
    else if (d.type === 'picker_stop') {
      A.pickerStop();
    }
    else if (d.type === 'bridge_click_element') {
      // QQ 指令「点击元素」：按选择器点击页面元素。
      // 带上 request_id，抽屉据此把执行结果（含失败）发回 QQ。
      const res = A.clickBySelector(d.selector || '');
      A.post({
        type: 'click_result',
        ok: !!res.ok,
        reason: res.reason || '',
        count: res.count || 0,
        selector: d.selector || '',
        request_id: d.request_id || ''
      });
    }
    else if (d.type === 'bridge_screenshot') {
      // QQ 指令「截屏」：captureVisibleTab 只能在后台调用，转发过去
      A.captureTab(d.request_id || '');
    }
    else if (d.type === 'bridge_copy_md') {
      // 抽屉请求：点页面的复制按钮，取带格式的 Markdown。
      // 点击后由主世界 hook 截获剪贴板内容，经 clip_copied 回传抽屉。
      const ok = A.clickCopyButton(d.selector || '');
      // 先回报「是否点到按钮」：抽屉据此区分失败阶段——
      // 是没找到按钮，还是点了但 hook 没截到内容。
      A.post({ type: 'clip_clicked', ok: !!ok });
      if (!ok) A.post({ type: 'clip_copied', text: '', error: 'button_not_found' });
    }
    else if (d.type === 'bridge_refresh_page') {
      // QQ 指令「刷新页面」：先记标记，刷新后据此自动打开抽屉。
      // 标记存 sessionStorage：刷新后仍在，关标签页即消失，
      // 这样「刷新后自动开抽屉」只对本次操作生效，不会长期驻留。
      try { sessionStorage.setItem('aiMirrorAutoOpen', '1'); } catch (e) { /* 忽略 */ }
      location.reload();
    }
  });

  // 来自后台（工具栏点击）的消息：切换悬浮对话框显隐
  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg && msg.type === 'toggle_dialog') {
      // 以「iframe 是否存在」为唯一开关依据：
      //   存在（面板打开中）→ 关闭（销毁 iframe）；
      //   不存在（面板关闭）→ 打开（创建 iframe 并激活）。
      // 不再用 display 判断，避免「创建即显示」与「隐藏态」两套状态打架。
      const f = document.getElementById('ai-mirror-iframe');
      if (f) A.setDialogVisible(false);
      else A.setDialogVisible(true);
    }
  });

  // 会话巡检定时器：仅面板打开期间运行。
  // 关闭时由 stopBackground 清掉，不在后台空转。
  let convTimer = null;
  /** 启动会话巡检：面板打开时调用。幂等，重复调用不叠加定时器。 */
  A.startConvWatch = function () {
    if (convTimer) clearInterval(convTimer);
    convTimer = setInterval(A.watchConversation, A.CONV_POLL_MS);
  };
  /** 停止会话巡检：面板关闭时调用。 */
  A.stopConvWatch = function () {
    if (convTimer) { clearInterval(convTimer); convTimer = null; }
  };

  // 建立长连接用于感知扩展卸载（见 cleanup 注释）
  try {
    const port = chrome.runtime.connect({ name: 'ai-mirror-cleanup' });
    port.onDisconnect.addListener(function () { A.cleanup('port_disconnect'); });
  } catch (e) {
    A.warn('cleanup: 建立长连接失败（扩展可能已卸载）', e && e.message);
  }

  // 前进/后退缓存（bfcache）恢复时内容脚本不会重跑，需要重挂事件监听。
  // 注意：此处不预注入 iframe —— 面板默认关闭，等用户点开时再按需创建。
  // 只把选择器记回 state，供打开时绑定观察器使用。
  window.addEventListener('pageshow', function (e) {
    if (e.persisted) {
      A.getConfig(function (cfg) { A.state.currentSel = cfg.container; });
    }
  });

  // 宿主主题监听器：仅面板打开期间存在。
  // 面板关闭时对话框已销毁，推送主题无人接收，继续观察纯属后台空转。
  let themeObserver = null;
  /** 启动宿主主题监听：面板打开时调用。幂等，已在监听则跳过。 */
  A.startThemeWatch = function () {
    if (themeObserver) return;
    let timer = null;
    const onChange = function () {
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () { A.postTheme(); }, 200);
    };
    const opts = { attributes: true, attributeFilter: ['class', 'style', 'data-theme', 'data-color-mode'] };
    themeObserver = new MutationObserver(onChange);
    themeObserver.observe(document.documentElement, opts);
    if (document.body) themeObserver.observe(document.body, opts);
  };
  /** 停止宿主主题监听：面板关闭时调用。 */
  A.stopThemeWatch = function () {
    if (themeObserver) { themeObserver.disconnect(); themeObserver = null; }
  };

  // 初始化
  A.getConfig(function (cfg) {
    // 每次页面加载都保持关闭：不依据历史显隐状态，仅在用户主动点击工具栏图标时展开。
    // 这样刷新、切换标签页、新开页面都不会自动弹出。
    chrome.storage.local.get(['aiMirrorPanelSide'], function (res) {
      A.state.panelSide = (res && res.aiMirrorPanelSide === 'left') ? 'left' : 'right';
      A.state.dialogHidden = true;
      // 只记下当前站点的对话容器选择器，不注入 iframe、不绑定观察器：
      // 面板默认关闭，此时不需要任何界面与监听；等用户点开面板时
      // setDialogVisible(true) 再按需创建 iframe、绑定观察器。
      // 这样页面在面板关闭期间没有任何本扩展的活动代码，杜绝后台空转。
      A.state.currentSel = cfg.container;
      // 「刷新页面」指令留下的标记：本次加载后自动打开抽屉，
      // 用完即清（sessionStorage 本就随标签页关闭而失效，这里再显式清一次，
      // 避免用户在同标签页内二次刷新时又被意外弹出）。
      let autoOpen = false;
      try {
        autoOpen = sessionStorage.getItem('aiMirrorAutoOpen') === '1';
        if (autoOpen) sessionStorage.removeItem('aiMirrorAutoOpen');
      } catch (e) { /* 忽略 */ }
      if (autoOpen) setTimeout(function () { A.setDialogVisible(true); }, 300);
    });
  });
})();
