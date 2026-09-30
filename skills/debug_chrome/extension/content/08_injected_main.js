// 模块：content/08_injected_main.js
// 用途：运行在页面「主世界」的脚本，向页面暴露 window.selectAiDebugElement(el)，
//       让用户能对无法用鼠标点选（被遮挡、pointer-events:none、动态生成）的元素，
//       自行取到 DOM 对象后直接触发选中。
// 关键约束：DOM 元素无法跨 world 传递。主世界拿不到隔离世界的选中逻辑，隔离世界
//       也拿不到主世界的元素引用，因此这里只给元素打一个一次性标记，再通过
//       postMessage 通知隔离世界的内容脚本按标记找回元素并完成选中。
// 加载方式：由内容脚本 07_index.js 以 <script src=...> 注入；同一页面只定义一次。
(function () {
  'use strict';
  // 已注入过则不重复定义（页面可能被多次注入，例如扩展重载）
  if (window.__AI_STYLE_DEBUG_MAIN__) return;
  window.__AI_STYLE_DEBUG_MAIN__ = true;

  // 临时标记属性名：内容脚本据此跨 world 找回同一个元素。
  // 用 data- 前缀，避免与页面自身属性冲突；用后即删，不留痕。
  var MARK_ATTR = 'data-ai-debug-pick';

  /**
   * 传入一个 DOM 元素即可触发选中，无需鼠标点选。
   * 元素可来自顶层文档，也可来自（同源）iframe 文档——通过 el.ownerDocument
   * 判定它所属的文档与 URL，选择结果会带上该文档地址，便于定位与路由。
   * @param {Element} el 目标 DOM 元素
   * @returns {boolean} 是否已成功发出选中请求
   */
  window.selectAiDebugElement = function (el) {
    // 只接受元素节点，拒绝文本 / 注释 / null 等无效入参
    if (!el || el.nodeType !== 1) {
      console.warn('[AI Style Debug] selectAiDebugElement: 请传入一个 DOM 元素');
      return false;
    }
    // 元素所属文档：可能不是顶层文档（元素在 iframe 内时）
    var doc = el.ownerDocument || document;
    // 生成一次性标记：时间戳 + 随机数，保证同页多次调用互不冲突
    var mark = 'ai-debug-pick-' + Date.now() + '-' + Math.floor(Math.random() * 1e9);
    try {
      el.setAttribute(MARK_ATTR, mark);
    } catch (e) {
      // 某些只读 / 冻结元素可能拒绝写属性，此时无法用标记法定位，直接失败
      console.warn('[AI Style Debug] selectAiDebugElement: 无法在元素上打标记', e);
      return false;
    }
    // 把标记与元素所属文档 URL 发给顶层内容脚本：
    // 内容脚本运行在顶层文档，故用 window.top 作为投递目标。
    var target = window.top || window;
    target.postMessage({
      source: 'ai-debug-main',
      type: 'select-by-mark',
      mark: mark,
      url: (doc.location && doc.location.href) || ''
    }, '*');
    return true;
  };

  // ============ console 记录钩子 ============
  // DevTools 面板无法回看历史 console，必须在页面侧先捕获。
  // 这里 hook console 的常用方法，把调用记录进环形缓冲，
  // 供 AI 通过工具读取（读取走 exec_js 或 DevTools 聚合）。
  var CONSOLE_MAX = 500;
  window.__AI_DEBUG_CONSOLE_LOGS = window.__AI_DEBUG_CONSOLE_LOGS || [];
  (function hookConsole() {
    if (window.__AI_DEBUG_CONSOLE_HOOKED__) return;
    window.__AI_DEBUG_CONSOLE_HOOKED__ = true;
    var methods = ['log', 'info', 'warn', 'error', 'debug'];
    methods.forEach(function (m) {
      var orig = console[m];
      if (typeof orig !== 'function') return;
      console[m] = function () {
        try {
          var args = Array.prototype.slice.call(arguments).map(function (a) {
            return safeSerialize(a, 0, []);
          });
          window.__AI_DEBUG_CONSOLE_LOGS.push({
            level: m,
            args: args,
            time: Date.now()
          });
          // 环形缓冲：超出上限丢弃最旧的
          if (window.__AI_DEBUG_CONSOLE_LOGS.length > CONSOLE_MAX) {
            window.__AI_DEBUG_CONSOLE_LOGS.splice(0, window.__AI_DEBUG_CONSOLE_LOGS.length - CONSOLE_MAX);
          }
        } catch (e) { /* 记录失败不影响原 console 行为 */ }
        return orig.apply(console, arguments);
      };
    });
  })();

  // ============ 执行 JS（供 AI 探查与控制页面） ============
  // 运行在主世界：这里能访问页面真实的 window / document / localStorage 等，
  // 隔离世界的内容脚本访问不到这些（拿到的是隔离副本）。
  // 内容脚本通过 postMessage 投递代码，执行结果序列化后回传。

  var MAX_DEPTH = 4;        // 序列化最大深度，防止深对象把结果撑爆
  var MAX_ITEMS = 100;      // 数组/对象最多列举的元素个数

  /**
   * 把任意值序列化为可跨 world 传递的安全结构。
   * 元素、函数、循环引用无法直接传，转成可读描述或截断标记。
   * @param {*} val 待序列化值
   * @param {number} depth 当前递归深度
   * @param {Array} seen 已访问对象（循环引用检测）
   * @returns {*} 可序列化结果
   */
  function safeSerialize(val, depth, seen) {
    depth = depth || 0;
    seen = seen || [];
    if (val === null || val === undefined) return val;
    var t = typeof val;
    if (t === 'string' || t === 'number' || t === 'boolean') return val;
    if (t === 'function') return '[Function ' + (val.name || 'anonymous') + ']';
    if (t === 'symbol') return String(val);
    if (t === 'bigint') return String(val) + 'n';
    // DOM 元素 / 节点：返回标签、选择器与外形摘要，避免整棵子树外传
    if (val.nodeType === 1) {
      var rect = null;
      try { rect = val.getBoundingClientRect(); } catch (e) {}
      return {
        __type: 'Element',
        tag: (val.tagName || '').toLowerCase(),
        id: val.id || '',
        className: (typeof val.className === 'string' ? val.className : ''),
        text: (val.textContent || '').slice(0, 200),
        rect: rect ? { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) } : null
      };
    }
    if (val.nodeType) return '[Node type=' + val.nodeType + ']';
    if (depth >= MAX_DEPTH) return '[MaxDepth]';
    if (seen.indexOf(val) !== -1) return '[Circular]';
    seen.push(val);
    try {
      if (Array.isArray(val)) {
        var arr = [];
        for (var i = 0; i < Math.min(val.length, MAX_ITEMS); i++) {
          arr.push(safeSerialize(val[i], depth + 1, seen));
        }
        if (val.length > MAX_ITEMS) arr.push('[+' + (val.length - MAX_ITEMS) + ' more]');
        return arr;
      }
      // 普通对象：逐键序列化
      var out = {};
      var keys = Object.keys(val);
      for (var k = 0; k < Math.min(keys.length, MAX_ITEMS); k++) {
        var key = keys[k];
        try { out[key] = safeSerialize(val[key], depth + 1, seen); }
        catch (e) { out[key] = '[Unserializable]'; }
      }
      if (keys.length > MAX_ITEMS) out.__more__ = '+' + (keys.length - MAX_ITEMS) + ' keys';
      return out;
    } finally {
      seen.pop();
    }
  }

  /**
   * 执行一段 JS 代码并回传结果。
   * 代码在页面主世界运行，可读写 window / document / localStorage，
   * 可对元素触发 click 等操作。支持 await（代码可写成异步形式）。
   * @param {string} reqId 请求 id，回传时原样带回
   * @param {string} code 待执行代码
   */
  function runCode(reqId, code) {
    function reply(payload) {
      (window.top || window).postMessage(Object.assign({
        source: 'ai-debug-main',
        type: 'exec-js-result',
        reqId: reqId
      }, payload), '*');
    }
    try {
      // 用 async 包裹，允许代码里直接写 await
      var fn = new Function('"use strict"; return (async function () {\n' + code + '\n})();');
      Promise.resolve(fn()).then(function (result) {
        reply({ success: true, result: safeSerialize(result, 0, []) });
      }, function (err) {
        reply({ success: false, error: String((err && err.stack) || err) });
      });
    } catch (e) {
      reply({ success: false, error: String((e && e.stack) || e) });
    }
  }

  // 监听内容脚本投递的执行请求（同窗口，隔离世界发的消息这里能收到）
  window.addEventListener('message', function (ev) {
    var d = ev.data;
    if (!d || d.source !== 'ai-debug-content' || d.type !== 'exec-js') return;
    runCode(d.reqId, String(d.code || ''));
  });
})();
