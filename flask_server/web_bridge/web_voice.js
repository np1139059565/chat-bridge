/* ============================================================
 * 网页版机器人 —— 语音子系统
 * 职责：
 *   1. 渲染语音区（已合成 / 待合成两种形态）
 *   2. 按需合成：点播时若音频未生成，调后端触发合成并轮询，
 *      就绪后自动接上播放——合成在后端后台线程跑，不阻塞任何接口
 *   3. 播放队列：同一时刻只播一条、条间留间隔；用户点播可顺时续播
 *   4. 已播放标记（localStorage 持久化）
 * 说明：从 web_page.js 抽出，使主脚本保持在仓库行数上限内。
 *       对外暴露 window.WebVoice.renderAudio(m) 与 WebVoice.bind(au, allowAuto)。
 * ============================================================ */
(function () {
  'use strict';
  var listEl = document.getElementById('list');

  // ---------- 已播放标记：以消息 seq 为键，存 localStorage，刷新后仍在 ----------
  // 目的：让用户一眼看出哪些语音听过、从哪继续。
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

  /** 标记某条语音已播放，并落盘、同步界面标记。 */
  function markVoicePlayed(seq) {
    var k = String(seq || 0);
    if (playedSeqs[k]) return;
    playedSeqs[k] = 1;
    try { localStorage.setItem(PLAYED_KEY, JSON.stringify(playedSeqs)); } catch (e) { /* 存不下则仅内存 */ }
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

  // ---------- 播放队列状态 ----------
  var unlocked = false;      // 自动播放是否已解锁（用户点过任意一条）
  var lockedByClose = false; // 是否因用户主动关闭而重新上锁
  var autoQueue = [];        // 待自动播放的音频队列
  var playing = null;        // 当前正在播放的音频（同一时刻最多一条）
  var VOICE_GAP_MS = 700;    // 两条语音之间的停顿：不留间隔会连成一条超长语音
  var gapTimer = null;       // 间隔计时器

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
   * 不依赖状态变量、直接扫 DOM——状态与事件时序一旦错位，守卫就会失效、
   * 多条音频同时出声；直接扫 DOM 从根上杜绝。
   */
  function pauseOthers(keep) {
    var all = listEl.querySelectorAll('audio');
    for (var i = 0; i < all.length; i++) {
      var a = all[i];
      if (a !== keep && !a.paused) {
        a._progPause = true;   // 标程序暂停，避免被 pause 处理器当成用户主动关闭
        try { a.pause(); } catch (e) { /* 忽略 */ }
      }
    }
  }

  /** 尝试从队列取出下一条播放。有在播 / 未解锁 / 被关闭上锁时都不播。 */
  function pumpQueue() {
    if (playing) return;                     // 有在播，等它 ended 再继续
    if (!unlocked || lockedByClose) return;  // 未解锁或已被用户关闭
    var au = autoQueue.shift();
    if (!au) return;
    playing = au;
    pauseOthers(au);                         // 开播前先把其它全部停掉
    au._progPlay = true;                     // 标记：本次播放由程序发起
    var p = au.play();
    if (p && p.catch) p.catch(function () {
      // 被浏览器拦截或瞬时加载失败：释放占用。不再静默丢弃——
      // 复位后该条仍在列表里，用户可再点一次；并在 flag 上给出提示。
      playing = null;
      au._progPlay = false;
      au._progPause = false;
      var wrap = au.closest('.voice-wrap');
      var flag = wrap && wrap.querySelector('.voice-flag');
      if (flag) flag.textContent = '播放受阻，请再点一次';
    });
  }

  /** 播完一条后，停顿 VOICE_GAP_MS 再播下一条（留出间隔）。 */
  function scheduleNext() {
    if (gapTimer) clearTimeout(gapTimer);
    gapTimer = setTimeout(function () {
      gapTimer = null;
      pumpQueue();
    }, VOICE_GAP_MS);
  }

  // ---------- 渲染语音区 HTML ----------
  /**
   * 生成一条消息的语音区 HTML：已合成出播放器，未合成出「生成」按钮。
   * @param m 收件箱消息对象（含 seq / voice / voice_text）
   * @returns 语音区 HTML；无语音返回空串
   */
  function renderAudio(m) {
    var seq = m.seq || 0;
    if (m.voice) {
      var played = isVoicePlayed(seq);
      return '<div class="voice-wrap' + (played ? ' played' : '') + '" data-seq="' + seq + '">' +
        '<span class="voice-flag">' + (played ? '已播放' : '未播放') + '</span>' +
        '<audio controls preload="none" data-seq="' + seq + '" src="/api/web/audio/' +
        encodeURIComponent(m.voice) + '"></audio></div>';
    }
    if (m.voice_text) {
      // 待合成：显示「生成中」，由 scanPending 自动轮询，无需用户点击。
      // 合成在后端入库时已自动启动（见 web_mirror.schedule_auto_synth）。
      return '<div class="voice-wrap pending" data-seq="' + seq + '">' +
        '<span class="voice-flag">生成中…</span></div>';
    }
    return '';
  }

  /** 造一个绑定好 src 的 audio 元素。 */
  function makeAudio(seq, name) {
    var au = document.createElement('audio');
    au.controls = true;
    au.preload = 'none';
    au.setAttribute('data-seq', seq);
    au.src = '/api/web/audio/' + encodeURIComponent(name);
    return au;
  }

  /** 把「待合成」区替换成真正的播放器，并按需自动播放。 */
  function fillReady(wrap, seq, name, autoPlay) {
    var played = isVoicePlayed(seq);
    wrap.className = 'voice-wrap' + (played ? ' played' : '');
    wrap.innerHTML = '<span class="voice-flag">' + (played ? '已播放' : '未播放') + '</span>';
    var au = makeAudio(seq, name);
    wrap.appendChild(au);
    bind(au, !!autoPlay);
  }

  /** 更新待合成区的状态文字。 */
  function setFlag(wrap, text) {
    var f = wrap.querySelector('.voice-flag');
    if (f) f.textContent = text;
  }

  /**
   * 轮询某条语音是否合成完毕；就绪则换成播放器。
   * @param tries 剩余轮询次数（约 1.5 秒一次）
   */
  function pollVoice(seq, wrap, tries, done) {
    function finish() { if (done) done(); }
    if (tries <= 0) { setFlag(wrap, '生成失败'); finish(); return; }
    setTimeout(function () {
      fetch('/api/web/voice-status?seq=' + seq)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.status === 'ready') { fillReady(wrap, seq, d.name, true); finish(); }
          else { pollVoice(seq, wrap, tries - 1, done); }
        })
        .catch(function () { pollVoice(seq, wrap, tries - 1, done); });
    }, 1500);
  }

  // ---------- 自动扫描待合成语音 ----------
  // 设计要点：合成由后台自动完成，前端只负责「发现有生成中的语音 → 轮询 → 就绪即自动播」。
  // 全程无需用户点击；网络慢只导致延迟出声，不影响自动连播。
  var scanning = false;

  /** 扫描页面上所有「生成中」的语音区，逐个轮询直到就绪。 */
  function scanPending() {
    if (scanning) return;
    var wraps = listEl.querySelectorAll('.voice-wrap.pending');
    if (!wraps.length) return;
    scanning = true;
    var pending = 0, done = 0;
    Array.prototype.forEach.call(wraps, function (wrap) {
      // 已在轮询中的跳过（用 _polling 标记）
      if (wrap._polling) return;
      wrap._polling = true;
      pending += 1;
      var seq = parseInt(wrap.getAttribute('data-seq') || '0', 10);
      // 就绪后自动接播（此时若已解锁，会按队列顺序自动播）
      pollVoice(seq, wrap, 40, function () {
        done += 1;
        if (done >= pending) scanning = false;
      });
    });
    if (!pending) scanning = false;
  }

  // 对外暴露：消息渲染后由页面脚本调用，触发一次扫描
  function kick() { setTimeout(scanPending, 300); }

  // ---------- 播放事件绑定（解锁 / 续播 / 关闭上锁） ----------
  // 规则（用户拍板）：
  // - 点任意一条语音播放 → 解锁自动播放，之后新到的语音自动播；
  // - 主动关闭任意一条语音 → 关闭自动播放，重新上锁。
  function bind(au, allowAuto) {
    // 播放事件：区分「程序自动播」与「用户手动点击播」
    au.addEventListener('play', function () {
      // 开始播放即标记已播放（点一下就算听过，不必等播完）
      markVoicePlayed(au.getAttribute('data-seq'));
      // 开始播放即自动定位：把正在播放的语音滚进可视区
      try { au.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } catch (e) { /* 老浏览器忽略 */ }
      if (au._progPlay) { au._progPlay = false; return; }   // 程序发起，已在队列登记
      // 用户手动点播：解锁、停掉其余、清空旧队列，并把「这条及之后」依次入队
      unlocked = true; lockedByClose = false;
      if (playing && playing !== au) {
        playing._progPause = true;   // pause 事件异步触发，标记交给事件处理器重置
        try { playing.pause(); } catch (e) { /* 忽略 */ }
      }
      playing = au;
      autoQueue = [];
      voicesFrom(au).forEach(function (a) {
        if (a !== au) autoQueue.push(a);   // 当前这条在播，其余排队
      });
    });
    // 暂停事件：区分「程序暂停」与「用户主动关闭」
    au.addEventListener('pause', function () {
      if (au._progPause) { au._progPause = false; return; }   // 程序暂停，不上锁
      if (!au.ended) {   // 用户主动暂停：关闭自动播放、上锁、清队列与计时
        unlocked = false; lockedByClose = true; autoQueue = [];
        if (gapTimer) { clearTimeout(gapTimer); gapTimer = null; }
      }
      if (playing === au) playing = null;
    });
    // 播放结束：标记已播放、释放占用、间隔后播下一条
    au.addEventListener('ended', function () {
      markVoicePlayed(au.getAttribute('data-seq'));
      if (playing === au) playing = null;
      scheduleNext();
    });
    // 自动播放：入队由队列统一调度，不在这里直接播
    if (allowAuto && unlocked && !lockedByClose) {
      autoQueue.push(au);
      pumpQueue();
    }
  }

  // ---------- 对外接口 ----------
  window.WebVoice = { renderAudio: renderAudio, bind: bind, kick: kick };
})();
