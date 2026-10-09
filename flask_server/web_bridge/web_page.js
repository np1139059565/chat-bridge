/* ============================================================
 * 网页版机器人 —— 前端逻辑
 * 职责：拉取消息、倒序渲染、Markdown 解析、指令链接、语音自动播放
 * ============================================================ */
(function () {
  'use strict';
  var renderMarkdown = window.WebRender.renderMarkdown, composeBody = window.WebRender.composeBody,
    renderCommandPanel = window.WebRender.renderCommandPanel;

  // ---------- 全局状态 ----------
  var cursor = 0;            // 已拉取到的最大 seq
  var seen = {};             // 已渲染消息 id，防重复
  var lastRenderedTs = 0;    // 最后一条渲染消息的时间戳（判断是否该吸顶）

  var listEl = document.getElementById('list');
  var inputEl = document.getElementById('input');
  var dotEl = document.getElementById('dot');
  var statusTextEl = document.getElementById('statusText');

  // ---------- 前端日志上报（实现在 web_clientlog.js，暴露为 window.WebLog） ----------
  // 手机上看不到控制台，日志只能打到后端；实现细节见 web_clientlog.js 顶部说明。
  var clientLog = window.WebLog.clientLog;

  // ---------- 时间格式化 ----------
  function fmtTime(ts) {
    var d = new Date(ts || Date.now());
    var hh = ('0' + d.getHours()).slice(-2);
    var mm = ('0' + d.getMinutes()).slice(-2);
    return hh + ':' + mm;
  }

  // ---------- 渲染单条消息并倒序插入到顶部 ----------
  // @param allowAuto 是否允许该条语音自动播放。
  //   历史加载（首次铺屏）传 false：已存在的语音不该一进页面就自动播；
  //   增量拉取传 true：解锁后新到的语音才自动播。
  function renderMessage(m, allowAuto) {
    if (!m || seen[m.id]) return false;
    seen[m.id] = true;
    var role = m.role || 'ai';
    // 角色 → 显示名与样式类。system 为指令回执（如 /help 输出），单独配色。
    var who = role === 'user' ? '我' : (role === 'ai' ? 'AI' : (role === 'system' ? '系统' : '工具'));
    var cls = role === 'user' ? 'user' : (role === 'ai' ? 'ai' : (role === 'system' ? 'system' : 'tool'));
    var el = document.createElement('div');
    el.className = 'msg ' + cls;
    el.setAttribute('data-seq', m.seq);
    var body = '';
    // 带 image 字段：渲染真实图片（网页发图 / 指令结果截图等），点击可看大图。
    // image 可能是单个文件名（字符串）或多张（数组），统一成数组处理。
    if (m.image && (!Array.isArray(m.image) || m.image.length)) {
      var imgs = Array.isArray(m.image) ? m.image : [m.image];
      body = imgs.map(function (name) {
        var u = '/api/web/image-file/' + encodeURIComponent(name);
        // 不套 <a target="_blank">：新开标签页会重新请求图片。
        // 改为页面内浮层看大图，直接复用已加载的图片（同 src 走缓存，零请求）。
        return '<img class="msg-img" src="' + u + '" alt="图片">';
      }).join('');
      if (m.text && m.text !== '[截图]' && m.text !== '[图片]') body += renderMarkdown(m.text);
    } else if (m.kind === 'web-image' || m.text === '[图片]') {
      // 图文消息：图片标记 + 文字一并渲染，不能只画标记把文字吞掉。
      // 纯图片时 text 是「[图片]」，只显示标记；带文字时把文字正常渲染出来。
      var label = (m.text && m.text !== '[图片]') ? renderMarkdown(m.text) : '';
      body = '<span class="img-badge">🖼 图片</span>' + label;
    } else {
      body = renderMarkdown(m.text || '');
    }
    // 语音：交给独立语音模块渲染（已合成为播放器，未合成为「生成」按钮）
    var audio = window.WebVoice ? window.WebVoice.renderAudio(m) : '';
    // 消息 key（pid-id）：显示在角色名旁，供逐条核对消息块是否完整、有无缺块。
    // 旧数据可能没有该字段，缺省不显示，避免出现空标记。
    var keyTag = m.key ? '<span class="msg-key" title="消息 key（pid-id）">' + m.key + '</span>' : '';
    // 语音位置：思考之下、正文之上。组装细节见 WebRender.composeBody。
    el.innerHTML =
      '<div class="who">' + who + keyTag + '<span class="time">' + fmtTime(m.ts) + '</span></div>' +
      '<div class="body">' + composeBody(body, audio) + '</div>';
    // 倒序：最新插入到列表最前面
    if (listEl.firstChild) listEl.insertBefore(el, listEl.firstChild);
    else listEl.appendChild(el);
    // 语音播放器：绑定解锁与自动播放（历史语音不自动播，见 allowAuto）
    var au = el.querySelector('audio');
    if (au && window.WebVoice) window.WebVoice.bind(au, !!allowAuto);
    return true;
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
  // 容差：连续失败达到此值才判定断开。原值 2 太小——后端偶发慢一次，
  // 再叠加一次就显示断开，用户体验为「时不时断十几秒」。放宽到 4，
  // 并配合更短的超时，让「真断开」也能较快识别、偶发抖动能扛过去。
  var FAIL_TOLERANCE = 4;

  function fetchMessages(history) {
    if (pollBusy) {
      // 上一轮未完成：跳过。记一条，便于看出「请求堆积」。
      if (!history) clientLog('poll', 'skip(busy)');
      return;   // 上一轮未完成：跳过本轮，避免并发堆积
    }
    pollBusy = true;
    var _t0 = Date.now();
    // 不再记「start」：每次轮询都记一条纯属噪音，结果已由 slow / fail 表达。
    var url = '/api/web/messages?cursor=' + cursor + '&limit=200';
    if (history) url += '&history=1';
    // 加超时：卡住的请求主动中断，否则 pollBusy 会永久为真、轮询停摆。
    // 由 10 秒收紧到 6 秒：轮询每 2.5 秒一次，6 秒足够正常请求完成；
    // 更短超时让偶发卡顿更快被跳过、更快进入下一轮重试，减少「断开」停留时长。
    var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, 6000);
    fetch(url, { headers: { 'Accept': 'application/json' }, signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        // 正常轮询不记日志（每 2.5 秒一次、量大）；只在响应偏慢时记，
        // 便于发现「变慢的苗头」而不淹没日志。失败仍照常记录。
        var _okms = Date.now() - _t0;
        if (!history && WebLogic.isSlowPoll(_okms, 1000)) clientLog('poll', 'slow ' + _okms + 'ms');
        failCount = 0;
        setStatus(true);
        if (!data || !data.success) return;
        cursor = data.seq || cursor;
        var msgs = data.messages || [];
        // 正序遍历、倒序插入：最终最新在顶部。
        // 历史加载（history）不自动播语音；增量拉取的新语音在解锁后自动播。
        var allowAuto = !history;
        var _rt0 = Date.now();
        msgs.forEach(function (m) { renderMessage(m, allowAuto); });
        var _rt = Date.now() - _rt0;
        // 渲染是主线程同步操作，渲染条数多 / 单条重时会明显占主线程，
        // 这里记渲染条数与耗时：若耗时大，就是「页面卡住」的嫌疑点。
        if (!history && (msgs.length || _rt > 200)) {
          clientLog('render', 'n=' + msgs.length + ' cost=' + _rt + 'ms');
        }
        // 新消息渲染后触发一次待合成扫描：把「生成中」的语音自动轮询、就绪即自动连播
        if (window.WebVoice && window.WebVoice.kick) window.WebVoice.kick();
        // 保持可见区域是最新消息（列表倒序，最新在顶部）
        if (listEl.scrollTop < 40) listEl.scrollTop = 0;
      })
      .catch(function (err) {
        // 失败分类（区分「发不出去」与「发出去了没回应」）由 WebLogic 统一实现，
        // 页面不再内联——同一逻辑在发送路径也复用，避免两处各写一份。
        var kind = WebLogic.classifyFailKind(err && err.name, err && err.message);
        var offline = WebLogic.offlineSuffix(typeof navigator !== 'undefined' ? navigator.onLine : true);
        if (!history) clientLog('poll', 'fail ' + (Date.now() - _t0) + 'ms kind=' + kind + offline + ' failCount=' + (failCount + 1));
        failCount += 1;   // 连续失败超容差才显示断开，避免抖动就闪断
        if (WebLogic.shouldShowDisconnected(failCount, FAIL_TOLERANCE)) setStatus(false);
      })
      .then(function () { clearTimeout(timer); pollBusy = false; });
  }

  function setStatus(ok) {
    dotEl.className = 'dot' + (ok ? ' on' : '');
    statusTextEl.textContent = ok ? '已连接' : '连接断开';
  }

  // ---------- 发送消息（文字与图片一起发出） ----------
  function sendMessage() {
    var text = inputEl.value.trim();
    // 无文字也无图片：不发送
    if (!text && pendingImages.length === 0) return;
    // 快照本次待发内容：失败时可原样恢复，避免消息静默丢失。
    var snapshotText = text;
    var snapshotImgs = pendingImages.slice();
    // 只有发送成功才清空输入与图片；失败则恢复现场并提示。
    // 失败时记录原因类型：超时（已发出无响应）/ 网络错（未发出）/ 服务端错误。
    var finish = function (res, err) {
      if (res && res.ok) { clientLog('send', 'ok'); clearImages(); fetchMessages(false); return; }
      // 失败分类与轮询共用 WebLogic，避免两处各写一份分类逻辑。
      var kind = res ? ('http' + res.status) : WebLogic.classifyFailKind(err && err.name, err && err.message);
      var offline = WebLogic.offlineSuffix(typeof navigator !== 'undefined' ? navigator.onLine : true);
      clientLog('send', 'fail kind=' + kind + offline);
      inputEl.value = snapshotText;
      pendingImages = snapshotImgs;
      renderPreview();
      setStatus(false);
      alert('发送失败，内容已保留在输入框，请检查网络后重试');
    };
    // 发送超时：8 秒未返回即中断，避免按钮永久无反馈。
    var sctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var stimer = setTimeout(function () { if (sctrl) sctrl.abort(); }, 8000);
    var _sopts = { headers: { 'Content-Type': 'application/json' } };
    if (sctrl) _sopts.signal = sctrl.signal;
    inputEl.value = '';
    autoGrow();
    var _done = function () { clearTimeout(stimer); };
    if (pendingImages.length > 0) {
      // 有图片：图文一次性提交（多张一并），避免图片被丢弃
      _sopts.method = 'POST';
      _sopts.body = JSON.stringify({ dataUrls: pendingImages.slice(), text: text });
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

  // ---------- 图片选择（支持一次多张） ----------
  var pendingImages = [];   // 已选图片的 dataURL 数组
  document.getElementById('btnImg').addEventListener('click', function () {
    document.getElementById('fileInput').click();
  });
  document.getElementById('fileInput').addEventListener('change', function (e) {
    // 多选：逐个读为 dataURL，全部读完再统一渲染预览
    var files = Array.prototype.slice.call(e.target.files || []);
    if (!files.length) return;
    var remain = files.length;
    files.forEach(function (f) {
      var reader = new FileReader();
      reader.onload = function () {
        pendingImages.push(reader.result);
        remain--;
        if (remain === 0) renderPreview();
      };
      reader.readAsDataURL(f);
    });
    e.target.value = '';
  });

  /** 渲染已选图片预览：每张配缩略图与移除按钮。 */
  function renderPreview() {
    var box = document.getElementById('preview');
    var list = document.getElementById('previewList');
    list.innerHTML = '';
    pendingImages.forEach(function (url, idx) {
      var wrap = document.createElement('span');
      wrap.className = 'thumb';
      var img = document.createElement('img');
      img.src = url;
      var rm = document.createElement('span');
      rm.className = 'rm';
      rm.textContent = '×';
      rm.addEventListener('click', function () {
        pendingImages.splice(idx, 1);   // 移除该张
        renderPreview();
      });
      wrap.appendChild(img);
      wrap.appendChild(rm);
      list.appendChild(wrap);
    });
    // 有图才显示预览条
    if (pendingImages.length) box.classList.add('on');
    else box.classList.remove('on');
  }

  /** 清空已选图片与预览。 */
  function clearImages() {
    pendingImages = [];
    renderPreview();
  }

  // ---------- 指令展开面板 ----------
  // 点击指令按钮向上展开快捷键列表；点某条指令即填入输入框等待发送。
  // 指令数据从后端 /api/web/commands 取，新增内置指令时面板自动出现。
  var btnCmd = document.getElementById('btnCmd');
  var cmdPanel = document.getElementById('cmdPanel');
  var cmdGrid = document.getElementById('cmdGrid');
  var cmdLoaded = false;

  /** 拉取指令快捷键列表并渲染成分区内网格（内置/自定义，各按首字母排序）。 */
  function loadCommands() {
    fetch('/api/web/commands', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) return;
        var groups = data.groups || { builtin: data.commands || [], custom: [] };
        // 点选即填入输入框并留尾随空格：需要参数的指令便于补参数，其余发送时会被 trim。
        renderCommandPanel(cmdGrid, groups, function (c) {
          inputEl.value = c + ' ';
          inputEl.focus();
          cmdPanel.classList.remove('on');
        });
      })
      .catch(function () { /* 取不到指令时面板为空，不阻断聊天 */ });
  }

  // 展开 / 收起指令面板（首次展开时懒加载指令列表）
  btnCmd.addEventListener('click', function (e) {
    e.preventDefault();
    if (!cmdLoaded) { loadCommands(); cmdLoaded = true; }
    cmdPanel.classList.toggle('on');
  });

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

  // ---------- 首次加载：铺历史 + 启动轮询 ----------
  clientLog('page', 'load 开始首次铺历史');
  fetchMessages(true);
  setInterval(function () { fetchMessages(false); }, 2500);
  // 不再单独发心跳：每 3 秒一条纯属噪音。页面是否仍在运行，
  // 由轮询（slow / fail）与性能监控（tickgap）共同反映——它们异常时才有记录。
  // 性能监控：长任务（主线程被占）与定时器实时间隔。
  // 卡顿时若出现 longtask，是代码卡的；若只有 tickgap、无 longtask，
  // 则更像浏览器/系统冻结了页面 JS。二者日志分不开，靠它区分。
  if (window.WebPerf) window.WebPerf.start();
  // 页面可见性变化打点：切后台时定时器会被系统暂停，这里记下进出时刻，
  // 便于把「断连空档」与「切后台」对齐——若空档两端正好是 hidden/visible，
  // 就是切后台所致，而非页面卡死。
  document.addEventListener('visibilitychange', function () {
    clientLog('page', document.hidden ? 'hidden（切后台）' : 'visible（回前台）');
  });
  // 页面重新可见时立即补拉一次：手机切后台会暂停定时器，
  // 回到前台若不主动拉，会等到下一个周期甚至更久才看到新消息。
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) fetchMessages(false);
  });
})();

