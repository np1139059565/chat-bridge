// 模块：extend/content/06_picker.js
// 用途：元素选择模式（供远程桥接的自定义指令配置使用）。
//  - 进入选择模式后，鼠标悬停高亮元素，点击即生成选择器并回传抽屉。
//  - 选择器生成算法与 debug_chrome 技能同源，保证「选中的元素」可被稳定复现。
//  - 另提供按选择器点击元素的能力，供 QQ 指令「点击元素」执行时调用。
// 依赖：content/00_state.js（命名空间 A）
(function () {
  'use strict';
  const A = window.AIMirrorContent;

  // 选择模式的运行时状态
  A.pickerState = {
    active: false,       // 是否处于选择模式
    hoverEl: null,       // 当前高亮的元素
    host: null,          // 高亮层宿主
    box: null,           // 高亮框
    tag: null,           // 尺寸标签
    onMove: null,        // 鼠标移动监听
    onClick: null,       // 点击监听
    onKey: null          // 键盘监听（Esc 退出）
  };

  /**
   * 生成元素的选择器。
   * 优先用唯一 id；否则沿 DOM 向上拼接路径，命中唯一即返回。
   * @param {Element} el 目标元素
   * @returns {Object} { selector, confidence }
   */
  A.pickerSelector = function (el) {
    if (!el || el.nodeType !== 1) return { selector: '', confidence: 'low' };
    // 1) 唯一 id 最稳
    if (el.id) {
      const idSel = '#' + CSS.escape(el.id);
      try {
        if (document.querySelectorAll(idSel).length === 1) {
          return { selector: idSel, confidence: 'high' };
        }
      } catch (e) { /* 非法 id，继续 */ }
    }
    // 2) 沿 DOM 向上拼路径
    let node = el;
    const path = [];
    let depth = 0;
    while (node && node !== document.body && node !== document.documentElement && depth < 5) {
      let sel = node.tagName.toLowerCase();
      if (node.className && typeof node.className === 'string') {
        const classes = node.className.split(/\s+/).filter(Boolean)
          .filter((c) => !c.startsWith('ai-mirror-'))
          .slice(0, 2);
        if (classes.length) sel += '.' + classes.map((c) => CSS.escape(c)).join('.');
      }
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children);
        if (siblings.length > 1) sel += ':nth-child(' + (siblings.indexOf(node) + 1) + ')';
      }
      path.unshift(sel);
      const joined = path.join(' > ');
      try {
        if (document.querySelectorAll(joined).length === 1) {
          return { selector: joined, confidence: 'high' };
        }
      } catch (e) { /* 继续向上 */ }
      node = parent;
      depth += 1;
    }
    return { selector: path.join(' > ') || el.tagName.toLowerCase(), confidence: 'low' };
  };

  /** 创建高亮层（懒加载，整页只建一次）。 */
  A.pickerHighlight = function () {
    const s = A.pickerState;
    if (s.host && s.host.isConnected) return;
    const host = document.createElement('div');
    host.id = 'ai-mirror-picker-host';
    // 宿主零尺寸、不拦截事件，层级取上限确保浮于页面之上
    host.style.cssText = 'position:fixed !important;top:0 !important;left:0 !important;'
      + 'width:0 !important;height:0 !important;z-index:2147483647 !important;pointer-events:none !important;';
    const box = document.createElement('div');
    box.style.cssText = 'position:fixed !important;pointer-events:none !important;box-sizing:border-box !important;'
      + 'border:2px solid #1890ff !important;background:rgba(24,144,255,0.18) !important;'
      + 'box-shadow:0 0 0 1px rgba(255,255,255,0.9) !important;border-radius:2px !important;display:none !important;';
    const tag = document.createElement('div');
    tag.style.cssText = 'position:fixed !important;pointer-events:none !important;background:#1890ff !important;color:#fff !important;'
      + 'font:11px/1.6 sans-serif !important;padding:1px 6px !important;border-radius:3px !important;display:none !important;';
    host.appendChild(box);
    host.appendChild(tag);
    document.documentElement.appendChild(host);
    s.host = host; s.box = box; s.tag = tag;
  };

  /** 高亮某个元素。 */
  A.pickerShow = function (el) {
    A.pickerHighlight();
    const s = A.pickerState;
    if (!el) { s.box.style.display = 'none'; s.tag.style.display = 'none'; return; }
    const r = el.getBoundingClientRect();
    s.box.style.left = r.left + 'px';
    s.box.style.top = r.top + 'px';
    s.box.style.width = r.width + 'px';
    s.box.style.height = r.height + 'px';
    s.box.style.display = 'block';
    s.tag.textContent = el.tagName.toLowerCase() + ' ' + Math.round(r.width) + '×' + Math.round(r.height);
    s.tag.style.left = r.left + 'px';
    s.tag.style.top = (r.top >= 20 ? r.top - 18 : r.top) + 'px';
    s.tag.style.display = 'block';
  };

  /** 退出选择模式，清理监听与高亮。 */
  A.pickerStop = function () {
    const s = A.pickerState;
    s.active = false;
    if (s.onMove) { document.removeEventListener('mousemove', s.onMove, true); s.onMove = null; }
    if (s.onClick) { document.removeEventListener('click', s.onClick, true); s.onClick = null; }
    if (s.onKey) { document.removeEventListener('keydown', s.onKey, true); s.onKey = null; }
    A.pickerShow(null);
    if (s.host && s.host.parentNode) s.host.parentNode.removeChild(s.host);
    s.host = null; s.box = null; s.tag = null; s.hoverEl = null;
    A.post({ type: 'picker_stopped' });
  };

  /**
   * 把拾取到的裸 CSS 选择器包装成执行端的新语法。
   * 执行端只按 JS 表达式求值，不再兼容裸选择器；拾取即产出新语法。
   * @param {string} selector 裸选择器
   * @returns {string} document.querySelector('...') 形式的表达式（单元素）
   */
  A.wrapPickerExpr = function (selector) {
    if (!selector) return '';
    // 转义反斜杠与单引号，保证嵌入单引号字符串后仍是合法 JS
    const escaped = String(selector).split('\\').join('\\\\').split("'").join("\\'");
    // 生成 querySelector：拾取到的选择器已保证唯一，直接得到单个 DOM 元素。
    // 不用 querySelectorAll——那返回列表，多元素时点击必然失败。
    return "document.querySelector('" + escaped + "')";
  };

  /**
   * 进入选择模式。
   * 悬停高亮、点击选中并把选择器回传抽屉、Esc 退出。
   */
  A.pickerStart = function () {
    const s = A.pickerState;
    if (s.active) return;
    s.active = true;
    // 捕获阶段监听，抢在页面自身逻辑之前处理
    s.onMove = function (e) {
      const el = e.target;
      if (!el || el.nodeType !== 1) return;
      if (s.host && (el === s.host || s.host.contains(el))) return;
      s.hoverEl = el;
      A.pickerShow(el);
    };
    s.onClick = function (e) {
      const el = e.target;
      if (!el || el.nodeType !== 1) return;
      if (s.host && (el === s.host || s.host.contains(el))) return;
      // 阻止页面自身响应这次点击
      e.preventDefault();
      e.stopPropagation();
      const info = A.pickerSelector(el);
      // 包成执行端的新语法（细节见 A.wrapPickerExpr）
      const expr = A.wrapPickerExpr(info.selector);
      // 把选择结果回传抽屉
      A.post({
        type: 'picker_result',
        selector: expr,
        confidence: info.confidence,
        page_url: location.href,
        tag: el.tagName.toLowerCase()
      });
      A.pickerStop();
    };
    s.onKey = function (e) {
      if (e.key === 'Escape') A.pickerStop();
    };
    document.addEventListener('mousemove', s.onMove, true);
    document.addEventListener('click', s.onClick, true);
    document.addEventListener('keydown', s.onKey, true);
    A.log('已进入元素选择模式');
  };

  // 主世界 hook（injected_clipboard.js）由 manifest 以 world:MAIN 声明式注入，
  // 在 document_start 就跑，早于页面自身脚本。
  // 注意：不要改回用 script 标签注入——那会被页面 CSP 拦掉，
  // hook 装不上，剪贴板内容就永远截获不到。

  // 接收主世界 hook 回传的剪贴板内容：{
  //   source:'ai-mirror-clip', type:'copied', text }
  // 收到后转交抽屉（A.post 走的是与抽屉的既有通道）。
  window.addEventListener('message', function (e) {
    const d = e.data;
    if (!d || d.source !== 'ai-mirror-clip' || d.type !== 'copied') return;
    A.post({ type: 'clip_copied', text: d.text || '' });
  });

  // ---------- 元素点击：经主世界执行 ----------
  // 求值必须在主世界做：隔离世界受扩展 CSP 限制（无 unsafe-eval），
  // new Function 会抛错，导致任何带 JS 的表达式都误报「语法无效」。
  // 主世界脚本（injected_clipboard.js）收到表达式后求值、点击并回传结果。

  // 待回传登记：reqId → { cb, timer }；主世界回传后据此转交抽屉。
  const _execPending = {};
  let _execSeq = 0;
  // 主世界回传超时：主世界脚本未注入 / 不回传时，看门狗兜底，
  // 避免回调永不触发、QQ 指令永久挂起。
  const EXEC_TIMEOUT = 3000;

  /**
   * 请求主世界执行表达式并点击。
   * 表达式由用户自由填写，不限定写法——只要求值得到符合要求的元素即可。
   * @param {string} expr 选择器或任意 JS 表达式
   * @param {string} mode 'unique'（默认，须一个且唯一）| 'last'（取最后一个）
   * @param {Function} onResult 结果回调 (ok, reason, count)
   * @returns {string} reqId
   */
  A.execClick = function (expr, mode, onResult) {
    const reqId = 'e' + (++_execSeq) + '_' + Date.now();
    const cb = onResult || null;
    // 看门狗：超时未回传则按「无法求值」收尾，保证回调一定被调用一次
    const timer = setTimeout(function () {
      const p = _execPending[reqId];
      if (!p) return;
      delete _execPending[reqId];
      if (p.cb) p.cb(false, 'timeout', 0);
    }, EXEC_TIMEOUT);
    _execPending[reqId] = { cb: cb, timer: timer };
    try {
      window.postMessage({
        source: 'ai-mirror-exec', type: 'click',
        reqId: reqId, expr: String(expr == null ? '' : expr), mode: mode || 'unique'
      }, '*');
    } catch (e) {
      clearTimeout(timer);
      delete _execPending[reqId];
      if (cb) cb(false, 'invalid', 0);
    }
    return reqId;
  };

  // 接收主世界回传的点击结果，转交对应回调。
  window.addEventListener('message', function (e) {
    const d = e.data;
    if (!d || d.source !== 'ai-mirror-exec' || d.type !== 'click_result') return;
    const p = _execPending[d.reqId];
    if (!p) return;
    delete _execPending[d.reqId];
    clearTimeout(p.timer);   // 已回传：取消看门狗
    if (p.cb) p.cb(!!d.ok, d.reason || '', d.count || 0);
  });

  /**
   * 点击页面的「复制按钮」，截获它写入剪贴板的 Markdown 内容。
   *
   * 流程：请求主世界点击按钮 → 页面执行 clipboard.writeText(md)
   * → 主世界 hook 截获 → 回传本脚本 → 再转交抽屉。
   * @param {string} selector 复制按钮的选择器或表达式
   */
  A.clickCopyButton = function (selector) {
    if (!selector) { A.warn('clickCopyButton：选择器为空'); return; }
    // 采集面向「最新一条回复」的复制按钮：命中多个取最后一个
    A.execClick(selector, 'last', function (ok, reason) {
      // 点击失败：回传空结果，让抽屉的采集流程照常收尾
      if (!ok) A.post({ type: 'clip_copied', text: '', error: reason || 'button_not_found' });
    });
  };

  /**
   * 点击页面元素（供 QQ 指令「点击元素」调用）。
   * 表达式由用户自由填写；只要求值得到「一个且唯一」的元素即视为生效。
   * @param {string} selector 选择器或任意 JS 表达式
   * @param {Object} extra 回传抽屉时一并带上的字段（如 selector / request_id）
   */
  A.clickBySelector = function (selector, extra) {
    if (!selector) {
      A.post(Object.assign(
        { type: 'click_result', ok: false, reason: 'empty_selector', count: 0 }, extra || {}));
      return;
    }
    A.execClick(selector, 'unique', function (ok, reason, count) {
      A.post(Object.assign(
        { type: 'click_result', ok: ok, reason: reason, count: count }, extra || {}));
    });
  };

  /**
   * 截取浏览器当前可见区域。
   *
   * 为什么要绕后台：chrome.tabs.captureVisibleTab 只能在后台服务里调用，
   * 内容脚本没有这个权限。这里发消息给后台，拿到 dataURL 后回传抽屉。
   * @param {string} requestId 待回传请求 id，原样带回给抽屉
   */
  A.captureTab = function (requestId) {
    // 超时兜底：后台若因 service worker 休眠等原因不回，回调可能永不触发，
    // 命令会一直挂着。这里 5 秒内没拿到结果就按失败回传，避免卡住。
    let done = false;
    const finish = (payload) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      A.post(Object.assign({ type: 'screenshot_result', request_id: requestId || '' }, payload));
    };
    const timer = setTimeout(() => finish({ ok: false, error: 'SCREENSHOT_TIMEOUT' }), 5000);
    try {
      chrome.runtime.sendMessage({ type: 'bridge_capture_tab' }, function (resp) {
        // 后台 service worker 未就绪时，回调的 resp 为空且 lastError 被设置。
        // 必须读取它，否则 Chrome 报 Unchecked runtime.lastError（控制台噪音，
        // 且被误判为「扩展连接失败」）。这里转为明确的失败回执。
        if (chrome.runtime.lastError) {
          finish({ ok: false, error: String(chrome.runtime.lastError.message || '') });
          return;
        }
        const ok = !!(resp && resp.ok);
        finish({
          ok: ok,
          dataUrl: (resp && resp.dataUrl) || '',
          error: (resp && resp.error) || ''
        });
      });
    } catch (e) {
      finish({ ok: false, error: String(e) });
    }
  };
})();
