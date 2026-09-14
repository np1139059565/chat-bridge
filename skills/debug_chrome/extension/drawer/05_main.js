// 抽屉根组件、状态管理与事件监听
(function () {
  const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;
  const D = window.AIDrawer;
  const { h } = D;

  createApp({
    setup() {
      const view = ref('chat'); // 'chat' | 'settings'
      const open = ref(false);
      const connected = ref(false);
      const selecting = ref(false);
      const draft = ref('');
      const messages = ref([]);
      const selectedElements = ref([]);
      const toolCards = ref([]);   // 来自工具服务的工具调用卡片（与消息并列展示）
      const msgList = ref(null);
      const backendUrl = ref('http://127.0.0.1:5000');
      const hostPageUrl = ref('');
      const toast = ref('');
      let toastTimer = null;

      function showToast(text) {
        toast.value = text;
        if (toastTimer) clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
          toast.value = '';
          toastTimer = null;
        }, 2500);
      }

      const cfg = ref(D.clone(D.DEFAULT_CFG));
      const cfgStatus = ref('');
      const cfgStatusClass = computed(() => {
        if (cfgStatus.value.startsWith('失败') || cfgStatus.value.startsWith('错误')) return 'error';
        if (cfgStatus.value.startsWith('成功')) return 'ok';
        return '';
      });

      async function initBackendUrl() {
        try {
          const stored = await chrome.storage.local.get(['aistyleCfg', 'backendUrl']);
          backendUrl.value = stored.backendUrl || (stored.aistyleCfg && stored.aistyleCfg.backend_url) || backendUrl.value;
        } catch (e) {}
      }

      const drawerSide = ref('right');   // 抽屉挂靠侧：right / left

      function reportDrawerState() {
        window.parent.postMessage({ type: 'ai-debug-drawer-state', open: open.value, source: 'ai-debug-drawer' }, '*');
      }

      // 切换挂靠侧：通知内容脚本调整抽屉形状
      function switchSide() {
        drawerSide.value = drawerSide.value === 'left' ? 'right' : 'left';
        window.parent.postMessage(
          { type: 'ai-debug-set-side', side: drawerSide.value, source: 'ai-debug-drawer' },
          '*'
        );
        try { chrome.storage.local.set({ aistyleDrawerSide: drawerSide.value }); } catch (e) {}
      }

      function toggle() {
        open.value = !open.value;
        reportDrawerState();
      }

      function scrollToBottom() {
        nextTick(() => {
          const el = msgList.value;
          if (el) el.scrollTop = el.scrollHeight;
        });
      }

      function addSystem(text) {
        messages.value.push({ id: D.generateId(), role: 'system', text, timestamp: Date.now() });
        scrollToBottom();
      }

      // 工具调用卡片：按 id 新增或更新（执行中 → 完成）
      function upsertToolCard(d) {
        const idx = toolCards.value.findIndex((c) => c.id === d.id);
        const card = {
          id: d.id,
          tool: d.tool || '',
          params: d.params || {},
          status: d.status || 'running',
          result: d.result || null,
          timestamp: d.timestamp || Date.now(),
        };
        if (idx >= 0) toolCards.value[idx] = card;
        else toolCards.value.push(card);
        scrollToBottom();
      }

      function updateConnectionState(state) {
        connected.value = state;
      }

      function toggleSelect() {
        selecting.value = !selecting.value;
        window.parent.postMessage({ type: 'ai-debug-toggle-select', selecting: selecting.value, source: 'ai-debug-drawer' }, '*');
      }

      // 移除单个元素：只发请求，由内容脚本作为唯一来源删除后回传 elements-updated。
      // 用 selId 定位（稳定），并附带下标作为兜底。
      function removeElement(selId, idx) {
        window.parent.postMessage(
          { type: 'ai-debug-remove-element', selId: selId, index: idx, source: 'ai-debug-drawer' },
          '*'
        );
      }

      function clearElements() {
        selectedElements.value = [];
        window.parent.postMessage({ type: 'ai-debug-clear-elements', source: 'ai-debug-drawer' }, '*');
      }

      // 组装 API 与渲染工厂
      const api = D.createApi({
        backendUrl,
        messages,
        toolCards,
        draft,
        connected,
        hostPageUrl,
        selectedElements,
        cfg,
        cfgStatus,
        scrollToBottom,
        addSystem,
        showToast,
      });

      const chatRenderer = D.createChatRenderer({
        open,
        connected,
        messages,
        toolCards,
        msgList,
        draft,
        selecting,
        selectedElements,
        view,
        toast,
        drawerSide,
        switchSide,
        clearHistory: api.clearHistory,
        toggle,
        toggleSelect,
        clearElements,
        removeElement,
        send: api.send,
      });

      // 接受一个选中元素：先按 URL 映射校验；未配置映射的 URL 拒绝选择并提示
      function acceptElement(el) {
        if (!el) return;
        const m = D.matchUrlMapping(cfg.value.url_mappings, el.page_url || '');
        if (!m) {
          showToast('该页面未配置本地工程映射，无法选择元素。请到设置里添加 URL 与本地路径的映射。');
          return;
        }
        selectedElements.value.push(el);
        if (!open.value) {
          open.value = true;
          reportDrawerState();
        }
      }

      // 当前页面自动列出的 URL（去参数，含 iframe）
      const pageUrls = ref([]);

      // 取某 URL 已配置的映射项
      function mappingFor(url) {
        return (cfg.value.url_mappings || []).find((m) => m && m.url_prefix === url) || null;
      }

      // 为某 URL 填写 / 更新本地路径；清空则移除该映射
      function setMappingPath(url, localPath) {
        if (!Array.isArray(cfg.value.url_mappings)) cfg.value.url_mappings = [];
        const idx = cfg.value.url_mappings.findIndex((m) => m && m.url_prefix === url);
        if (!localPath) {
          if (idx >= 0) cfg.value.url_mappings.splice(idx, 1);
          return;
        }
        if (idx >= 0) cfg.value.url_mappings[idx].local_path = localPath;
        else cfg.value.url_mappings.push({ url_prefix: url, local_path: localPath });
      }

      function refreshUrls() {
        window.parent.postMessage({ type: 'ai-debug-request-urls', source: 'ai-debug-drawer' }, '*');
      }

      const settingsRenderer = D.createSettingsRenderer({
        cfg,
        view,
        saveCfg: api.saveCfg,
        loadCfgFromBackend: api.loadCfgFromBackend,
        pageUrls,
        mappingFor,
        setMappingPath,
        refreshUrls,
        copyPatch: api.copyPatch,
        cfgStatus,
        cfgStatusClass,
      });

      // 进入设置页时自动拉取一次页面 URL 列表
      watch(view, (v) => {
        if (v === 'settings') refreshUrls();
      });

      onMounted(async () => {
        await initBackendUrl();
        reportDrawerState();
        const stored = await chrome.storage.local.get(['aistyleCfg']);
        cfg.value = D.mergeCfg(stored.aistyleCfg);

        // 接收两个来源的消息：内容脚本（ai-debug-content）与 iframe 补丁（ai-debug-iframe）
        window.addEventListener('message', (ev) => {
          const d = ev.data;
          if (!d) return;
          const fromContent = d.source === 'ai-debug-content';
          const fromIframe = d.source === 'ai-debug-iframe';
          if (!fromContent && !fromIframe) return;
          if (fromContent && d.pageUrl) hostPageUrl.value = d.pageUrl;
          if (d.type === 'connection-state') {
            updateConnectionState(d.connected);
          } else if (d.type === 'element-selected') {
            acceptElement(d.element);
          } else if (d.type === 'elements-updated') {
            // 内容脚本回传的完整列表可能含抽屉已拒绝的元素（未配置映射），
            // 这里按同一规则过滤，保证两边列表一致、下标不会错位。
            const list = Array.isArray(d.elements) ? d.elements : [];
            selectedElements.value = list.filter((el) => !!D.matchUrlMapping(cfg.value.url_mappings, (el && el.page_url) || ''));
          } else if (d.type === 'page-urls') {
            pageUrls.value = Array.isArray(d.urls) ? d.urls : [];
          } else if (d.type === 'tool-card') {
            upsertToolCard(d);
          } else if (d.type === 'ai-debug-select-cancelled') {
            // 页面按 Esc 退出选择模式：同步抽屉按钮状态，避免按钮停留在「退出选择」
            selecting.value = false;
          } else if (d.type === 'append-reply') {
            D.dedupPush(messages, [
              { id: d.id || D.generateId(), role: 'assistant', text: d.text || '', timestamp: d.timestamp || Date.now() },
            ]);
            scrollToBottom();
          } else if (d.type === 'ai-debug-toggle-request') {
            toggle();
          }
        });
      });

      return () => (view.value === 'settings' ? settingsRenderer.renderSettings() : chatRenderer.renderChat());
    },
  }).mount('#ai-debug-app');
})();
