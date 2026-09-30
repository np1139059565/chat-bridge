// 抽屉根组件、状态管理与事件监听
(function () {
  const { createApp, ref, computed, watch, onMounted, nextTick } = Vue;
  const D = window.AIDrawer;
  const { h } = D;

  createApp({
    setup() {
      const view = ref('chat'); // 'chat' | 'settings'
      const connected = ref(false);
      const selecting = ref(false);
      const draft = ref('');
      const messages = ref([]);
      const selectedElements = ref([]);
      const toolCards = ref([]);   // 来自工具服务的工具调用卡片（与消息并列展示）
      const msgList = ref(null);
      const inputBox = ref(null);       // 消息输入框（用于按内容自适应高度）
      const stickToBottom = ref(true);  // 是否自动吸底：用户上滚后置 false，回到底部再置 true
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
      const theme = ref('light');        // 宿主页面明暗主题：light / dark（由内容脚本推送）

      /**
       * 把主题写到抽屉根元素上，CSS 令牌按 data-theme 切换。
       * 用属性而非 class：属性选择器优先级稳定，不与其它 class 规则冲突。
       * @param {string} t 'light' | 'dark'
       */
      function applyTheme(t) {
        const next = t === 'dark' ? 'dark' : 'light';
        theme.value = next;
        const root = document.documentElement;
        if (root) root.setAttribute('data-theme', next);
      }

      // 通知内容脚本：抽屉已挂载完成。内容脚本据此标记就绪并回推页面地址等。
      function reportReady() {
        window.parent.postMessage({ type: 'ai-debug-drawer-ready', source: 'ai-debug-drawer' }, '*');
      }

      // 请求内容脚本关闭抽屉：抽屉自身不做显隐，只发请求，
      // 由内容脚本统一负责移除 iframe 与停止轮询。
      function requestClose() {
        window.parent.postMessage({ type: 'ai-debug-close-request', source: 'ai-debug-drawer' }, '*');
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

      // 滚动到底部：仅在吸底状态为 true 时执行。
      // 用户手动上滚查看历史后 stickToBottom 置 false，新消息不再把视图拽回底部。
      function scrollToBottom() {
        if (!stickToBottom.value) return;
        nextTick(() => {
          const el = msgList.value;
          if (el) el.scrollTop = el.scrollHeight;
        });
      }

      // 消息区滚动监听：距底部小于阈值即视为「贴底」，恢复自动吸底。
      function onMessagesScroll() {
        const el = msgList.value;
        if (!el) return;
        const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
        stickToBottom.value = distance < 24;
      }

      // 输入框按内容自适应高度：先归零再按 scrollHeight 撑开，
      // 上限由 CSS 的 max-height 控制，超出后输入框内部滚动。
      function resizeInput() {
        nextTick(() => {
          const el = inputBox.value;
          if (!el) return;
          el.style.height = 'auto';
          el.style.height = el.scrollHeight + 'px';
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

      // 元素去重 / 还原：已选列表的唯一来源是内容脚本，实际操作由它完成。
      // 这里只按 selId 发请求，内容脚本处理后回传 elements-updated 整份列表，
      // 避免两处各持一份状态、以谁为准产生分歧。
      function dedupElement(selId) {
        window.parent.postMessage(
          { type: 'ai-debug-dedup-element', selId: selId, source: 'ai-debug-drawer' },
          '*'
        );
      }

      function restoreElement(selId) {
        window.parent.postMessage(
          { type: 'ai-debug-restore-element', selId: selId, source: 'ai-debug-drawer' },
          '*'
        );
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
        connected,
        messages,
        toolCards,
        msgList,
        inputBox,
        onMessagesScroll,
        resizeInput,
        draft,
        selecting,
        selectedElements,
        view,
        toast,
        drawerSide,
        switchSide,
        clearHistory: api.clearHistory,
        close: requestClose,
        toggleSelect,
        clearElements,
        removeElement,
        dedupElement,
        restoreElement,
        send: api.send,
        resendMessage: api.resendMessage,
      });

      // 已选去重键：同一文档内、DOM 内容相同的元素视为同一元素。
      // 与内容脚本 pushSelected 使用完全相同的规则，保证两边判断一致。
      // 不能只用选择器：同一元素在不同状态（展开 / 折叠等）下 DOM 内容不同，
      // 用户可能需要各选一份，用选择器判重会把后一次误判为重复。
      // DOM 内容为空时退回选择器，保证键始终可用。
      function selectedKey(el) {
        const dom = String((el && el.dom_html) || '');
        const sig = dom || ('\u0001' + String((el && el.selector) || ''));
        return String((el && el.page_url) || '') + '\u0000' + sig;
      }

      // 接受一个选中元素：未配置本地映射时仍允许选择。映射只决定 AI 能否定位
      // 到本地源码，不构成选择元素的前提，因此这里不做拦截。
      function acceptElement(el) {
        if (!el) return;
        // 重复选择同一元素：不入列，仅提示，避免列表出现重复条目
        const key = selectedKey(el);
        if (selectedElements.value.some((x) => selectedKey(x) === key)) {
          showToast('该元素已在已选列表中');
          return;
        }
        selectedElements.value.push(el);
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
        else resizeInput();
      });

      // 草稿内容变化（含发送后清空）都重算输入框高度，保证高度与内容一致
      watch(draft, () => resizeInput());

      onMounted(async () => {
        await initBackendUrl();
        reportReady();
        const stored = await chrome.storage.local.get(['aistyleCfg']);
        cfg.value = D.mergeCfg(stored.aistyleCfg);

        // 接收两个来源的消息：内容脚本（ai-debug-content）与 iframe 补丁（ai-debug-iframe）
        window.addEventListener('message', (ev) => {
          const d = ev.data;
          if (!d) return;
          const fromContent = d.source === 'ai-debug-content';
          const fromIframe = d.source === 'ai-debug-iframe';
          if (!fromContent && !fromIframe) return;
          if (fromContent && d.page_url) hostPageUrl.value = d.page_url;
          if (d.type === 'connection-state') {
            updateConnectionState(d.connected);
          } else if (d.type === 'host-theme') {
            // 内容脚本推送的宿主页面明暗主题：切换令牌，跟随宿主观感
            applyTheme(d.theme);
          } else if (d.type === 'element-selected') {
            acceptElement(d.element);
          } else if (d.type === 'elements-updated') {
            // 内容脚本回传的完整列表即唯一来源，直接采用。
            selectedElements.value = Array.isArray(d.elements) ? d.elements : [];
          } else if (d.type === 'page-urls') {
            pageUrls.value = Array.isArray(d.urls) ? d.urls : [];
          } else if (d.type === 'tool-card') {
            upsertToolCard(d);
          } else if (d.type === 'ai-debug-select-cancelled') {
            // 页面按 Esc 退出选择模式：同步抽屉按钮状态，避免按钮停留在「退出选择」
            selecting.value = false;
          } else if (d.type === 'append-reply') {
            // page_url 记录该回复来自哪个页面（内容脚本 postToDrawer 时自动带上），
            // 便于多页面同时调试时区分消息来源。
            D.dedupPush(messages, [
              {
                id: d.id || D.generateId(),
                role: 'assistant',
                text: d.text || '',
                page_url: d.page_url || '',
                timestamp: d.timestamp || Date.now()
              },
            ]);
            scrollToBottom();
          }
        });
      });

      return () => (view.value === 'settings' ? settingsRenderer.renderSettings() : chatRenderer.renderChat());
    },
  }).mount('#ai-debug-app');
})();
