// 事件监听与消息处理
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  function onMouseOver(e) {
    if (!state.selectMode) return;
    if (A.isInsideDrawer(e.target)) return;
    // iframe 是替换元素：顶层的 mouseover 只能把 iframe 本身当作目标，
    // 鼠标一旦进入子文档，顶层不再收到事件，若此时画顶层高亮框，
    // 它会一直停在 iframe 这一层（且 z-index 高于子文档内补丁画的虚线框），
    // 表现为“蓝底实心框附着在 iframe 上，只有虚线框能选中内部元素”。
    // 因此遇到 iframe 目标时撤掉顶层高亮，把内部高亮交给 iframe 点选补丁。
    if (e.target && e.target.tagName === 'IFRAME') {
      A.hideHighlight();
      return;
    }
    A.updateHighlight(e.target);
  }

  function onMouseOut(e) {
    if (!state.selectMode) return;
    if (A.isInsideDrawer(e.relatedTarget)) return;
    A.hideHighlight();
  }

  // 选择元素：使用「鼠标中键（滚轮键）」点击触发。
  // 中键在网页上极少承载业务行为，用它选择既不碰左键单击、也不碰右键菜单，
  // 因此无需拦截任何常规鼠标手势，完全不影响页面交互。
  // 中键点击由 auxclick 事件承载（e.button === 1）。
  function onAuxClick(e) {
    if (!state.selectMode) return;
    if (e.button !== 1) return;   // 只处理中键
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

  // 选择模式下拦截「中键 mousedown」的默认行为：
  // 浏览器默认把中键按下当作「自动滚动」或「新标签打开链接」，
  // 需在 mousedown 阶段阻止，否则会干扰选择操作。
  // 注意：只在中键且选择模式下拦截，不影响其它按键。
  function onMouseDown(e) {
    if (!state.selectMode) return;
    if (e.button !== 1) return;   // 只处理中键
    if (A.isInsideDrawer(e.target)) return;
    e.preventDefault();
  }

  // 退出选择模式：使用「右键单击」触发。
  // 右键在多数页面不承载业务行为，作为「退出」手势直观且不与页面冲突。
  function onContextMenu(e) {
    if (!state.selectMode) return;
    if (A.isInsideDrawer(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    A.toggleSelectMode(false);
    A.postToDrawer({ type: 'ai-debug-select-cancelled' });
    A.showToast('已退出元素选择模式');
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
          // 保证两条选择路径（页面直接双击 / iframe 补丁双击）状态一致
          A.pushSelected(d.element);
        } else if (d.type === 'select-cancelled') {
          // iframe 内右键退出选择：同步顶层状态与抽屉按钮，避免状态不一致
          A.toggleSelectMode(false);
          A.postToDrawer({ type: 'ai-debug-select-cancelled' });
          A.showToast('已退出元素选择模式');
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
    // 中键点击选择元素；右键单击退出选择模式。
    // 不注册左键 click / dblclick，因此左键单击与双击均不受影响，页面交互完全正常。
    document.addEventListener('mousedown', onMouseDown, { capture: true });
    document.addEventListener('auxclick', onAuxClick, { capture: true });
    document.addEventListener('contextmenu', onContextMenu, { capture: true });

    // 选择模式下的十字光标：作用于宿主页面，提示当前处于点选状态。
    // 高亮框本身在 Shadow DOM 中，不受这里影响。
    const selectStyle = document.createElement('style');
    selectStyle.textContent = '.ai-style-select-mode, .ai-style-select-mode * { cursor: crosshair !important; }';
    document.head.appendChild(selectStyle);

    // Esc 退出选择模式：作为右键退出之外的兜底，保证用户总能退出。
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
