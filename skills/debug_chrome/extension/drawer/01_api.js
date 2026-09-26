// 抽屉业务逻辑：与工具服务交互
//
// 发送链路：把用户需求与已选元素封装为外部卡片，POST /api/cards 挂起等待，
// 工具服务渲染卡片、自动发网页 AI；采用「发送即结束」，投递后立即返回确认。
// 任务进展由网页 AI 通过 push_message 主动推送到抽屉。
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
    /**
     * 组装并投递一张外部卡片。发送与重新发送共用此逻辑，避免两处实现漂移。
     * @param {string} text 需求正文
     * @param {Array} elements 已选元素列表
     * @returns {Promise<boolean>} 是否登记成功
     */
    async function postCard(text, elements) {
      // 剔除仅供本地还原用的备份字段 dom_html_full：它是完整 DOM，
      // 若随卡片一起发出，体积又会回到压缩前，去重就白做了。
      // 用浅拷贝剔除，不动原对象，保证本地仍可「还原」。
      const wireElements = (elements || []).map((el) => {
        const copy = Object.assign({}, el);
        delete copy.dom_html_full;
        return copy;
      });
      const body = {
        type: 'external-call',
        title: '样式调试需求',
        content: buildCardContent(text, wireElements, ctx.cfg.value.url_mappings),
        payload: { elements: wireElements, page_url: ctx.hostPageUrl.value },
      };
      try {
        const res = await fetch(`${ctx.backendUrl.value}/api/cards`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!data.success) {
          ctx.showToast('卡片发送失败：' + (data.error || '未知错误'));
          return false;
        }
        // 外部卡片采用「发送即结束」：登记成功即完成，无需等待。
        // 真正的任务进展由网页 AI 用 push_message 主动推送到本抽屉。
        return true;
      } catch (e) {
        ctx.showToast('发送失败：无法连接到工具服务');
        return false;
      }
    }

    async function send() {
      const text = ctx.draft.value.trim();
      if (!text) return;
      const elements = ctx.selectedElements.value.slice();
      // 先投递卡片，再记录消息：这次请求本身就是最直接的连接测试。
      // 成功才落消息、清空输入；失败则提示并保留输入，用户可重试。
      const ok = await postCard(text, elements);
      if (!ok) return;
      const userMsg = {
        id: D.generateId(),
        role: 'user',
        text,
        elements,
        timestamp: Date.now(),
      };
      D.dedupPush(ctx.messages, [userMsg]);
      ctx.draft.value = '';
      ctx.selectedElements.value = [];
      window.parent.postMessage({ type: 'ai-debug-clear-elements', source: 'ai-debug-drawer' }, '*');
      ctx.scrollToBottom();
    }

    /**
     * 重新发送某条已发出的用户消息。
     * 用于 chat-bridge 未收到消息（例如当时后端未就绪）时补发，
     * 不新增消息条目，也不改动原始已选元素。
     * @param {Object} msg 用户消息对象（须含 text 与 elements）
     */
    async function resendMessage(msg) {
      if (!msg) return;
      // 与首次发送一致：直接投递，用请求本身的成败判断连接。
      await postCard(String(msg.text || ''), msg.elements || []);
      ctx.scrollToBottom();
    }

    function clearHistory() {
      ctx.messages.value = [];
      // 工具卡片与消息同属会话内容，一并清空
      if (ctx.toolCards) ctx.toolCards.value = [];
      D.MSG_ID_SET.clear();
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

    return { fetchHistory: async () => {}, send, resendMessage, clearHistory, saveCfg, loadCfgFromBackend, copyPatch };
  };
})();
