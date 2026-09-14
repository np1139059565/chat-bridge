// 抽屉业务逻辑：与工具服务交互
//
// 发送链路：把用户需求与已选元素封装为外部卡片，POST /api/cards 挂起等待，
// 工具服务渲染卡片、自动发网页 AI、按 id 捕获结果后返回，抽屉展示为回复。
(function () {
  const D = window.AIDrawer;

  // 组装卡片正文：需求 + 已选元素（html / style / 元素信息）+ 源码路径映射
  // 每个元素按其 URL 匹配本地工程路径，拼成源码路径，供 AI 定位要改的文件。
  function buildCardContent(text, elements, mappings) {
    const lines = [text];
    if (elements && elements.length) {
      lines.push('', '【页面元素】');
      elements.forEach((el, i) => {
        lines.push(`\n#${i + 1} 选择器：${el.selector || ''}`);
        if (el.page_url) lines.push('URL：' + el.page_url);
        const m = D.matchUrlMapping(mappings, el.page_url || '');
        if (m) {
          // 源码路径 = 本地工程路径 + URL 归一后相对前缀的剩余部分
          const norm = D.normalizeUrl(el.page_url || '');
          const rest = norm.slice(m.url_prefix.length).replace(/^\/+/, '');
          const srcPath = rest ? (m.local_path.replace(/\/+$/, '') + '/' + rest) : m.local_path;
          lines.push('本地源码：' + srcPath);
        }
        if (el.computed_style && Object.keys(el.computed_style).length) {
          lines.push('计算样式：');
          Object.keys(el.computed_style).slice(0, 30).forEach((k) => lines.push('  ' + k + ': ' + el.computed_style[k]));
        }
        if (el.dom_html) lines.push('DOM：\n' + el.dom_html);
      });
    }
    return lines.join('\n');
  }

  D.createApi = function (ctx) {
    async function send() {
      const text = ctx.draft.value.trim();
      if (!text || !ctx.connected.value) return;
      const userMsg = {
        id: D.generateId(),
        role: 'user',
        text,
        elements: ctx.selectedElements.value.slice(),
        timestamp: Date.now(),
      };
      D.dedupPush(ctx.messages, [userMsg]);
      ctx.draft.value = '';
      ctx.selectedElements.value = [];
      window.parent.postMessage({ type: 'ai-debug-clear-elements', source: 'ai-debug-drawer' }, '*');
      ctx.scrollToBottom();

      const body = {
        type: 'debug-chrome-req',
        title: '样式调试需求',
        content: buildCardContent(text, userMsg.elements, ctx.cfg.value.url_mappings),
        payload: { elements: userMsg.elements, page_url: ctx.hostPageUrl.value },
        timeout_ms: 120000,
      };
      try {
        const res = await fetch(`${ctx.backendUrl.value}/api/cards`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (data.success) {
          D.dedupPush(ctx.messages, [{
            id: D.generateId(),
            role: 'assistant',
            text: typeof data.result === 'string' ? data.result : JSON.stringify(data.result, null, 2),
            timestamp: Date.now(),
          }]);
        } else {
          ctx.showToast('卡片未完成：' + (data.error || '未知错误'));
        }
      } catch (e) {
        ctx.showToast('发送失败：无法连接到工具服务');
      }
      ctx.scrollToBottom();
    }

    function clearHistory() {
      ctx.messages.value = [];
      // 工具卡片与消息同属会话内容，一并清空
      if (ctx.toolCards) ctx.toolCards.value = [];
      D.MSG_ID_SET.clear();
      ctx.showToast('会话记录已清空');
    }

    async function saveCfg() {
      const payload = D.cleanCfg(ctx.cfg.value);
      await chrome.storage.local.set({ aistyleCfg: payload, backendUrl: payload.backend_url });
      ctx.backendUrl.value = payload.backend_url;
      ctx.cfgStatus.value = '成功：配置已保存';
    }

    async function loadCfgFromBackend() {
      const stored = await chrome.storage.local.get(['aistyleCfg']);
      ctx.cfg.value = D.mergeCfg(stored.aistyleCfg);
      ctx.backendUrl.value = ctx.cfg.value.backend_url;
      ctx.cfgStatus.value = '成功：已从本地刷新配置';
    }

    // 复制 iframe 点选补丁代码到剪贴板
    function copyPatch() {
      const code = D.IFRAME_PATCH;
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(code).then(
          () => ctx.showToast('补丁代码已复制，请到 iframe 控制台粘贴执行'),
          () => fallbackCopy(code)
        );
      } else {
        fallbackCopy(code);
      }
    }

    function fallbackCopy(text) {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
        ctx.showToast('补丁代码已复制，请到 iframe 控制台粘贴执行');
      } catch (e) {
        ctx.showToast('复制失败，请手动选择复制');
      }
      document.body.removeChild(ta);
    }

    return { fetchHistory: async () => {}, send, clearHistory, saveCfg, loadCfgFromBackend, copyPatch };
  };
})();
