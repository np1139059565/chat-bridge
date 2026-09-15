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
    A.log('收到 iframe 消息 ←', d.type);
    if (d.type === 'request_page') A.sendPage(true);
    else if (d.type === 'auto_send') { A.log('收到 auto_send 请求'); A.pasteToWebpageAI(d.text || ''); }
    else if (d.type === 'request_panel_side') {
      // iframe 就绪后主动询问当前挂靠侧，避免刷新后面板方向与记录不一致
      A.post({ type: 'panel_side', side: A.state.panelSide });
    }
    else if (d.type === 'set_panel_side') {
      A.state.panelSide = d.side === 'left' ? 'left' : 'right';
      A.applyPanelSide();
      // 持久化挂靠侧，刷新后保持
      try { chrome.storage.local.set({ aiMirrorPanelSide: A.state.panelSide }); } catch (e) {}
      A.log('set_panel_side: 挂靠侧 →', A.state.panelSide);
    }
    else if (d.type === 'close_panel') {
      A.setDialogVisible(false);
      A.log('close_panel: 已隐藏抽屉');
    }
  });

  // 来自后台（工具栏点击）的消息：切换悬浮对话框显隐
  chrome.runtime.onMessage.addListener(function (msg) {
    if (msg && msg.type === 'toggle_dialog') {
      let f = document.getElementById('ai-mirror-iframe');
      // 界面被清理 / 旧实例残留 / 注入失败时，点图标应先重新拉起，而不是直接隐藏一个不存在的元素
      if (!f) {
        A.log('toggle_dialog: 未找到 iframe，尝试重新注入');
        A.inject();
        f = document.getElementById('ai-mirror-iframe');
      }
      if (!f) {
        A.warn('toggle_dialog: 重新注入后仍无 iframe');
        return;
      }
      // 真正的 toggle：当前可见 → 隐藏；当前隐藏（display:none）→ 显示并重新探测对话容器
      if (f.style.display === 'none') {
        A.setDialogVisible(true);
        A.log('toggle_dialog: 显示对话框并重新探测对话容器');
        A.reprobe();
      } else {
        A.setDialogVisible(false);
        A.log('toggle_dialog: 隐藏对话框');
      }
    }
  });

  // 定时巡检：会话切换 / 容器节点被替换时补绑
  setInterval(A.watchConversation, 700);

  // 建立长连接用于感知扩展卸载（见 cleanup 注释）
  try {
    const port = chrome.runtime.connect({ name: 'ai-mirror-cleanup' });
    port.onDisconnect.addListener(function () { A.cleanup('port_disconnect'); });
  } catch (e) {
    A.warn('cleanup: 建立长连接失败（扩展可能已卸载）', e && e.message);
  }

  // 前进/后退缓存（bfcache）恢复时内容脚本不会重跑，需要补注入，否则界面消失
  window.addEventListener('pageshow', function (e) {
    if (e.persisted && !document.getElementById('ai-mirror-iframe')) {
      A.log('pageshow: bfcache 恢复，补注入 iframe');
      A.getConfig(function (cfg) { A.inject(); A.startObserver(cfg.container); });
    }
  });

  A.log('content 脚本已加载', location.href);

  // 初始化
  A.getConfig(function (cfg) {
    // 每次页面加载都保持关闭：不依据历史显隐状态，仅在用户主动点击工具栏图标时展开。
    // 这样刷新、切换标签页、新开页面都不会自动弹出。
    chrome.storage.local.get(['aiMirrorPanelSide'], function (res) {
      A.state.panelSide = (res && res.aiMirrorPanelSide === 'left') ? 'left' : 'right';
      A.state.dialogHidden = true;
      A.log('初始化：抽屉默认关闭，挂靠侧 =', A.state.panelSide);
      A.inject();
      A.startObserver(cfg.container);
    });
  });
})();
