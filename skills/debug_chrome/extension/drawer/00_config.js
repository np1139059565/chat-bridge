// 抽屉配置模型与通用辅助函数
window.AIDrawer = (function () {
  const MSG_ID_SET = new Set();

  function dedupPush(messages, list) {
    for (const m of list) {
      if (m.id && MSG_ID_SET.has(m.id)) continue;
      if (m.id) MSG_ID_SET.add(m.id);
      messages.value.push(m);
    }
  }

  function updateMessageStatus(messages, id, status) {
    if (!id) return;
    const target = messages.value.find((m) => m.id === id);
    if (target) target.status = status;
  }

  // 仅保留与调试能力相关的配置；连接地址指向工具服务（chat-bridge）
  // url_mappings：URL 前缀 → 本地工程文件路径，供元素卡片把选中元素对应到源码位置
  const DEFAULT_CFG = {
    backend_url: 'http://127.0.0.1:5000',
    screenshot_enabled: false,
    style_list_enabled: false,
    url_mappings: [],
  };

  function clone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function mergeCfg(stored) {
    const base = clone(DEFAULT_CFG);
    if (!stored || typeof stored !== 'object') return base;
    Object.keys(base).forEach((k) => {
      if (stored[k] !== undefined) base[k] = stored[k];
    });
    if (!Array.isArray(base.url_mappings)) base.url_mappings = [];
    return base;
  }

  function cleanCfg(raw) {
    const c = clone(raw);
    c.screenshot_enabled = c.screenshot_enabled === true;
    c.style_list_enabled = c.style_list_enabled === true;
    if (!Array.isArray(c.url_mappings)) c.url_mappings = [];
    // 只保留填写完整的映射项
    c.url_mappings = c.url_mappings.filter((m) => m && m.url_prefix && m.local_path);
    return c;
  }

  // 归一 URL：去查询串与锚点，仅保留「协议 + 主机 + 路径」。
  // 注意：chrome-extension:// 等非 http(s) 协议的 origin 为 "null"，
  // 必须改用 protocol + host 重建，否则插件自身页面的 URL 会变成 "null/..."。
  function normalizeUrl(url) {
    if (!url) return '';
    try {
      const u = new URL(url, location.href);
      let path = u.pathname;
      if (path.length > 1 && path.endsWith('/')) path = path.slice(0, -1);
      const base = (u.origin && u.origin !== 'null') ? u.origin : (u.protocol + '//' + u.host);
      return base + path;
    } catch (e) {
      return '';
    }
  }

  // 按 URL 前缀匹配本地工程路径：取最长匹配项。
  // 比对前先归一，参数 / 锚点不影响匹配。
  function matchUrlMapping(mappings, url) {
    const target = normalizeUrl(url);
    if (!target) return null;
    let best = null;
    (mappings || []).forEach((m) => {
      if (!m || !m.url_prefix || !m.local_path) return;
      if (target.indexOf(m.url_prefix) === 0) {
        if (!best || m.url_prefix.length > best.url_prefix.length) best = m;
      }
    });
    return best;
  }

  function generateId() {
    return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function formatTime(ts) {
    if (!ts) return '';
    const millis = typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts;
    const d = new Date(millis);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  }

  function styleSummary(styles) {
    if (!styles || typeof styles !== 'object') return '';
    return Object.keys(styles).slice(0, 30).map((k) => `${k}: ${styles[k]}`).join('\n');
  }

  // iframe 点选补丁：粘贴到 iframe 控制台后，该 iframe 内的元素可被点选。
  // 补丁在 iframe 内监听父页面的选择模式开关：
  //   - 鼠标中键（滚轮键）点击：选择元素并回传父页面
  //   - 右键单击：退出选择模式，并通知父页面同步状态
  // 用中键而非左键：中键极少承载页面业务，不碰左键单击、也不碰右键菜单，
  // 因此无需拦截任何常规鼠标手势，完全不影响 iframe 内页面交互。
  const IFRAME_PATCH = [
    '(function(){',
    '  if (window.__AI_DEBUG_IFRAME_PATCH__) { console.log("[AI-Debug] 补丁已安装"); return; }',
    '  window.__AI_DEBUG_IFRAME_PATCH__ = true;',
    '  var mode = false, box = null;',
    '  function post(m){ m.source = "ai-debug-iframe"; m.frameUrl = location.href; window.parent.postMessage(m, "*"); }',
    '  function cssEscape(s){ return (window.CSS && CSS.escape) ? CSS.escape(s) : s; }',
    '  function unique(sel){ try { return document.querySelectorAll(sel).length === 1; } catch(e){ return false; } }',
    '  function genSelector(el){',
    '    if (el.id){ var s = "#" + cssEscape(el.id); if (unique(s)) return s; }',
    '    var node = el, path = [], depth = 0;',
    '    while (node && node !== document.body && node !== document.documentElement && depth < 5){',
    '      var sel = node.tagName.toLowerCase();',
    '      if (node.className && typeof node.className === "string"){',
    '        var cls = node.className.split(/\\s+/).filter(Boolean).filter(function(c){ return c.indexOf("ai-debug-") !== 0; }).slice(0,2);',
    '        if (cls.length) sel += "." + cls.map(cssEscape).join(".");',
    '      }',
    '      var parent = node.parentElement;',
    '      if (parent){ var sib = Array.prototype.slice.call(parent.children); if (sib.length > 1) sel += ":nth-child(" + (sib.indexOf(node)+1) + ")"; }',
    '      path.unshift(sel); if (unique(path.join(" > "))) return path.join(" > ");',
    '      node = parent; depth++;',
    '    }',
    '    return path.join(" > ") || el.tagName.toLowerCase();',
    '  }',
    '  function highlight(el){',
    '    if (!box){ box = document.createElement("div"); box.style.cssText = "position:fixed;pointer-events:none;z-index:2147483646;border:2px dashed #1890ff;background:rgba(24,144,255,.1);box-sizing:border-box;"; document.body.appendChild(box); }',
    '    var r = el.getBoundingClientRect();',
    '    box.style.left = r.left + "px"; box.style.top = r.top + "px"; box.style.width = r.width + "px"; box.style.height = r.height + "px"; box.style.display = "block";',
    '  }',
    '  document.addEventListener("mouseover", function(e){ if (mode) highlight(e.target); }, true);',
    '  document.addEventListener("mouseout", function(){ if (box) box.style.display = "none"; }, true);',
    '  document.addEventListener("mousedown", function(e){ if (mode && e.button === 1) e.preventDefault(); }, true);',
    '  document.addEventListener("auxclick", function(e){',
    '    if (!mode) return;',
    '    if (e.button !== 1) return;',
    '    e.preventDefault(); e.stopPropagation();',
    '    var el = e.target;',
    '    post({ type: "element-selected", element: {',
    '      selector: genSelector(el),',
    '      selector_confidence: unique(genSelector(el)) ? "high" : "low",',
    '      tag_name: el.tagName.toLowerCase(),',
    '      inline_style: el.getAttribute("style") || "",',
    '      dom_html: (el.outerHTML || "").slice(0, 2000),',
    '      page_url: location.href',
    '    }});',
    '    console.log("[AI-Debug] 已回传元素：" + genSelector(el));',
    '  }, true);',
    '  document.addEventListener("contextmenu", function(e){',
    '    if (!mode) return;',
    '    e.preventDefault(); e.stopPropagation();',
    '    mode = false;',
    '    if (box) box.style.display = "none";',
    '    post({ type: "select-cancelled" });',
    '    console.log("[AI-Debug] 已退出选择模式");',
    '  }, true);',
    '  function buildData(el){',
    '    return {',
    '      selector: genSelector(el),',
    '      selector_confidence: unique(genSelector(el)) ? "high" : "low",',
    '      tag_name: el.tagName.toLowerCase(),',
    '      inline_style: el.getAttribute("style") || "",',
    '      dom_html: (el.outerHTML || "").slice(0, 2000),',
    '      page_url: location.href',
    '    };',
    '  }',
    '  function replyQuery(reqId, result){',
    '    post({ type: "query-result", reqId: reqId, result: result });',
    '  }',
    '  window.addEventListener("message", function(e){',
    '    var d = e.data;',
    '    if (!d || d.source !== "ai-debug-parent") return;',
    '    if (d.type === "toggle-select"){ mode = !!d.selecting; if (!mode && box) box.style.display = "none"; }',
    '    else if (d.type === "query-element"){',
    '      try {',
    '        var ms = d.selector ? document.querySelectorAll(d.selector) : null;',
    '        if (!ms || ms.length === 0) { replyQuery(d.reqId, { success:false, error:"ELEMENT_NOT_FOUND", selector:d.selector, page_url: location.href }); }',
    '        else if (ms.length > 1) { replyQuery(d.reqId, { success:false, error:"ELEMENT_NOT_UNIQUE", selector:d.selector, count: ms.length }); }',
    '        else { var el = ms[0]; var data = buildData(el); if (d.wantStyle) { var cs = getComputedStyle(el); data.computed_style = {}; if (d.includeAll || !d.properties || !d.properties.length) { for (var i=0;i<cs.length;i++){ data.computed_style[cs[i]] = cs.getPropertyValue(cs[i]); } } else { d.properties.forEach(function(k){ var v = cs.getPropertyValue(k); if (v) data.computed_style[k] = v; }); } } replyQuery(d.reqId, { success:true, data:data }); }',
    '      } catch(err){ replyQuery(d.reqId, { success:false, error:"QUERY_FAILED", message: String(err) }); }',
    '    }',
    '    else if (d.type === "query-dom"){',
    '      replyQuery(d.reqId, { success:true, data:{ dom: (document.documentElement.outerHTML || "").slice(0, 20000) } });',
    '    }',
    '  });',
    '  post({ type: "patch-ready" });',
    '  console.log("[AI-Debug] iframe 点选补丁已安装");',
    '})();'
  ].join('\n');

  function statusLabel(status) {
    if (status === 'waiting') return '等待领取';
    if (status === 'processing') return '处理中';
    if (status === 'completed') return '已完成';
    return '';
  }

  return {
    DEFAULT_CFG,
    MSG_ID_SET,
    dedupPush,
    updateMessageStatus,
    clone,
    mergeCfg,
    cleanCfg,
    generateId,
    formatTime,
    styleSummary,
    statusLabel,
    matchUrlMapping,
    normalizeUrl,
    IFRAME_PATCH,
  };
})();
