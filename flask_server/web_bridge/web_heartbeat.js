/* ============================================================
 * 网页版机器人 —— 临时诊断心跳
 *
 * 状态：**临时诊断代码，问题定位后整个文件删除**。
 *
 * 作用：每秒向服务端推一条 hb 日志，附带轮询状态摘要。
 * 卡住时凭摘要可区分到底是哪一环断的：
 *   poll=on、okago 一路涨      → 定时器在走但请求发不出去（网络或服务端不可达）
 *   poll=off                  → 定时器被浏览器丢弃，页面不再轮询
 *   busy=1 长期不变            → 某次请求卡死，pollBusy 锁住了后续轮询
 *   vis=hidden                → 页面被切到后台，浏览器冻结了定时器
 *
 * 代价：每秒一条，一天约 8.6 万条，当天日志文件会明显变大。
 * 清理方式：删除本文件，并移除 web_page.html 的引用与 web_page.js 里的两个调用点。
 * ============================================================ */
(function () {
  'use strict';

  // 心跳间隔（毫秒）
  var HEARTBEAT_MS = 1000;
  // 定时器句柄：非空表示心跳在跑
  var timer = null;
  // 状态提供者：每次心跳时调用，返回当前轮询状态摘要对象
  var stateProvider = null;

  /**
   * 启动心跳。重复调用会先停掉旧的，避免出现两个定时器。
   */
  function start() {
    stop();
    // 开关关闭时不启动：避免「关了还在跑」
    if (!enabled) return;
    timer = setInterval(function () {
      // 取不到状态也要发：心跳本身是否连续，就是重要信息
      var s = stateProvider ? stateProvider() : {};
      // okago：距上次轮询成功的秒数；-1 表示本次会话还没成功过
      var okAgo = s.lastPollOkAt ? Math.round((Date.now() - s.lastPollOkAt) / 1000) : -1;
      window.WebLog.heartbeat('poll=' + (s.pollOn ? 'on' : 'off')
        + ' busy=' + (s.busy ? 1 : 0)
        + ' fail=' + (s.failCount || 0)
        + ' vis=' + (document.hidden ? 'hidden' : 'visible')
        + ' okago=' + okAgo);
    }, HEARTBEAT_MS);
  }

  /** 停止心跳。 */
  function stop() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  // 开关：默认关闭。
  //
  // 心跳是排查「页面卡住」的临时诊断手段，每秒一条，一天约 8.6 万条。
  // 该问题可能长期无法定位，长期开着会把日志文件撑大，故默认关闭，
  // 需要排查时在设置页显式打开。
  var enabled = false;

  /**
   * 初始化：注入状态提供者与开关初值，并绑定顶栏开关按钮。
   *
   * @param {Function} provider 返回 { pollOn, busy, failCount, lastPollOkAt } 的函数
   * @param {boolean}  [on]     开关初值，缺省关闭
   */
  function init(provider, on) {
    stateProvider = provider || null;
    enabled = !!on;
    bindButton();
  }

  /**
   * 绑定顶栏开关按钮：点击切换并持久化到 localStorage。
   *
   * 放在本模块而非主文件，是因为它只服务心跳，
   * 且主文件已顶到行数上限。
   */
  function bindButton() {
    var btn = document.getElementById('btnHeartbeat');
    if (!btn) return;
    /** 按当前开关状态刷新按钮文案与样式。 */
    var refresh = function () {
      btn.textContent = enabled ? '心跳：开' : '心跳：关';
      btn.className = 'hb-btn' + (enabled ? ' on' : '');
    };
    refresh();
    btn.addEventListener('click', function () {
      setEnabled(!enabled);
      try { localStorage.setItem('webHeartbeatEnabled', enabled ? '1' : '0'); } catch (e) {}
      refresh();
      // 打开时立即启动；关闭时 setEnabled 已停表
      if (enabled) start();
    });
  }

  /**
   * 设置开关。关闭时立即停表，打开时立即启动（若调用方已就绪）。
   * @param {boolean} on 是否启用
   */
  function setEnabled(on) {
    enabled = !!on;
    if (!enabled) stop();
  }

  /** 查询当前开关状态。 */
  function isEnabled() {
    return enabled;
  }

  window.WebHeartbeat = {
    init: init, start: start, stop: stop,
    setEnabled: setEnabled, isEnabled: isEnabled
  };
})();
