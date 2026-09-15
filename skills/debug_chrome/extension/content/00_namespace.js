// 内容脚本共享命名空间与常量
window.AIStyleDebug = (function () {
  const SHADOW_HOST_ID = 'ai-style-debug-host';
  const MAX_ELEMENTS = 5;
  const MAX_DOM_CHARS = 2000;
  const MAX_SNAPSHOT_CHARS = 20000;
  const MAX_SHOT_WIDTH = 1280;
  // 后端指向工具服务（chat-bridge）；端口与工具服务 config.yaml 的 flask.port 一致
  const DEFAULT_BACKEND_URL = 'http://127.0.0.1:5000';
  const DRAWER_READY_TIMEOUT_MS = 5000;

  // get_element_style 默认返回的常用 CSS 属性。全量样式有数百条，默认只回传
  // 调试最常用的这批；需要全量时传 include_all=true，需要自定义时传 properties 数组。
  const DEFAULT_STYLE_PROPS = [
    'display', 'position', 'top', 'right', 'bottom', 'left', 'z-index',
    'width', 'height', 'min-width', 'max-width', 'min-height', 'max-height',
    'margin', 'padding',
    'box-sizing', 'flex', 'flex-direction', 'justify-content', 'align-items', 'gap',
    'grid-template-columns', 'grid-template-rows',
    'font-family', 'font-size', 'font-weight', 'line-height', 'color', 'text-align',
    'background', 'background-color', 'background-image',
    'border', 'border-radius', 'box-shadow', 'opacity',
    'overflow', 'overflow-x', 'overflow-y', 'transform', 'transition', 'visibility',
  ];

  // 提供方标识：与 skills/debug_chrome/tool.json 的 provider 一致
  const PROVIDER = 'debug_chrome';
  // 命令轮询节奏：1 秒一次，上线即启、下线即停
  const POLL_INTERVAL_MS = 1000;

  const state = {
    shadowRoot: null,
    drawerIframe: null,
    selectMode: false,
    highlightBox: null,
    highlightTag: null,     // 高亮框上方的尺寸标签
    highlightLayer: null,   // 承载高亮框的隔离层（位于 Shadow DOM）
    drawerOpen: false,
    connected: false,
    screenshotEnabled: false,
    styleListEnabled: false,
    backendUrl: DEFAULT_BACKEND_URL,
    pollIntervalMs: POLL_INTERVAL_MS,
    pollFailCount: 0,
    pollTimer: null,
    tabId: null,
    drawerReady: false,
    drawerWatchdogTimer: null,
    selectedElements: [],
    drawerSide: 'right',   // 抽屉挂靠侧：right / left
  };

  return {
    SHADOW_HOST_ID,
    MAX_ELEMENTS,
    MAX_DOM_CHARS,
    MAX_SNAPSHOT_CHARS,
    MAX_SHOT_WIDTH,
    DEFAULT_BACKEND_URL,
    DRAWER_READY_TIMEOUT_MS,
    DEFAULT_STYLE_PROPS,
    PROVIDER,
    POLL_INTERVAL_MS,
    state,
  };
})();
