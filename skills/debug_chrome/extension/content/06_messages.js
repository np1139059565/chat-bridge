// 事件监听与消息处理
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  function onMouseOver(e) {
    if (!state.selectMode) return;
    if (A.isInsideDrawer(e.target)) return;
    A.updateHighlight(e.target);
  }

  function onMouseOut(e) {
    if (!state.selectMode) return;
    if (A.isInsideDrawer(e.relatedTarget)) return;
    A.hideHighlight();
  }

  function onClick(e) {
    if (!state.selectMode) return;
    if (A.isInsideDrawer(e.target)) return;
    e.preventDefault();
    e.stopPropagation();

    if (state.selectedElements.length >= A.MAX_ELEMENTS) {
      A.showToast(`最多选择 ${A.MAX_ELEMENTS} 个元素，已自动退出选择模式`);
      A.toggleSelectMode(false);
      return;
    }

    const el = e.target;
    const selectorInfo = A.generateSelector(el);

    if (!state.screenshotEnabled) {
      A.pushSelected(A.buildElementData(el, selectorInfo));
      return;
    }
    A.requestScreenshot()
      .then((shot) => A.pushSelected(A.buildElementData(el, selectorInfo), shot))
      .catch(() => A.pushSelected(A.buildElementData(el, selectorInfo)));
  }

  A.initEventListeners = function () {
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      const { type } = message || {};
      if (type === 'ai-debug-toggle-from-action') {
        A.postToDrawer({ type: 'ai-debug-toggle-request' });
        return false;
      }
      if (type === 'ai-style-debug-start-select') {
        A.toggleSelectMode(true);
        sendResponse({ received: true });
        return true;
      }
      return false;
    });

    // iframe 补丁回传的元素 / 就绪消息：转交给抽屉
    window.addEventListener('message', (ev) => {
      const d = ev.data;
      if (!d) return;
      if (d.source === 'ai-debug-iframe') {
        if (d.type === 'element-selected') {
          // 走统一入口：既更新内容脚本的已选列表，也通知抽屉，
          // 保证两条选择路径（页面直接点击 / iframe 补丁）状态一致
          A.pushSelected(d.element);
        } else if (d.type === 'patch-ready') {
          A.showToast('iframe 点选补丁已就绪：' + (d.frameUrl || ''));
        }
        return;
      }
    });

    window.addEventListener('message', (ev) => {
      const d = ev.data;
      if (!d || d.source !== 'ai-debug-drawer') return;
      if (d.type === 'ai-debug-toggle-select') {
        A.toggleSelectMode(d.selecting);
      } else if (d.type === 'ai-debug-remove-element') {
        // 优先按 selId 删除（稳定），无 selId 时退回按下标
        if (d.selId) A.removeElementById(d.selId);
        else A.removeElementAt(d.index);
      } else if (d.type === 'ai-debug-clear-elements') {
        A.clearElements();
      } else if (d.type === 'ai-debug-drawer-state') {
        A.markDrawerReady();
        state.drawerOpen = !!d.open;
        A.applyDrawerShape(state.drawerOpen);
        if (state.drawerOpen) {
          A.postToDrawer({ type: 'host-page-url' });
          A.postToDrawer({ type: 'page-urls', urls: A.collectPageUrls() });
          A.tick();
        }
      } else if (d.type === 'ai-debug-request-urls') {
        A.postToDrawer({ type: 'page-urls', urls: A.collectPageUrls() });
      } else if (d.type === 'ai-debug-set-side') {
        A.setDrawerSide(d.side);
      }
    });

    document.addEventListener('mouseover', onMouseOver, { capture: true });
    document.addEventListener('mouseout', onMouseOut, { capture: true });
    document.addEventListener('click', onClick, { capture: true });

    // 选择模式下的十字光标：作用于宿主页面，提示当前处于点选状态。
    // 高亮框本身在 Shadow DOM 中，不受这里影响。
    const selectStyle = document.createElement('style');
    selectStyle.textContent = '.ai-style-select-mode, .ai-style-select-mode * { cursor: crosshair !important; }';
    document.head.appendChild(selectStyle);

    // Esc/右键 退出选择模式：选择模式会拦截页面点击，一旦开启就应能可靠地退出，
    // 否则用户会被困在无法点击页面的状态里。
    document.addEventListener('contextmenu', (e) => {
      if (!state.selectMode) return;
      e.preventDefault();
      e.stopPropagation();
      A.toggleSelectMode(false);
      A.postToDrawer({ type: 'ai-debug-select-cancelled' });
      A.showToast('已退出元素选择模式');
    }, { capture: true });
    document.addEventListener('keydown', (e) => {
      if (!state.selectMode) return;
      if (e.key !== 'Escape' && e.keyCode !== 27) return;
      e.preventDefault();
      e.stopPropagation();
      A.toggleSelectMode(false);
      A.postToDrawer({ type: 'ai-debug-select-cancelled' });
      A.showToast('已退出元素选择模式');
    }, { capture: true });
  };
})();
