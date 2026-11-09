/* ============================================================
 * 网页版机器人 —— 前端逻辑
 * 职责：拉取消息、倒序渲染、Markdown 解析、指令链接、语音自动播放
 * ============================================================ */
(function () {
  'use strict';
  // ---------- 全局状态 ----------
  var cursor = 0;            // 已拉取到的最大 seq
  var seen = {};             // 已渲染消息 id，防重复
  var lastRenderedTs = 0;    // 最后一条渲染消息的时间戳（判断是否该吸顶）

  // ---------- DOM 上限与懒加载 ----------
  // 页面保留条数、裁剪与向前翻页的实现见 web_dom_limit.js（window.WebDom）。
  // 初始化在其后（依赖 listEl 与 renderMessage 均已就绪）。

  var listEl = document.getElementById('list');
  var inputEl = document.getElementById('input');
  var dotEl = document.getElementById('dot');
  var statusTextEl = document.getElementById('statusText');

  // ---------- 前端日志上报（实现在 web_clientlog.js，暴露为 window.WebLog） ----------
  // 手机上看不到控制台，日志只能打到后端；实现细节见 web_clientlog.js 顶部说明。
  var clientLog = window.WebLog.clientLog;
  if (window.WebPollTrace) window.WebPollTrace.init(clientLog);   // 临时诊断：注入日志函数

  // ---------- 时间格式化（实现在 web_time.js） ----------
  var fmtTime = window.WebTime.fmtTime;

  // ---------- 渲染单条消息并倒序插入到顶部 ----------
  // 实现已迁至 web_render_message.js，此处仅注入依赖并转调。
  if (window.WebMessage) {
    window.WebMessage.init({ listEl: listEl, seen: seen, fmtTime: fmtTime });
  }

  /**
   * 渲染一条消息（转调 WebMessage.render）。
   *
   * @param {Object}  m         消息对象
   * @param {boolean} allowAuto 是否允许该条语音自动播放
   * @param {boolean} atBottom  为真时插到列表末尾（懒加载更早的消息用）
   * @returns {boolean} 是否真的渲染了
   */
  function renderMessage(m, allowAuto, atBottom) {
    return window.WebMessage.render(m, allowAuto, atBottom);
  }

  // ---------- 图片看大图 ----------
  // 浮层与手势缩放已抽到 web_viewer.js，暴露为 window.WebViewer。

  // ---------- 指令链接 / 图片点击（事件委托） ----------
  listEl.addEventListener('click', function (e) {
    var t = e.target;
    // 图片：页面内浮层看大图，复用缓存
    if (t && t.classList && t.classList.contains('msg-img')) {
      e.preventDefault();
      window.WebViewer.show(t.getAttribute('src') || '');
      return;
    }
    if (t && t.classList && t.classList.contains('cmd-link')) {
      e.preventDefault();
      var cmd = t.getAttribute('data-cmd') || '';
      inputEl.value = cmd;
      inputEl.focus();
      // 移动端尝试聚焦并放到末尾
      try { inputEl.setSelectionRange(cmd.length, cmd.length); } catch (err) {}
    }
  });

  // ---------- 拉取消息 ----------
  // 轮询健壮性：pollBusy 防重入；failCount 连续失败计数（超容差才显示断开）。
  var pollBusy = false, failCount = 0;
  // 在途轮询的可中止句柄：页面切后台时主动中止，避免「回来还要干等超时」。
  // inflightCtrl 是 AbortController；inflightTimer 是那 6 秒超时器。
  var inflightCtrl = null, inflightTimer = null;

  /**
   * 主动中止在途轮询，并立即释放忙碌标记。
   *
   * 为什么需要：手机切到别的应用时，浏览器会冻结页面定时器，但在途的 fetch
   * 不会随之结束。切回前台后，这轮请求仍占着 pollBusy，补拉会被 skip(busy)
   * 挡掉，只能干等它自己 6 秒超时——用户看到的就是「回来还要卡一会儿」。
   * 这里直接掐断它并解锁，让回到前台的那次补拉能立刻跑起来。
   *
   * 注意：中止会让该轮进入 catch 计一次失败，故中止前把 pollBusy 先清掉，
   * 并让失败分支不把「主动中止」算作断连（由 isAbort 判断）。
   */
  function abortInflightPoll(why) {
    if (inflightTimer) { clearTimeout(inflightTimer); inflightTimer = null; }
    var c = inflightCtrl;
    inflightCtrl = null;
    pollBusy = false;
    // 无条件留痕：不管当时有没有在途请求都记一条，并注明触发原因与是否有请求被掐断。
    // 目的：让「新代码是否在页面上运行」有确定的证据，不必依赖「恰好有请求在飞」这种
    // 概率条件——否则切后台时若上一轮刚好已完成，就什么都不会记，无法判断改动是否生效。
    clientLog('poll', 'abort(' + (why || '') + ') inflight=' + (c ? 'yes' : 'no'));
    if (c) {
      try { c.abort(); } catch (e) { /* 已结束或环境不支持：忽略 */ }
    }
  }
  // 容差为 1：一次失败即判定未连接。
  // 此前放宽到 4 是为了扛住偶发抖动，代价是断线后要连续等四个周期才显示、
  // 期间界面一直停在旧状态，用户看到的就是「要等十几秒」。
  // 抖动由「失败后立即重连」承担——早判早重连，比晚判后干等更接近真实体验。
  var FAIL_TOLERANCE = 1;

  // 临时诊断开关：定位「切 app 回来发送必失败」；true 时每轮记 begin/end 配对（约 7 万条/天）
  var POLL_LOG_VERBOSE = true;

  /**
   * 轮询成功的处理：更新连接状态、按需渲染新消息、维护滚动与裁剪。
   *
   * @param {Object}  data    接口返回体
   * @param {boolean} history 是否为首次铺历史（不自动播语音、不裁剪）
   * @param {number}  t0      本轮发起时刻，用于记慢响应日志
   */
  function onPollOk(data, history, t0) {
    // 正常轮询不记日志（每 2.5 秒一次、量大）；只在响应偏慢时记，
    // 便于发现「变慢的苗头」而不淹没日志。失败仍照常记录。
    if (!history && WebLogic.isSlowPoll(Date.now() - t0, 1000)) clientLog('poll', 'slow ' + (Date.now() - t0) + 'ms');
    if (failCount > 0) clientLog('poll', 'recover failCount=' + failCount + ' -> 0');
    failCount = 0;
    setStatus(true);
    // 诊断用：记录最后一次轮询成功的时刻，心跳据此报「距上次成功多少秒」
    lastPollOkAt = Date.now();
    if (!data || !data.success) return;
    cursor = data.seq || cursor;
    var _cursorForCatchUp = cursor;
    var msgs = data.messages || [];
    // 正序遍历、倒序插入：最终最新在顶部。
    // 历史加载（history）不自动播语音；增量拉取的新语音在解锁后自动播。
    var allowAuto = !history;
    var _rt0 = Date.now();
    msgs.forEach(function (m) { renderMessage(m, allowAuto); });
    var _rt = Date.now() - _rt0;
    // 新消息到达：按 DOM 上限裁剪（实现见 web_dom_limit.js）
    if (!history && window.WebDom) window.WebDom.afterAppend();
    // 本批渲染完再补齐：整页重载后游标归零，靠存储里的旧游标把中间段补回来。
    if (window.WebCursor) window.WebCursor.onPollOk(_cursorForCatchUp, history);
    // 渲染是主线程同步操作，渲染条数多 / 单条重时会明显占主线程，
    // 这里记渲染条数与耗时：若耗时大，就是「页面卡住」的嫌疑点。
    if (!history && (msgs.length || _rt > 200)) {
      clientLog('render', 'n=' + msgs.length + ' cost=' + _rt + 'ms');
    }
    // 新消息渲染后触发一次待合成扫描：把「生成中」的语音自动轮询、就绪即自动连播
    if (window.WebVoice && window.WebVoice.kick) window.WebVoice.kick();
    // 保持可见区域是最新消息（列表倒序，最新在顶部）
    if (listEl.scrollTop < 40) listEl.scrollTop = 0;
    // 首屏只铺 10 条，不满一屏时主动补更早的消息（否则滚动条不出现、翻不到历史）
    if (history && window.WebDom && window.WebDom.fillIfNeeded) window.WebDom.fillIfNeeded();
  }

  /**
   * 轮询失败的处理：判定未连接并立即重连。
   *
   * @param {Error}   err     失败原因
   * @param {boolean} history 是否为首次铺历史（首次失败不触发重连）
   * @param {number}  t0      本轮发起时刻，用于记耗时
   */
  function onPollFail(err, history, t0) {
    // 主动中止（切后台 / 回前台补拉前掐断）不算断连：
    // 它是预期行为，若计入失败会误报「连接断开」，也会污染 failCount。
    if (WebLogic.isAbortError(err && err.name)) {
      if (!history) clientLog('poll', 'aborted（主动中止，不计失败）');
      return;
    }
    // 失败分类（区分「发不出去」与「发出去了没回应」）由 WebLogic 统一实现，
    // 页面不再内联——同一逻辑在发送路径也复用，避免两处各写一份。
    var kind = WebLogic.classifyFailKind(err && err.name, err && err.message);
    var offline = WebLogic.offlineSuffix(typeof navigator !== 'undefined' ? navigator.onLine : true);
    if (!history) clientLog('poll', 'fail ' + (Date.now() - t0) + 'ms kind=' + kind + offline + ' failCount=' + (failCount + 1));
    failCount += 1;
    // 一次失败即判定未连接：不让界面停在「看似已连接、实际收不到消息」的假象里。
    if (WebLogic.shouldShowDisconnected(failCount, FAIL_TOLERANCE)) setStatus(false);
    // 一次失败即彻底重建：停表、掐断在途、清忙标记、重开定时器、立刻补拉。
    // 不再设最小重连间隔，也不再依赖「延迟重连」那层判断——
    // 那层判断的代价是失败后可能迟迟不重建，用户看到的就是「一直未连接」。
    // 空转风险由「重建后立刻补拉一次」加轮询周期本身兜住：
    // 断网时每轮 2.5 秒一次，不会形成高频空转。
    if (!history) hardResetPolling();
  }

  /**
   * 彻底重建轮询：停表 → 掐断在途 → 清忙标记 → 重开定时器 → 立即补拉。
   *
   * 这是断连恢复的唯一入口。之所以把这几步捆在一起，是因为它们必须同时成立：
   * 只重建定时器而 pollBusy 仍为真，下一轮仍会在入口被跳过；
   * 只清忙标记而不重建定时器，则永远不会有下一轮。
   * 不做整页刷新——刷新会丢掉滚动位置与输入框内容，代价远大于收益。
   */
  function hardResetPolling() {
    var _r0 = Date.now();
    clientLog('poll', 'reset.begin timer=' + (pollTimer ? 'on' : 'off') + ' busy=' + (pollBusy ? 1 : 0) + ' failCount=' + failCount);
    stopPolling();
    abortInflightPoll('reset');
    pollBusy = false;
    startPolling();
    clientLog('poll', 'reset.done cost=' + (Date.now() - _r0) + 'ms');
    fetchMessages(false);
  }

  function fetchMessages(history, src) {
    var _src = src || 'tick';
    if (WebLogic.shouldSkipPoll(pollBusy)) {
      // 上一轮未完成：跳过。记一条，便于看出「请求堆积」。
      if (!history) clientLog('poll', 'skip(busy) src=' + _src);
      return;   // 上一轮未完成：跳过本轮，避免并发堆积
    }
    pollBusy = true;
    var _t0 = Date.now();
    // 诊断：每轮入口打点与末尾 end 配对——有 begin 无 end 即该轮卡死
    if (!history && POLL_LOG_VERBOSE) clientLog('poll', 'begin src=' + _src + ' cursor=' + cursor + ' hidden=' + (document.hidden ? 1 : 0));
    // 首次铺屏只取最新 10 条（后端 history=1 分支），其余滑到底部再懒加载。
    // 增量轮询仍按 200 拉，避免断开重连后新消息一次拿不全。
    var url = '/api/web/messages?cursor=' + cursor + '&limit=' + (history ? 10 : 200)
      + (window.WebSite ? window.WebSite.queryParam() : '');
    if (history) url += '&history=1';
    // 加超时：卡住的请求主动中断，否则 pollBusy 会永久为真、轮询停摆。
    // 由 10 秒收紧到 6 秒：轮询每 2.5 秒一次，6 秒足够正常请求完成；
    // 更短超时让偶发卡顿更快被跳过、更快进入下一轮重试，减少「断开」停留时长。
    var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    // 记录本轮控制器与超时器：页面切后台时需要外部主动中止（见 abortInflightPoll）
    inflightCtrl = ctrl;
    // 诊断：区分「6 秒超时中断」与「切后台主动中止」——两者都是 AbortError，
    // 此前在日志里无法区分，用 _timedOut 标记。
    var _timedOut = false;
    var timer = setTimeout(function () { _timedOut = true; if (ctrl) ctrl.abort(); }, 6000);
    inflightTimer = timer;
    // ---------- 临时诊断：分段计时（实现见 web_poll_trace.js，问题定位后删除） ----------
    // 把一次轮询拆成四段分别计时，定位卡在网络、传输、解析还是渲染。
    var _p0 = window.WebPollTrace ? window.WebPollTrace.now() : Date.now();
    var _outcome = 'unknown';
    fetch(url, { headers: { 'Accept': 'application/json' }, signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) {
        return window.WebPollTrace ? window.WebPollTrace.traceResponse(r, _p0, history) : r.json();
      })
      .then(function (data) {
        _outcome = 'ok';
        var _p4 = window.WebPollTrace ? window.WebPollTrace.now() : Date.now();
        onPollOk(data, history, _t0);
        if (window.WebPollTrace) window.WebPollTrace.traceBusiness(_p0, _p4, history);
      })
      .catch(function (err) {
        _outcome = WebLogic.isAbortError(err && err.name) ? (_timedOut ? 'timeout6s' : 'abort') : 'fail';
        onPollFail(err, history, _t0);
      })
      .then(function () {
        clearTimeout(timer);
        // 只清理「本轮自己的」句柄，避免把后续轮次的句柄误清。
        if (inflightCtrl === ctrl) inflightCtrl = null;
        if (inflightTimer === timer) inflightTimer = null;
        pollBusy = false;
        // 诊断：每轮出口打点，与 begin 配对。正常轮询也记（噪音换配对完整性）。
        if (!history && POLL_LOG_VERBOSE) clientLog('poll', 'end src=' + _src + ' outcome=' + _outcome + ' cost=' + (Date.now() - _t0) + 'ms');
      });
  }

  // ---------- 游标持久化与缺口补齐（web_cursor.js）：重载后补齐中间段 ----------
  if (window.WebCursor) {
    window.WebCursor.wirePage({ renderMessage: renderMessage, clientLog: clientLog, WebDom: window.WebDom });
  }

  function setStatus(ok) {
    dotEl.className = 'dot' + (ok ? ' on' : '');
    statusTextEl.textContent = ok ? '已连接' : '未连接';
  }

  // ---------- 发送消息（文字与图片一起发出） ----------
  function sendMessage() {
    var text = inputEl.value.trim();
    // 待发图片从选图模块取副本：本次发送的快照即此副本，失败时原样恢复
    var snapshotImgs = window.WebImagePicker.list();
    // 无文字也无图片：不发送（判定口径见 WebLogic.canSend）
    if (!WebLogic.canSend(text, snapshotImgs.length)) return;
    // 快照文字：失败时可原样恢复，避免消息静默丢失。
    var snapshotText = text;
    // 诊断：发送入口打点，与 finish 的 ok / fail 配对——有 begin 无二者即 fetch 无响应
    clientLog('send', 'begin textLen=' + text.length + ' imgs=' + snapshotImgs.length + ' hidden=' + (document.hidden ? 1 : 0));
    // 只有发送成功才清空输入与图片；失败则恢复现场并提示。
    // 失败时记录原因类型：超时（已发出无响应）/ 网络错（未发出）/ 服务端错误。
    var finish = function (res, err) {
      if (WebLogic.isSendOk(res)) { clientLog('send', 'ok'); clearImages(); fetchMessages(false); return; }
      // 失败分类与轮询共用 WebLogic，避免两处各写一份分类逻辑。
      var kind = WebLogic.sendFailKind(res, err && err.name, err && err.message);
      var offline = WebLogic.offlineSuffix(typeof navigator !== 'undefined' ? navigator.onLine : true);
      var online = (typeof navigator !== 'undefined') && navigator.onLine ? 1 : 0;
      clientLog('send', 'fail kind=' + kind + offline + ' hidden=' + (document.hidden ? 1 : 0)
        + ' online=' + online + ' textLen=' + (snapshotText ? snapshotText.length : 0) + ' imgs=' + snapshotImgs.length);
      inputEl.value = snapshotText;
      window.WebImagePicker.restore(snapshotImgs);
      // 恢复内容后重算高度：发送前已把输入框清空并压回单行，
      // 不重算的话多行原文会被挤在单行高度里、看不全。
      autoGrow();
      setStatus(false);
      window.WebToast && window.WebToast.show('发送失败，内容已保留在输入框，请检查网络后重试');
    };
    // 发送超时：8 秒未返回即中断，避免按钮永久无反馈。
    var sctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var stimer = setTimeout(function () { if (sctrl) sctrl.abort(); }, 8000);
    var _sopts = { headers: { 'Content-Type': 'application/json' } };
    if (sctrl) _sopts.signal = sctrl.signal;
    inputEl.value = '';
    autoGrow();
    var _done = function () { clearTimeout(stimer); };
    if (snapshotImgs.length > 0) {
      // 有图片：图文一次性提交（多张一并），避免图片被丢弃
      _sopts.method = 'POST';
      _sopts.body = JSON.stringify({ dataUrls: snapshotImgs, text: text });
      fetch('/api/web/image', _sopts)
        .then(function (r) { _done(); finish(r, null); })
        .catch(function (e) { _done(); finish(null, e); });
    } else {
      _sopts.method = 'POST';
      _sopts.body = JSON.stringify({ text: text });
      fetch('/api/web/send', _sopts)
        .then(function (r) { _done(); finish(r, null); })
        .catch(function (e) { _done(); finish(null, e); });
    }
  }

  // ---------- 文件选择（一次一个，独立于图片预览） ----------
  // 绑定与上传逻辑都在 web_upload.js（使本文件保持在行数上限内）。
  // 成功回调里清空输入并刷新列表；失败提示由该模块直接弹出。
  WebUpload.bind(
    function () { return inputEl.value.trim(); },
    clientLog,
    function () { inputEl.value = ''; autoGrow(); fetchMessages(false); }
  );

  // ---------- 图片选择（支持一次多张） ----------
  // 实现已迁至 web_image_picker.js（window.WebImagePicker），此处仅注入依赖。
  // 清空后重算输入框高度：图片被提交或移除时输入框需要按文字重新撑开。
  window.WebImagePicker.init({ onClear: function () { autoGrow(); } });

  /** 清空已选图片与预览（转调 WebImagePicker.clear）。 */
  function clearImages() {
    window.WebImagePicker.clear();
  }

  // ---------- 指令展开面板 ----------
  // 实现在 web_commands.js（window.WebCommands），此处仅完成初始化。
  if (window.WebCommands) {
    window.WebCommands.init({
      btnCmd: document.getElementById('btnCmd'),
      cmdPanel: document.getElementById('cmdPanel'),
      cmdGrid: document.getElementById('cmdGrid'),
      inputEl: inputEl
    });
  }

  // ---------- 输入框自适应高度 ----------
  function autoGrow() {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
  }
  inputEl.addEventListener('input', autoGrow);
  inputEl.addEventListener('keydown', function (e) {
    // 回车发送（Shift+回车换行）
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  document.getElementById('btnSend').addEventListener('click', sendMessage);

  // ---------- 轮询调度 ----------
  // 用「可重建的定时器」而非裸 setInterval。
  //
  // 为什么：手机浏览器切后台会冻结定时器，回前台后不保证自动恢复，
  // 冻结久了甚至可能直接丢弃该定时器。被丢弃后页面再也不轮询，
  // 表现为「切回来显示无法连接、要再切出去切回来才好」——
  // 因为再次切换会走一遍可见性回调、重新拉起轮询。
  // 故切后台时主动停表，回前台时显式重建，不依赖浏览器是否恢复。
  var POLL_INTERVAL = 2500;
  var pollTimer = null;

  // ---------- 临时诊断心跳（实现见 web_heartbeat.js，默认关闭） ----------
  // 附带轮询状态摘要，区分「定时器被丢」「请求发不出」「页面被冻结」。
  var lastPollOkAt = 0;   // 最后一次轮询成功的时刻，心跳据此报「距上次成功多少秒」

  // 状态提供者：心跳模块每秒回调一次，取当前轮询现场
  if (window.WebHeartbeat) {
    var hbOn = false; try { hbOn = localStorage.getItem('webHeartbeatEnabled') === '1'; } catch (e) {}
    window.WebHeartbeat.init(function () {
      return { pollOn: !!pollTimer, busy: pollBusy, failCount: failCount, lastPollOkAt: lastPollOkAt };
    }, hbOn);
  }

  /** 启动（或重建）轮询定时器与诊断心跳。 */
  function startPolling() {
    stopPolling();
    pollTimer = setInterval(function () { fetchMessages(false); }, POLL_INTERVAL);
    if (window.WebHeartbeat) window.WebHeartbeat.start();
  }

  /** 停止轮询定时器与诊断心跳（切后台时不留残余）。 */
  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    if (window.WebHeartbeat) window.WebHeartbeat.stop();
  }

  // ---------- DOM 上限与懒加载初始化 ----------
  // 注入容器、渲染函数、反注册回调与日志函数，之后由模块自行管理裁剪与翻页。
  if (window.WebDom) {
    window.WebDom.init({
      listEl: listEl,
      render: function (m, allowAuto, atBottom) { return renderMessage(m, allowAuto, atBottom); },
      evict: function (seq) { delete seen['w-' + seq]; },
      log: clientLog
    });
  }

  // ---------- 首次加载：铺历史 + 启动轮询 ----------
  clientLog('page', 'load 开始首次铺历史');
  fetchMessages(true);
  startPolling();
  // 性能监控：有 longtask 是代码卡的；只有 tickgap 无 longtask，
  // 更像浏览器冻结了页面（详见 web_perf.js）。
  if (window.WebPerf) window.WebPerf.start();
  // 看门狗：定时自检轮询是否还活着，死了强制复活（详见 web_watchdog.js）。
  // 此前轮询停掉后只能靠「切回前台」恢复，事件没触发就永久未连接。
  if (window.WebWatchdog) {
    var wdState = function () { return { pollOn: !!pollTimer, busy: pollBusy, lastPollOkAt: lastPollOkAt }; };
    var wdRevive = function () { startPolling(); pollBusy = false; fetchMessages(false); };
    window.WebWatchdog.init({ state: wdState, revive: wdRevive }).start();
  }
  // 页面可见性变化打点：切后台时定时器会被系统暂停，这里记下进出时刻，
  // 便于把「断连空档」与「切后台」对齐——若空档两端正好是 hidden/visible，
  // 就是切后台所致，而非页面卡死。
  document.addEventListener('visibilitychange', function () {
    clientLog('page', document.hidden ? 'hidden（切后台）' : 'visible（回前台）');
  });
  // 页面重新可见时立即补拉一次：手机切后台会暂停定时器，
  // 回到前台若不主动拉，会等到下一个周期甚至更久才看到新消息。
  var hiddenAt = 0;

  document.addEventListener('visibilitychange', function () {
    if (document.hidden) {
      // 切后台：记录时刻 + 停表 + 掐断在途请求并解锁。
      hiddenAt = Date.now();
      stopPolling();
      abortInflightPoll('hidden');
      return;
    }
    // 回前台：一律走彻底重建，不整页刷新。
    // 刷新会丢滚动位置与输入框内容，且用户已明确要求禁止；
    // 陈旧页面带来的问题由重建轮询 + 看门狗兜住。
    var away = hiddenAt ? (Date.now() - hiddenAt) : 0;
    clientLog('page', 'visible（回前台，后台 ' + Math.round(away / 1000) + 's）→ 重建轮询 busy=' + (pollBusy ? 1 : 0) + ' failCount=' + failCount);
    hiddenAt = 0;
    hardResetPolling();
  });
})();
