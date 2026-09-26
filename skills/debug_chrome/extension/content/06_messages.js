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

    // 统一入口：生成选择器、构建数据、入列三步收敛在 A.selectElement
    A.selectElement(e.target);
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
        // 插件图标：抽屉存在则关闭，不存在则打开。
        // 开关由内容脚本直接掌控，不再绕经抽屉转发，
        // 这样抽屉被移除后图标仍能把它重新打开。
        A.log('插件图标被点击：抽屉当前' + (state.drawerIframe ? '已打开 → 关闭' : '已关闭 → 打开'));
        if (state.drawerIframe) A.closeDrawer();
        else A.openDrawer();
        return false;
      }
      if (type === 'ai-style-debug-start-select') {
        A.toggleSelectMode(true);
        sendResponse({ received: true });
        return true;
      }
      return false;
    });

    // 主世界脚本投递的「按标记选中」请求：
    // 主世界无法直接传元素引用过来，只能给元素打标记；这里按标记跨文档找回元素，
    // 完成选中后立即清除标记，不给页面留痕。
    window.addEventListener('message', (ev) => {
      const d = ev.data;
      if (!d || d.source !== 'ai-debug-main' || d.type !== 'select-by-mark') return;
      const el = A.findElementByMark(d.mark);
      // 无论成败都清标记：成功时不再需要，失败时避免残留属性污染页面 DOM
      if (el) {
        try { el.removeAttribute('data-ai-debug-pick'); } catch (e) {}
      }
      if (!el) {
        A.showToast('未找到目标元素：可能来自跨域 iframe，或元素已被移除');
        return;
      }
      A.selectElement(el);
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
      } else if (d.type === 'ai-debug-dedup-element') {
        A.dedupElementById(d.selId);
      } else if (d.type === 'ai-debug-restore-element') {
        A.restoreElementById(d.selId);
      } else if (d.type === 'ai-debug-drawer-ready') {
        // 抽屉挂载完成：标记就绪，并把宿主页面地址与可选 URL 列表推给它。
        A.markDrawerReady();
        A.postToDrawer({ type: 'host-page-url' });
        A.postToDrawer({ type: 'page-urls', urls: A.collectPageUrls() });
      } else if (d.type === 'ai-debug-close-request') {
        // 抽屉上的「关闭」按钮：彻底关闭抽屉（移除并停轮询）。
        A.closeDrawer();
      } else if (d.type === 'ai-debug-request-urls') {
        A.postToDrawer({ type: 'page-urls', urls: A.collectPageUrls() });
      } else if (d.type === 'ai-debug-set-side') {
        A.setDrawerSide(d.side);
      }
    });

    // 页面级鼠标 / 键盘监听不在此绑定：它们随抽屉开关attach / detach，
    // 抽屉关闭后页面上不留任何本扩展的交互监听。
  };

  /** Esc 退出选择模式：作为右键退出之外的兜底，保证用户总能退出。 */
  function onKeyDown(e) {
    if (!state.selectMode) return;
    if (e.key !== 'Escape' && e.keyCode !== 27) return;
    e.preventDefault();
    e.stopPropagation();
    A.toggleSelectMode(false);
    A.postToDrawer({ type: 'ai-debug-select-cancelled' });
    A.showToast('已退出元素选择模式');
  }

  /**
   * 绑定页面级交互监听：抽屉打开时调用。
   * 包含元素选择相关（中键选择 / 右键退出 / 高亮）与 Esc 兜底。
   * 这些监听只在抽屉存在时才有意义，关闭后必须解绑，不在宿主页面留痕。
   */
  A.attachPageListeners = function () {
    if (state.pageListenersAttached) return;
    state.pageListenersAttached = true;
    document.addEventListener('mouseover', onMouseOver, { capture: true });
    document.addEventListener('mouseout', onMouseOut, { capture: true });
    // 中键点击选择元素；右键单击退出选择模式。
    // 不注册左键 click / dblclick，因此左键单击与双击均不受影响，页面交互完全正常。
    document.addEventListener('mousedown', onMouseDown, { capture: true });
    document.addEventListener('auxclick', onAuxClick, { capture: true });
    document.addEventListener('contextmenu', onContextMenu, { capture: true });
    document.addEventListener('keydown', onKeyDown, { capture: true });
    // 选择模式下的十字光标：作用于宿主页面，提示当前处于点选状态。
    // 高亮框本身在 Shadow DOM 中，不受这里影响。
    const selectStyle = document.createElement('style');
    selectStyle.id = 'ai-style-debug-select-style';
    selectStyle.textContent = '.ai-style-select-mode, .ai-style-select-mode * { cursor: crosshair !important; }';
    document.head.appendChild(selectStyle);
  };

  /** 解绑页面级交互监听：抽屉关闭时调用，同时退出选择模式并清除高亮与光标样式。 */
  A.detachPageListeners = function () {
    if (!state.pageListenersAttached) return;
    state.pageListenersAttached = false;
    document.removeEventListener('mouseover', onMouseOver, { capture: true });
    document.removeEventListener('mouseout', onMouseOut, { capture: true });
    document.removeEventListener('mousedown', onMouseDown, { capture: true });
    document.removeEventListener('auxclick', onAuxClick, { capture: true });
    document.removeEventListener('contextmenu', onContextMenu, { capture: true });
    document.removeEventListener('keydown', onKeyDown, { capture: true });
    // 退出选择模式并隐藏高亮框 / 尺寸标签，恢复页面默认光标
    if (state.selectMode) A.toggleSelectMode(false);
    A.hideHighlight();
    const st = document.getElementById('ai-style-debug-select-style');
    if (st && st.parentNode) st.parentNode.removeChild(st);
  };
})();
