// 内容脚本入口：初始化并启动
(function () {
  if (window.__AI_STYLE_DEBUG_INITIALIZED__) return;
  window.__AI_STYLE_DEBUG_INITIALIZED__ = true;

  const A = window.AIStyleDebug;

  A.initShadowDrawer();
  A.initEventListeners();

  A.loadConfig().then(() => {
    // 配置读取到挂靠侧后再应用一次形状（注入时配置尚未加载）
    A.applyDrawerShape(A.state.drawerOpen);
    chrome.storage.onChanged.addListener(() => A.loadConfig());
    A.tick();
  });
})();
