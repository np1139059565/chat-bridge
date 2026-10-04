/* ============================================================
 * 网页版机器人 —— 前端逻辑
 * 职责：拉取消息、倒序渲染、Markdown 解析、指令链接、语音自动播放
 * ============================================================ */
(function () {
  'use strict';
  var renderMarkdown = window.WebRender.renderMarkdown;

  // ---------- 全局状态 ----------
  var cursor = 0;            // 已拉取到的最大 seq
  var unlocked = false;      // 语音自动播放是否已解锁
  var lockedByClose = false; // 是否因用户关闭语音而主动上锁
  var seen = {};             // 已渲染消息 id，防重复
  var lastRenderedTs = 0;    // 最后一条渲染消息的时间戳（判断是否该吸顶）

  var listEl = document.getElementById('list');
  var inputEl = document.getElementById('input');
  var dotEl = document.getElementById('dot');
  var statusTextEl = document.getElementById('statusText');

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
    if (m.kind === 'web-image' || m.text === '[图片]') {
      body = '<span class="img-badge">🖼 图片</span>';
    } else {
      body = renderMarkdown(m.text || '');
    }
    // 语音：带 voice 字段时渲染播放器；已播过的加标记（见 playedSeqs）
    var audio = '';
    if (m.voice) {
      var played = isVoicePlayed(m.seq);
      // data-seq：该消息的时间序号。点播时据此定位「这条之后还有哪些」以续播。
      audio = '<div class="voice-wrap' + (played ? ' played' : '') + '">' +
        '<span class="voice-flag">' + (played ? '已播放' : '未播放') + '</span>' +
        '<audio controls preload="none" data-seq="' + (m.seq || 0) + '" src="/api/web/audio/' + encodeURIComponent(m.voice) + '"></audio>' +
        '</div>';
    }
    el.innerHTML =
      '<div class="who">' + who + '<span class="time">' + fmtTime(m.ts) + '</span></div>' +
      '<div class="body">' + body + '</div>' + audio;
    // 倒序：最新插入到列表最前面
    if (listEl.firstChild) listEl.insertBefore(el, listEl.firstChild);
    else listEl.appendChild(el);
    // 语音播放器：绑定解锁与自动播放（历史语音不自动播，见 allowAuto）
    var au = el.querySelector('audio');
    if (au) bindAudio(au, !!allowAuto);
    return true;
  }

  // ---------- 语音播放：解锁与自动播放 ----------
  // 规则（用户拍板）：
  // - 用户点击任意一条语音播放 → 解锁自动播放，之后新到的语音自动播；
  // - 用户主动关闭任意一条语音 → 关闭自动播放，重新上锁。
  //
  // 自动播放必须「排队」而非「抢播」：增量拉取时多条语音可能同一时刻到达，
  // 若每条各自调用播放，会出现「前一条没播完，后一条就抢着响」。
  // 因此用一条队列串起来：当前无人在播时才播队首，一条播完（ended）再播下一条。
  // ---------- 已播放语音标记（持久化到 localStorage） ----------
  // 目的：让用户一眼看出哪些语音听过、从哪继续。
  // 以消息 seq 为键记录；用 localStorage 而非内存，刷新后标记仍在。
  var PLAYED_KEY = 'webVoicePlayed';
  var playedSeqs = (function () {
    try {
      var raw = localStorage.getItem(PLAYED_KEY);
      var obj = raw ? JSON.parse(raw) : {};
      // 兜底：非对象（如旧版存了数组）一律重置为空集合，避免后续判断出错
      return (obj && typeof obj === 'object' && !Array.isArray(obj)) ? obj : {};
    } catch (e) { return {}; }
  })();

  /** 判断某条语音是否已播放。 */
  function isVoicePlayed(seq) {
    return !!playedSeqs[String(seq || 0)];
  }

  /** 标记某条语音已播放，并落盘。 */
  function markVoicePlayed(seq) {
    var k = String(seq || 0);
    if (playedSeqs[k]) return;
    playedSeqs[k] = 1;
    try { localStorage.setItem(PLAYED_KEY, JSON.stringify(playedSeqs)); } catch (e) { /* 存不下则仅内存 */ }
    // 同步更新界面标记（找到对应播放器容器）
    var au = listEl.querySelector('audio[data-seq="' + seq + '"]');
    if (au) {
      var wrap = au.closest('.voice-wrap');
      if (wrap) {
        wrap.classList.add('played');
        var flag = wrap.querySelector('.voice-flag');
        if (flag) flag.textContent = '已播放';
      }
    }
  }

  var autoQueue = [];   // 待自动播放的音频队列
  var playing = null;   // 当前正在播放的音频（同一时刻最多一条）
  // 两条语音之间的停顿（毫秒）：不留间隔会听起来连成一条超长语音。
  var VOICE_GAP_MS = 700;
  var gapTimer = null;  // 间隔计时器

  /**
   * 取「某条及其之后」的全部语音元素，按时间序号升序。
   * 用途：用户从历史某条点播时，把这条之后的依次续播，而不是只播这一条。
   * @param au 起点音频元素
   * @returns 音频元素数组（含起点），按 seq 从小到大
   */
  function voicesFrom(au) {
    var cur = parseInt(au.getAttribute('data-seq') || '0', 10);
    var all = Array.prototype.slice.call(listEl.querySelectorAll('audio[data-seq]'));
    all.sort(function (a, b) {
      return parseInt(a.getAttribute('data-seq') || '0', 10) - parseInt(b.getAttribute('data-seq') || '0', 10);
    });
    return all.filter(function (a) {
      return parseInt(a.getAttribute('data-seq') || '0', 10) >= cur;
    });
  }

  /**
   * 兜底互斥：暂停页面上除 keep 之外所有正在播放的音频。
   * 不依赖 playing 等状态变量，直接扫 DOM——状态变量与事件时序一旦错位，
   * 守卫就会失效、多条音频同时出声；直接扫 DOM 从根上杜绝。
   * @param {HTMLAudioElement} keep 要保持播放的那条
   */
  function pauseOthers(keep) {
    var all = listEl.querySelectorAll('audio');
    for (var i = 0; i < all.length; i++) {
      var a = all[i];
      if (a !== keep && !a.paused) {
        // 标 _progPause，避免被 pause 处理器当成「用户主动关闭」而上锁
        a._progPause = true;
        try { a.pause(); } catch (e) { /* 忽略 */ }
      }
    }
  }

  /** 尝试从队列取出下一条播放。有在播 / 未解锁 / 被关闭上锁时都不播。 */
  function pumpQueue() {
    if (playing) return;         // 有在播，等它 ended 再继续
    if (!unlocked || lockedByClose) return;  // 未解锁或已被用户关闭
    var au = autoQueue.shift();
    if (!au) return;
    playing = au;
    pauseOthers(au);             // 开播前先把其它全部停掉，确保同一时刻只此一条
    au._progPlay = true;         // 标记：本次播放由程序发起
    var p = au.play();
    if (p && p.catch) p.catch(function () {
      // 被浏览器拦截（未解锁等）：释放占用、清掉程序标记，等待用户手动点击
      playing = null;
      au._progPlay = false;
      au._progPause = false;
    });
  }

  /** 播完一条后，停顿 VOICE_GAP_MS 再播下一条（留出间隔，避免连成一条）。 */
  function scheduleNext() {
    if (gapTimer) clearTimeout(gapTimer);
    gapTimer = setTimeout(function () {
      gapTimer = null;
      pumpQueue();
    }, VOICE_GAP_MS);
  }

  // @param allowAuto 该条是否允许自动播放（历史语音为 false）
  function bindAudio(au, allowAuto) {
    // 播放事件：区分「程序自动播」与「用户手动点击播」。
    au.addEventListener('play', function () {
      // 开始播放即自动定位：把正在播放的语音滚进可视区。
      // block:'nearest' 温和——已在可视区时不动，避免每次小幅跳动。
      try { au.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (e) { /* 老浏览器忽略 */ }
      // 程序发起：已在 pumpQueue 里登记，不重复处理
      if (au._progPlay) { au._progPlay = false; return; }
      // 用户手动点播：解锁、停掉其余、清空旧队列，
      // 并把「这条及其之后」的语音依次入队——从历史点播也能顺时间续播。
      unlocked = true; lockedByClose = false;
      if (playing && playing !== au) {
        // 标 _progPause 后交给 pause 事件处理器重置：
        // pause 事件是异步触发的，若在此同步重置标记，事件到达时会误判为用户主动关闭。
        playing._progPause = true;
        try { playing.pause(); } catch (e) { /* 忽略 */ }
      }
      playing = au;
      autoQueue = [];
      voicesFrom(au).forEach(function (a) {
        if (a !== au) autoQueue.push(a);   // 当前这条在播，其余排队
      });
    });
    // 暂停事件：区分「程序暂停」与「用户主动关闭」。
    au.addEventListener('pause', function () {
      // 程序暂停：不算用户主动关闭，不上锁
      if (au._progPause) { au._progPause = false; return; }
      // 用户主动暂停：关闭自动播放、重新上锁，并清空待播队列与间隔计时
      if (!au.ended) {
        unlocked = false; lockedByClose = true; autoQueue = [];
        if (gapTimer) { clearTimeout(gapTimer); gapTimer = null; }
      }
      if (playing === au) playing = null;
    });
    // 播放结束：标记已播放，释放占用，间隔后再播队列里的下一条（等播完 + 留间隔）。
    au.addEventListener('ended', function () {
      markVoicePlayed(au.getAttribute('data-seq'));
      if (playing === au) playing = null;
      scheduleNext();
    });
    // 自动播放：入队，由队列统一调度，不在这里直接播。
    if (allowAuto && unlocked && !lockedByClose) {
      autoQueue.push(au);
      pumpQueue();
    }
  }

  // ---------- 指令链接：点击复制到输入框 ----------
  listEl.addEventListener('click', function (e) {
    var t = e.target;
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
  function fetchMessages(history) {
    var url = '/api/web/messages?cursor=' + cursor + '&limit=200';
    if (history) url += '&history=1';
    fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        setStatus(true);
        if (!data || !data.success) return;
        cursor = data.seq || cursor;
        var msgs = data.messages || [];
        // 正序遍历、倒序插入：最终最新在顶部。
        // 历史加载（history）不自动播语音；增量拉取的新语音在解锁后自动播。
        var allowAuto = !history;
        msgs.forEach(function (m) { renderMessage(m, allowAuto); });
        // 保持可见区域是最新消息（列表倒序，最新在顶部）
        if (listEl.scrollTop < 40) listEl.scrollTop = 0;
      })
      .catch(function () { setStatus(false); });
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
    inputEl.value = '';
    autoGrow();
    // 发送完成后的收尾：清空已选图片并立即拉取
    var finish = function () { clearImages(); fetchMessages(false); };
    if (pendingImages.length > 0) {
      // 有图片：图文一次性提交（多张一并），避免图片被丢弃
      fetch('/api/web/image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataUrls: pendingImages.slice(), text: text })
      }).then(finish);
    } else {
      fetch('/api/web/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
      }).then(finish);
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

  // ---------- 录音（按住录音，松开发送） ----------
  var mediaRec = null, chunks = [], recording = false;
  var btnRec = document.getElementById('btnRec');
  function startRec() {
    if (recording) return;
    // 安全上下文检查：浏览器只在 https 或 localhost 下允许麦克风。
    // 局域网 http 访问时明确提示原因，避免用户以为功能坏了。
    var secure = window.isSecureContext ||
      location.protocol === 'https:' ||
      location.hostname === 'localhost' ||
      location.hostname === '127.0.0.1';
    if (!secure) {
      alert('当前用 http 访问，浏览器禁止使用麦克风。\n录音需要 https 或本机访问。\n文字、图片、语音播放不受影响。');
      return;
    }
    if (!navigator.mediaDevices || !window.MediaRecorder) { alert('浏览器不支持录音'); return; }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      chunks = [];
      mediaRec = new MediaRecorder(stream);
      mediaRec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      mediaRec.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        var blob = new Blob(chunks, { type: 'audio/webm' });
        uploadVoice(blob);
      };
      mediaRec.start();
      recording = true;
      btnRec.classList.add('rec');
      document.getElementById('recTip').classList.add('on');
    }).catch(function () { alert('无法访问麦克风'); });
  }
  function stopRec() {
    if (!recording || !mediaRec) return;
    recording = false;
    btnRec.classList.remove('rec');
    document.getElementById('recTip').classList.remove('on');
    try { mediaRec.stop(); } catch (e) {}
  }
  btnRec.addEventListener('touchstart', function (e) { e.preventDefault(); startRec(); });
  btnRec.addEventListener('touchend', function (e) { e.preventDefault(); stopRec(); });
  btnRec.addEventListener('mousedown', function (e) { e.preventDefault(); startRec(); });
  btnRec.addEventListener('mouseup', function (e) { e.preventDefault(); stopRec(); });

  // 上传语音：转 base64 后交给后端（后端落盘并尝试识别）
  function uploadVoice(blob) {
    var reader = new FileReader();
    reader.onload = function () {
      var b64 = String(reader.result).split(',')[1] || '';
      fetch('/api/web/voice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ audio: b64, format: 'webm' })
      }).then(function () { fetchMessages(false); });
    };
    reader.readAsDataURL(blob);
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

  // ---------- 首次加载：铺历史 + 启动轮询 ----------
  fetchMessages(true);
  setInterval(function () { fetchMessages(false); }, 2500);
})();

