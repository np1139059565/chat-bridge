// 元素选择器生成、元素数据构建、选择模式与高亮
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  A.isUnique = function (selector) {
    try {
      return document.querySelectorAll(selector).length === 1;
    } catch (err) {
      return false;
    }
  };

  A.generateSelector = function (el) {
    if (el.id) {
      const idSel = '#' + CSS.escape(el.id);
      if (A.isUnique(idSel)) return { selector: idSel, confidence: 'high' };
    }
    let node = el;
    const path = [];
    let depth = 0;
    while (node && node !== document.body && node !== document.documentElement && depth < 5) {
      let sel = node.tagName.toLowerCase();
      if (node.className && typeof node.className === 'string') {
        const classes = node.className
          .split(/\s+/)
          .filter(Boolean)
          .filter((c) => !c.startsWith('ai-style-'))
          .slice(0, 2);
        if (classes.length) sel += '.' + classes.map(CSS.escape).join('.');
      }
      const parent = node.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children);
        if (siblings.length > 1) {
          sel += `:nth-child(${siblings.indexOf(node) + 1})`;
        }
      }
      path.unshift(sel);
      if (A.isUnique(path.join(' > '))) {
        return { selector: path.join(' > '), confidence: 'high' };
      }
      node = parent;
      depth += 1;
    }
    return { selector: path.join(' > ') || el.tagName.toLowerCase(), confidence: 'low' };
  };

  // 采集元素数据。
  // forceStyle：强制采集计算样式（get_element_style 工具默认需要样式，
  //   不应受「采集样式列表」全局开关限制——否则工具名不副实）。
  // properties：只返回指定 CSS 属性（数组），省略则返回全量。
  A.buildElementData = function (el, selectorInfo, forceStyle, properties) {
    const data = {
      selector: selectorInfo.selector,
      selector_confidence: selectorInfo.confidence,
      tag_name: el.tagName ? el.tagName.toLowerCase() : '',
      computed_style: {},
      inline_style: el.getAttribute('style') || '',
      // DOM 内容保持完整：截断会让用户看不到元素真实结构，也会让「按内容去重」失真。
      // 体积交由调用方按需判断，这里只附带长度，便于界面展示与用户评估。
      dom_html: el.outerHTML,
      dom_html_length: (el.outerHTML || '').length,
      page_url: location.href,
    };
    // 采集样式：工具显式要求，或全局样式开关开启
    if (forceStyle || state.styleListEnabled) {
      const computed = window.getComputedStyle(el);
      const style = {};
      if (Array.isArray(properties) && properties.length) {
        // 只取指定属性，避免返回数百条无关样式
        properties.forEach((k) => {
          const v = computed.getPropertyValue(k);
          if (v) style[k] = v;
        });
      } else {
        for (let i = 0; i < computed.length; i++) {
          const key = computed[i];
          style[key] = computed.getPropertyValue(key);
        }
      }
      data.computed_style = style;
    }
    return data;
  };

  // 归一 URL：实现由共享模块提供（shared/url-utils.js），此处仅做命名空间转发，
  // 保证 A.normalizeUrl 既有调用点与对外接口保持不变。
  A.normalizeUrl = function (url) {
    return window.AIUrlUtils.normalizeUrl(url);
  };

  // 收集文档内所有 iframe 元素。
  // 除常规子 iframe 外，仍会递归进入页面自身的 Shadow DOM（若页面用了），
  // 保证嵌套在 shadow 树里的 iframe 也能被覆盖。
  A.collectAllIframes = function () {
    const out = [];
    const walk = (root) => {
      if (!root || !root.querySelectorAll) return;
      const frames = root.querySelectorAll('iframe');
      for (let i = 0; i < frames.length; i++) out.push(frames[i]);
      // 递归进入所有带 shadowRoot 的元素
      const all = root.querySelectorAll('*');
      for (let i = 0; i < all.length; i++) {
        if (all[i].shadowRoot) walk(all[i].shadowRoot);
      }
    };
    walk(document);
    return out;
  };

  // 收集当前页面所有 URL：主文档 + 各 iframe（含跨域 iframe 的 src 声明值）。
  // 用于设置页自动列出可映射的 URL，用户只需为每个 URL 填本地路径。
  A.collectPageUrls = function () {
    const seen = {};
    const out = [];
    const push = (raw) => {
      const n = A.normalizeUrl(raw);
      if (!n || seen[n]) return;
      seen[n] = true;
      out.push(n);
    };
    push(location.href);
    const frames = A.collectAllIframes();
    for (let i = 0; i < frames.length; i++) {
      const f = frames[i];
      // 同源 iframe 可读取真实地址；跨域读不到时退回 src 声明值
      try {
        if (f.contentWindow && f.contentWindow.location && f.contentWindow.location.href) {
          push(f.contentWindow.location.href);
        }
      } catch (e) {
        if (f.getAttribute && f.getAttribute('src')) push(f.getAttribute('src'));
      }
      if (f.getAttribute && f.getAttribute('src')) push(f.getAttribute('src'));
    }
    return out;
  };

  // 列出当前页面所有可路由文档的归一 URL（顶层文档 + 各 iframe），
  // 供工具在顶层找不到元素时给出候选提示。
  // 顶层文档必须计入：它同样是一个合法的 page_url 目标，漏掉会让 FRAME_NOT_FOUND
  // 的 available 列表与实际可查询范围不符。
  A.frameUrls = function () {
    const seen = {};
    const out = [];
    const topUrl = A.normalizeUrl(location.href);
    if (topUrl) { seen[topUrl] = true; out.push(topUrl); }
    A.collectAllIframes().forEach((f) => {
      let href = '';
      try {
        if (f.contentWindow && f.contentWindow.location && f.contentWindow.location.href) {
          href = f.contentWindow.location.href;
        }
      } catch (e) { /* 跨域读不到，退回 src */ }
      if (!href && f.getAttribute) href = f.getAttribute('src') || '';
      const n = A.normalizeUrl(href);
      if (n && !seen[n]) { seen[n] = true; out.push(n); }
    });
    return out;
  };

  // 按归一 URL 找到匹配的 iframe（用于把工具调用路由到元素实际所在的子页面）。
  // 调试扩展的 content script 只运行在顶层文档，子页面里没有它；
  // 因此必须借助用户已安装的「iframe 点选补丁」来代答查询。
  A.findFrameByUrl = function (url) {
    const target = A.normalizeUrl(url);
    if (!target) return null;
    const frames = A.collectAllIframes();
    for (let i = 0; i < frames.length; i++) {
      const f = frames[i];
      let href = '';
      try {
        if (f.contentWindow && f.contentWindow.location && f.contentWindow.location.href) {
          href = f.contentWindow.location.href;
        }
      } catch (e) { /* 跨域读不到，退回 src */ }
      if (!href && f.getAttribute) href = f.getAttribute('src') || '';
      if (A.normalizeUrl(href) === target) return f;
    }
    return null;
  };

  // 向指定 iframe 发起一次查询并等待回包（依赖该 iframe 内已安装点选补丁）。
  // 用 reqId 关联请求与响应，避免并发查询串包。
  A.queryFrame = function (frame, payload, timeoutMs) {
    return new Promise((resolve, reject) => {
      if (!frame || !frame.contentWindow) { reject(new Error('FRAME_UNAVAILABLE')); return; }
      const reqId = 'q-' + Date.now() + '-' + Math.floor(Math.random() * 1e6);
      const timer = setTimeout(() => {
        window.removeEventListener('message', onMsg);
        reject(new Error('FRAME_TIMEOUT'));
      }, timeoutMs || 3000);
      function onMsg(ev) {
        const d = ev.data;
        if (!d || d.source !== 'ai-debug-iframe' || d.type !== 'query-result' || d.reqId !== reqId) return;
        clearTimeout(timer);
        window.removeEventListener('message', onMsg);
        resolve(d);
      }
      window.addEventListener('message', onMsg);
      try {
        frame.contentWindow.postMessage(Object.assign({ source: 'ai-debug-parent', reqId }, payload), '*');
      } catch (e) {
        clearTimeout(timer);
        window.removeEventListener('message', onMsg);
        reject(new Error('FRAME_POST_FAILED'));
      }
    });
  };
})();
