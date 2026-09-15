// 元素选择器生成、元素数据构建、选择模式与高亮
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  A.truncate = function (text, max) {
    if (typeof text !== 'string' || text.length <= max) return text;
    return text.slice(0, max) + '[truncated]';
  };

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
      dom_html: A.truncate(el.outerHTML, A.MAX_DOM_CHARS),
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

  // 归一 URL：去掉查询串与锚点，仅保留「协议 + 主机 + 路径」。
  // 映射以「页面路径」为单位，参数变化不影响匹配。
  // chrome-extension:// 等协议的 origin 为 "null"，需用 protocol + host 重建。
  A.normalizeUrl = function (url) {
    try {
      const u = new URL(url, location.href);
      let path = u.pathname;
      if (path.length > 1 && path.endsWith('/')) path = path.slice(0, -1);
      const base = (u.origin && u.origin !== 'null') ? u.origin : (u.protocol + '//' + u.host);
      return base + path;
    } catch (e) {
      return '';
    }
  };

  // 收集文档（含 Shadow DOM）内所有 iframe 元素。
  // 本工具抽屉自身也是一个 iframe，但它位于 Shadow DOM 中，
  // 常规 querySelectorAll('iframe') 看不到它；递归遍历 shadowRoot 才能拿到。
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

  // 列出当前页面所有 iframe 的归一 URL（供工具在顶层找不到元素时给出候选提示）
  A.frameUrls = function () {
    const seen = {};
    const out = [];
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

  A.isInsideDrawer = function (el) {
    const host = document.getElementById(A.SHADOW_HOST_ID);
    if (!host) return false;
    return host === el || host.contains(el);
  };

  A.toggleSelectMode = function (active) {
    state.selectMode = active;
    if (state.selectMode) {
      document.body.classList.add('ai-style-select-mode');
      A.showToast('已进入元素选择模式，鼠标中键（滚轮键）点击页面元素即可连续多选；右键单击或按 Esc 退出');
    } else {
      document.body.classList.remove('ai-style-select-mode');
      A.hideHighlight();
    }
    A.broadcastSelectToIframes(active);
  };

  // 向页面内所有 iframe（含 Shadow DOM 中的抽屉 iframe）广播选择模式开关。
  // 装了点选补丁的 iframe 会据此在自身文档内启用点选，
  // 解决「iframe 内元素无法被点选」的问题。
  A.broadcastSelectToIframes = function (active) {
    const frames = A.collectAllIframes();
    for (let i = 0; i < frames.length; i++) {
      try {
        if (frames[i].contentWindow) {
          frames[i].contentWindow.postMessage(
            { source: 'ai-debug-parent', type: 'toggle-select', selecting: !!active },
            '*'
          );
        }
      } catch (e) { /* 跨域 iframe 忽略 */ }
    }
  };

  // 高亮层使用 Shadow DOM 承载：外部网页的全局 CSS（通配选择器、transition、transform、
  // overflow 裁剪、!important 规则等）无法穿透 Shadow 边界影响高亮框，样式始终可控、
  // 始终可见；这与 chat-bridge 把面板放进 iframe 从而隔离宿主样式的做法一致。
  A.getHighlightLayer = function () {
    if (state.highlightLayer && state.highlightLayer.isConnected) return state.highlightLayer;
    const host = document.createElement('div');
    host.id = 'ai-style-highlight-host';
    // 宿主本身不占位、不拦截事件；层级取上限，确保浮于页面之上
    host.style.cssText = 'position:fixed;top:0;left:0;width:0;height:0;z-index:2147483647;pointer-events:none;';
    document.documentElement.appendChild(host);
    const root = host.attachShadow({ mode: 'open' });

    // 高亮框：实线双层描边 + 半透明填充，选择范围一目了然
    const box = document.createElement('div');
    box.className = 'ai-style-highlight-box';
    box.style.cssText = 'position:fixed;pointer-events:none;box-sizing:border-box;'
      + 'border:2px solid #1890ff;background:rgba(24,144,255,0.18);'
      + 'box-shadow:0 0 0 1px rgba(255,255,255,0.9), 0 0 6px rgba(24,144,255,0.6);'
      + 'border-radius:2px;transition:none;';

    // 尺寸标签：显示当前元素的宽高，进一步确认选择范围
    const tag = document.createElement('div');
    tag.className = 'ai-style-highlight-tag';
    tag.style.cssText = 'position:fixed;pointer-events:none;background:#1890ff;color:#fff;'
      + 'font:11px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;'
      + 'padding:1px 6px;border-radius:3px;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,0.3);';

    root.appendChild(box);
    root.appendChild(tag);
    state.highlightLayer = host;
    state.highlightBox = box;
    state.highlightTag = tag;
    return host;
  };

  A.updateHighlight = function (el) {
    A.getHighlightLayer();
    const rect = el.getBoundingClientRect();
    const box = state.highlightBox;
    box.style.left = rect.left + 'px';
    box.style.top = rect.top + 'px';
    box.style.width = rect.width + 'px';
    box.style.height = rect.height + 'px';
    box.style.display = 'block';

    // 标签贴在元素左上角上方；靠近视口顶部时改放到元素内侧，避免被裁掉
    const tag = state.highlightTag;
    tag.textContent = el.tagName.toLowerCase() + ' '
      + Math.round(rect.width) + '×' + Math.round(rect.height);
    tag.style.display = 'block';
    tag.style.left = rect.left + 'px';
    tag.style.top = (rect.top >= 20 ? rect.top - 18 : rect.top) + 'px';
  };

  A.hideHighlight = function () {
    if (state.highlightBox) state.highlightBox.style.display = 'none';
    if (state.highlightTag) state.highlightTag.style.display = 'none';
  };

  // 给每个已选元素分配唯一 selId：抽屉与内容脚本据此增删，
  // 避免用下标带来的错位（例如抽屉因未配置映射而拒绝加入时）。
  let _selSeq = 0;
  function nextSelId() {
    _selSeq += 1;
    return 'sel-' + Date.now() + '-' + _selSeq;
  }

  A.pushSelected = function (elementData, screenshot) {
    if (screenshot) elementData.screenshot = screenshot;
    if (!elementData.selId) elementData.selId = nextSelId();
    state.selectedElements.push(elementData);
    A.postToDrawer({ type: 'element-selected', element: elementData });
  };

  // 按 selId 移除单个元素，回传最新列表
  A.removeElementById = function (selId) {
    const idx = state.selectedElements.findIndex((el) => el.selId === selId);
    if (idx >= 0) state.selectedElements.splice(idx, 1);
    A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
  };

  A.removeElementAt = function (index) {
    if (index >= 0 && index < state.selectedElements.length) {
      state.selectedElements.splice(index, 1);
    }
    A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
  };

  A.clearElements = function () {
    state.selectedElements.length = 0;
    A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
  };
})();
