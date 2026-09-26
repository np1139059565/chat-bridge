// 内容脚本共享命名空间与常量
window.AIStyleDebug = (function () {
  // 抽屉 iframe 的 id。iframe 直接挂在顶层文档的 light DOM 上，
  // 页面脚本与控制台可用 document.getElementById 直接取到。
  const DRAWER_IFRAME_ID = 'ai-style-debug-iframe';
  const MAX_ELEMENTS = 5;
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
  // 命令轮询节奏：先快后慢。
  // 常规间隔 5 秒；连接状态刚变化后的 30 秒内用 1 秒快速间隔，
  // 便于尽快确认状态稳定或恢复，之后自动回落到常规间隔。
  // 轮询本身就是心跳，既要取命令也要探测连接；长期高频轮询没有必要。
  const POLL_INTERVAL_MS = 5000;        // 常规间隔
  const FAST_POLL_INTERVAL_MS = 1000;   // 状态切换后的快速间隔
  const FAST_POLL_WINDOW_MS = 30000;    // 快速间隔持续的窗口
  // 连续失败次数达到此阈值才判定为「未连接」。单次失败可能来自瞬时抖动
  // 或页面切换，不应立刻翻状态，否则界面会频繁闪断。
  const POLL_FAIL_THRESHOLD = 3;

  const state = {
    drawerIframe: null,
    selectMode: false,
    highlightBox: null,
    highlightTag: null,     // 高亮框上方的尺寸标签
    highlightLayer: null,   // 承载高亮框的层（直接挂在顶层文档）
    connected: false,
    screenshotEnabled: false,
    styleListEnabled: false,
    backendUrl: DEFAULT_BACKEND_URL,
    pollIntervalMs: POLL_INTERVAL_MS,
    connectedChangedAt: 0,   // 上次连接状态变化的时刻（毫秒），用于先快后慢的节奏判定
    pollFailCount: 0,
    pollTimer: null,
    polling: false,          // 是否有一次轮询在途（防止手动与定时触发并发）
    pollingEnabled: false,   // 是否允许轮询：抽屉存在时才取命令，关闭即停止
    tabId: null,
    drawerReady: false,
    drawerWatchdogTimer: null,
    selectedElements: [],
    drawerSide: 'right',   // 抽屉挂靠侧：right / left
    themeObserver: null,          // 宿主主题监听器：仅抽屉打开期间存在
    pageListenersAttached: false, // 页面级交互监听是否已绑定：随抽屉开关
  };

  // 日志工具：默认开启，带统一前缀，便于在控制台过滤本扩展的输出。
  // 这些日志用于判断「命令路由 / 抽屉开关是否真的生效」，因此不受任何开关限制。
  const LOG_PREFIX = '[AI-Style-Debug]';

  /** 打印一条普通日志（默认开启）。 */
  function log() {
    console.log.apply(console, [LOG_PREFIX].concat(Array.prototype.slice.call(arguments)));
  }

  /** 打印一条告警日志（默认开启）。 */
  function warn() {
    console.warn.apply(console, [LOG_PREFIX].concat(Array.prototype.slice.call(arguments)));
  }

  return {
    LOG_PREFIX,
    log,
    warn,
    DRAWER_IFRAME_ID,
    MAX_ELEMENTS,
    MAX_SHOT_WIDTH,
    DEFAULT_BACKEND_URL,
    DRAWER_READY_TIMEOUT_MS,
    DEFAULT_STYLE_PROPS,
    PROVIDER,
    POLL_INTERVAL_MS,
    FAST_POLL_INTERVAL_MS,
    FAST_POLL_WINDOW_MS,
    POLL_FAIL_THRESHOLD,
    state,
  };
})();
