/* ============================================================
 * AI Bridge 扩展 —— 内容脚本（v0.2）
 *
 * 两个职责：
 *   1. 诊断面板：点击各项检查页面是否具备自动化条件（v0.1 已有）
 *   2. 自动接管：轮询手机本地服务，领到任务后替用户打字、等待生成、抓回答案
 *
 * 安全约定：
 *   - 自动接管默认关闭，必须手动点「启动自动接管」才开始轮询
 *   - 诊断面板里的「写入测试文本」永远只写不发
 * ============================================================ */

(function () {
  'use strict';

  // 防止重复注入
  if (window.__aiBridgeDiagLoaded) return;
  window.__aiBridgeDiagLoaded = true;

  // 本地服务地址：QPython 脚本监听的端口
  var LOCAL_API = 'http://127.0.0.1:8000';

  // ---- 站点选择器表 ----
  var PROFILES = [
    {
      name: 'deepseek',
      host: /deepseek\.com/,
      input: ['textarea#chat-input', 'textarea[placeholder]', 'div[contenteditable="true"]'],
      sendBtn: ['div[role="button"].ds-button--primary', 'button[type="submit"]', 'div[role="button"]'],
      assistant: '.ds-markdown.ds-assistant-message-main-content',
      thinking: '.ds-think-content',
      sessionItem: 'a[href*="/a/chat/s/"]'
    },
    {
      name: 'glm',
      host: /chatglm\.(cn|com)/,
      input: ['textarea', 'div[contenteditable="true"]'],
      sendBtn: ['button[type="submit"]', 'div[role="button"]'],
      assistant: '.answer-content-wrap',
      thinking: '.advance-thinking',
      sessionItem: '[class*="session"] a'
    }
  ];

  function activeProfile() {
    var h = location.hostname;
    for (var i = 0; i < PROFILES.length; i++) {
      if (PROFILES[i].host.test(h)) return PROFILES[i];
    }
    return {
      name: '通用',
      input: ['textarea', 'div[contenteditable="true"]', 'input[type="text"]'],
      sendBtn: ['button[type="submit"]', 'div[role="button"]', 'button'],
      assistant: '[class*="markdown"]',
      thinking: '[class*="think"]',
      sessionItem: 'a[href]'
    };
  }

  function findFirst(selectors) {
    for (var i = 0; i < selectors.length; i++) {
      var el = document.querySelector(selectors[i]);
      if (el) return { el: el, sel: selectors[i] };
    }
    return { el: null, sel: '' };
  }

  function textOf(el) {
    return el ? String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim() : '';
  }

  function sleep(ms) {
    return new Promise(function (r) { setTimeout(r, ms); });
  }

  // ---- 面板样式 ----
  function injectStyle() {
    var css = [
      '#aibridge-diag{position:fixed;right:8px;bottom:8px;z-index:2147483647;',
      'width:290px;max-height:76vh;overflow:auto;background:#1b1f27;color:#e6e8ec;',
      'font:12px/1.5 system-ui,sans-serif;border-radius:10px;box-shadow:0 6px 24px rgba(0,0,0,.45);',
      'padding:10px}',
      '#aibridge-diag h4{margin:0 0 8px;font-size:13px;color:#7cc4ff}',
      '#aibridge-diag button{display:block;width:100%;margin:4px 0;padding:7px 9px;',
      'background:#2a3140;color:#e6e8ec;border:1px solid #3a4252;border-radius:6px;',
      'text-align:left;font-size:12px;cursor:pointer}',
      '#aibridge-diag button:active{background:#3a4252}',
      '#aibridge-diag .auto{background:#1d4ed8;border-color:#2563eb}',
      '#aibridge-diag .auto.on{background:#b91c1c;border-color:#dc2626}',
      '#aibridge-out{margin-top:8px;padding:8px;background:#11151b;border-radius:6px;',
      'white-space:pre-wrap;word-break:break-all;max-height:32vh;overflow:auto;font-size:11px}',
      '#aibridge-close{float:right;background:none;border:none;color:#8b93a3;',
      'font-size:14px;cursor:pointer;padding:0 4px}'
    ].join('');
    var s = document.createElement('style');
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  }

  var outEl = null;

  function out(msg) {
    if (!outEl) return;
    outEl.textContent = typeof msg === 'string' ? msg : JSON.stringify(msg, null, 2);
    outEl.scrollTop = 0;
  }

  // ============================================================
  // 诊断项（与 v0.1 相同）
  // ============================================================

  function testInjected() {
    var p = activeProfile();
    out([
      '✅ 扩展已注入页面',
      '站点: ' + p.name,
      'URL: ' + location.href,
      '标题: ' + document.title,
      '可见尺寸: ' + window.innerWidth + ' x ' + window.innerHeight
    ].join('\n'));
  }

  function testDom() {
    var p = activeProfile();
    out([
      'DOM 概况（站点规则: ' + p.name + '）',
      'textarea: ' + document.querySelectorAll('textarea').length,
      'contenteditable: ' + document.querySelectorAll('[contenteditable="true"]').length,
      'button: ' + document.querySelectorAll('button').length,
      'role=button: ' + document.querySelectorAll('[role="button"]').length,
      '',
      '输入框候选: ' + (findFirst(p.input).sel || '（无）'),
      '发送按钮候选: ' + (findFirst(p.sendBtn).sel || '（无）'),
      '正文区命中: ' + document.querySelectorAll(p.assistant).length,
      '思考区命中: ' + document.querySelectorAll(p.thinking).length
    ].join('\n'));
  }

  function testFindInput() {
    var p = activeProfile();
    var hit = findFirst(p.input);
    if (!hit.el) {
      out('❌ 没找到输入框\n尝试过的选择器:\n' + p.input.join('\n'));
      return;
    }
    out([
      '✅ 找到输入框',
      '选择器: ' + hit.sel,
      '标签: ' + hit.el.tagName,
      '可见: ' + (hit.el.offsetParent !== null),
      '尺寸: ' + hit.el.offsetWidth + ' x ' + hit.el.offsetHeight
    ].join('\n'));
  }

  // 把文本写进输入框：用原生 setter 绕过框架拦截，再派发 input 事件
  function writeToInput(el, text) {
    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
      var proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
      setter.call(el, text);
    } else {
      el.innerText = text;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function testWrite() {
    var p = activeProfile();
    var hit = findFirst(p.input);
    if (!hit.el) { out('❌ 先通过「定位输入框」再试'); return; }
    var text = '这是扩展写入的测试文本 ' + new Date().toLocaleTimeString();
    try {
      writeToInput(hit.el, text);
      var now = String(hit.el.value || hit.el.innerText || '');
      out([
        now.indexOf('测试文本') >= 0 ? '✅ 写入成功' : '⚠️ 写入后读取不一致',
        '当前读取: ' + now.slice(0, 80),
        '',
        '未自动发送，避免误发。'
      ].join('\n'));
    } catch (e) {
      out('❌ 写入失败: ' + e.message);
    }
  }

  function testGrabAnswer() {
    var p = activeProfile();
    var nodes = document.querySelectorAll(p.assistant);
    var thinks = document.querySelectorAll(p.thinking);
    if (!nodes.length) {
      out('❌ 没抓到回答\n选择器: ' + p.assistant + '\n先让 AI 回一句话再试');
      return;
    }
    var body = textOf(nodes[nodes.length - 1]);
    var think = thinks.length ? textOf(thinks[thinks.length - 1]) : '';
    out([
      '✅ 抓到回答',
      '正文容器数: ' + nodes.length,
      '正文长度: ' + body.length,
      body.slice(0, 120),
      '',
      '思考长度: ' + think.length,
      think ? think.slice(0, 80) : '（无思考内容）'
    ].join('\n'));
  }

  function testLocalHttp() {
    var url = prompt('本地服务地址', LOCAL_API + '/health');
    if (!url) return;
    out('正在请求 ' + url + ' ...');
    var t0 = Date.now();
    fetch(url, { method: 'GET', mode: 'cors' })
      .then(function (r) {
        out('✅ 本地服务可访问\n状态码: ' + r.status + '\n耗时: ' + (Date.now() - t0) + ' ms');
      })
      .catch(function (e) {
        out('❌ 请求失败\n错误: ' + e.message + '\n\n检查：服务是否在跑、端口对不对、CORS 是否允许');
      });
  }

  function testTokenInfo() {
    var body = document.body ? (document.body.innerText || '') : '';
    var patterns = [/tokens?\s*[:：]\s*\d+/gi, /\d+\s*tokens?/gi, /用量\s*[:：]\s*\d+/g];
    var hits = [];
    patterns.forEach(function (re) {
      var m = body.match(re);
      if (m) hits = hits.concat(m);
    });
    out(hits.length
      ? ('⚠️ 页面出现疑似用量文本\n命中: ' + hits.slice(0, 5).join(' / '))
      : '❌ 页面上没有 token 用量信息\n结论：接口只能返回估算值');
  }

  // ============================================================
  // 自动接管：轮询任务 → 打字 → 等生成 → 抓回答案
  // ============================================================

  var polling = false;       // 轮询开关
  var busy = false;          // 是否正在处理一个任务
  var fetching = false;      // 是否已有一个「取任务」请求在飞
  var pollTimer = null;

  // 轮询主循环：每 2 秒问一次有没有活
  // fetching 与 busy 缺一不可：
  //   busy 防止「处理中又去领新任务」，
  //   fetching 防止「上一次取任务还没返回、下一次又发出去」——
  //   后者在网络慢时会同时领到两个任务，在页面上互相打架。
  function pollLoop() {
    if (!polling || busy || fetching) return;
    fetching = true;
    fetch(LOCAL_API + '/ext/get_task', { mode: 'cors' })
      .then(function (r) { return r.json(); })
      .then(function (task) {
        fetching = false;
        if (!task || !task.task_id) return;
        busy = true;
        out('📥 领到任务 ' + task.task_id.slice(0, 8) + '\n内容: ' + String(task.prompt).slice(0, 60));
        handleTask(task)
          .catch(function (e) {
            out('❌ 处理任务失败: ' + e.message);
            // 失败也要回传，避免服务端一直等
            return submitResult(task.task_id, '', '', e.message);
          })
          .then(function () { busy = false; });
      })
      .catch(function () {
        // 服务没开或网络抖动：必须清掉在途标记，否则轮询会永久卡死。
        // 这是本轮修复的关键：只在成功分支清标记，请求一失败就再也不发新请求了。
        fetching = false;
      });
  }

  // 提交结果给本地服务
  function submitResult(taskId, content, thinking, error) {
    return fetch(LOCAL_API + '/ext/submit_result', {
      method: 'POST',
      mode: 'cors',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task_id: taskId,
        content: content || '',
        thinking: thinking || '',
        error: error || ''
      })
    }).then(function (r) { return r.json(); });
  }

  // 处理一个任务：写入 → 发送 → 等新消息 → 等生成结束 → 抓取 → 回传
  async function handleTask(task) {
    var p = activeProfile();

    // 1. 定位输入框
    var hit = findFirst(p.input);
    if (!hit.el) throw new Error('找不到输入框');

    // 2. 记录发送前的回答数量，用于判断新回答何时出现
    var beforeCount = document.querySelectorAll(p.assistant).length;

    // 3. 写入提问
    writeToInput(hit.el, task.prompt);
    await sleep(400);

    // 4. 发送：优先点发送按钮，找不到就回车
    var btn = findFirst(p.sendBtn);
    if (btn.el) {
      btn.el.click();
    } else {
      hit.el.dispatchEvent(new KeyboardEvent('keydown', {
        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
      }));
    }
    out('📤 已发送，等待回答...');

    // 5. 等新回答出现（最多 20 秒）
    var t0 = Date.now();
    while (Date.now() - t0 < 20000) {
      if (document.querySelectorAll(p.assistant).length > beforeCount) break;
      await sleep(500);
    }
    if (document.querySelectorAll(p.assistant).length <= beforeCount) {
      throw new Error('20 秒内未检测到新回答');
    }

    // 6. 等生成结束：文本连续 2 秒不变即认为稳定（最多再等 150 秒）
    var last = '';
    var stableSince = Date.now();
    var deadline = Date.now() + 150000;
    while (Date.now() < deadline) {
      var nodes = document.querySelectorAll(p.assistant);
      var cur = textOf(nodes[nodes.length - 1]);
      if (cur !== last) {
        last = cur;
        stableSince = Date.now();
      } else if (cur.length > 0 && Date.now() - stableSince > 2000) {
        break;
      }
      await sleep(500);
    }

    // 7. 抓思考内容
    var thinks = document.querySelectorAll(p.thinking);
    var think = thinks.length ? textOf(thinks[thinks.length - 1]) : '';

    // 8. 回传
    await submitResult(task.task_id, last, think, '');
    out('✅ 任务完成\n正文长度: ' + last.length + '\n思考长度: ' + think.length);
  }

  // 开关自动接管
  function toggleAuto(btnEl) {
    polling = !polling;
    if (polling) {
      btnEl.textContent = '⏹ 停止自动接管';
      btnEl.classList.add('on');
      out('🤖 自动接管已启动\n将每 2 秒向本地服务领一次任务');
      pollTimer = setInterval(pollLoop, 2000);
    } else {
      btnEl.textContent = '▶ 启动自动接管';
      btnEl.classList.remove('on');
      out('⏸ 自动接管已停止');
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }
  }

  // ============================================================
  // 组装面板
  // ============================================================

  function buildPanel() {
    injectStyle();
    var box = document.createElement('div');
    box.id = 'aibridge-diag';

    var title = document.createElement('h4');
    title.textContent = 'AI Bridge';
    var close = document.createElement('button');
    close.id = 'aibridge-close';
    close.textContent = '✕';
    close.style.cssText = 'width:auto;margin:0;padding:0 4px;background:none;border:none';
    close.onclick = function () { box.style.display = 'none'; };
    title.appendChild(close);
    box.appendChild(title);

    // 自动接管开关（置顶，最常用）
    var autoBtn = document.createElement('button');
    autoBtn.className = 'auto';
    autoBtn.textContent = '▶ 启动自动接管';
    autoBtn.onclick = function () { toggleAuto(autoBtn); };
    box.appendChild(autoBtn);

    // 诊断项
    var tests = [
      ['0.1 注入检查', testInjected],
      ['0.2 DOM 概况', testDom],
      ['0.3 定位输入框', testFindInput],
      ['0.4 写入测试文本', testWrite],
      ['0.5 抓取最后回答', testGrabAnswer],
      ['0.6 连本地服务', testLocalHttp],
      ['0.7 找 token 用量', testTokenInfo]
    ];
    tests.forEach(function (t) {
      var b = document.createElement('button');
      b.textContent = t[0];
      b.onclick = function () {
        try { t[1](); } catch (e) { out('❌ 异常: ' + e.message); }
      };
      box.appendChild(b);
    });

    outEl = document.createElement('div');
    outEl.id = 'aibridge-out';
    outEl.textContent = '先跑诊断，确认各项可用后再启动自动接管。';
    box.appendChild(outEl);

    document.body.appendChild(box);
  }

  if (document.body) {
    buildPanel();
  } else {
    document.addEventListener('DOMContentLoaded', buildPanel);
  }
})();
