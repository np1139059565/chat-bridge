// 元素选择器（高亮层）：高亮框与尺寸标签的创建与缓存。
// 从 04b_element-selector.js 抽出，使该文件保持在行数上限内。
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  // 高亮层：直接挂在顶层文档，用一个零尺寸容器承载高亮框与尺寸标签。
  // 关键属性一律带 !important，尽量压过宿主网页的全局 CSS（如通配选择器、
  // transition、transform 等），保证高亮框始终可控、可见。
  A.getHighlightLayer = function () {
    if (state.highlightLayer && state.highlightLayer.isConnected) return state.highlightLayer;
    const host = document.createElement('div');
    host.id = 'ai-style-highlight-host';
    // 宿主本身不占位、不拦截事件；层级取上限，确保浮于页面之上
    host.style.cssText = 'position:fixed !important;top:0 !important;left:0 !important;'
      + 'width:0 !important;height:0 !important;z-index:2147483647 !important;pointer-events:none !important;';
    document.documentElement.appendChild(host);

    // 高亮框：实线双层描边 + 半透明填充，选择范围一目了然
    const box = document.createElement('div');
    box.className = 'ai-style-highlight-box';
    box.style.cssText = 'position:fixed !important;pointer-events:none !important;box-sizing:border-box !important;'
      + 'border:2px solid #1890ff !important;background:rgba(24,144,255,0.18) !important;'
      + 'box-shadow:0 0 0 1px rgba(255,255,255,0.9), 0 0 6px rgba(24,144,255,0.6) !important;'
      + 'border-radius:2px !important;transition:none !important;margin:0 !important;padding:0 !important;';

    // 尺寸标签栏：左侧是「标签名 宽×高」文字，右侧挂三个层级导航按钮。
    // 栏本身接收指针事件，使鼠标移到其上时算作「停在浮层内」而非页面元素；
    // 悬停逻辑据此保持高亮不跳动，用户才能稳定点到钻取按钮。
    const bar = document.createElement('div');
    bar.className = 'ai-style-highlight-bar';
    bar.style.cssText = 'position:fixed !important;pointer-events:auto !important;display:flex !important;'
      + 'align-items:center !important;gap:0 !important;'
      + 'font:11px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif !important;'
      + 'white-space:nowrap !important;box-shadow:0 1px 3px rgba(0,0,0,0.3) !important;'
      + 'border-radius:3px !important;overflow:hidden !important;margin:0 !important;';

    // 文字区：显示标签名与宽高
    const tagText = document.createElement('span');
    tagText.className = 'ai-style-highlight-tag-text';
    tagText.style.cssText = 'background:#1890ff !important;color:#fff !important;'
      + 'padding:1px 6px !important;margin:0 !important;';

    // 信息条：单独一行，显示选择器与源码字符数，不与按钮挤在同一行。
    // 优先贴在高亮框下方；下方空间不足时由 updateHighlight 改放到元素上方。
    const infoBar = document.createElement('div');
    infoBar.className = 'ai-style-highlight-info-bar';
    infoBar.style.cssText = 'position:fixed !important;pointer-events:none !important;'
      + 'background:#fffbe6 !important;color:#613400 !important;'
      + 'border:1px solid #ffe58f !important;border-radius:3px !important;'
      + 'font:11px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif !important;'
      + 'padding:1px 6px !important;margin:0 !important;max-width:560px !important;'
      + 'white-space:nowrap !important;overflow:hidden !important;text-overflow:ellipsis !important;'
      + 'box-shadow:0 1px 3px rgba(0,0,0,0.2) !important;display:none !important;';

    // 三个导航按钮的公共样式：小方块、独立底色，便于与文字区分
    const btnCss = 'pointer-events:auto !important;background:#0f6fd4 !important;color:#fff !important;'
      + 'border:none !important;font:inherit !important;line-height:1 !important;'
      + 'padding:3px 6px !important;margin:0 !important;cursor:pointer !important;';

    // 四个导航按钮：创建、加样式、绑事件一次完成
    const btns = A._buildHighlightButtons(btnCss);

    bar.appendChild(tagText);
    bar.appendChild(btns.up);
    bar.appendChild(btns.down);
    bar.appendChild(btns.sibling);
    bar.appendChild(btns.unlock);

    host.appendChild(box);
    host.appendChild(bar);
    host.appendChild(infoBar);
    state.highlightLayer = host;
    state.highlightBox = box;
    state.highlightTag = bar;        // 复用既有字段：hideHighlight 据此隐藏整条标签栏
    state.highlightBar = bar;        // 标签栏容器
    state.highlightTagText = tagText; // 标签栏内的文字节点
    state.highlightInfo = infoBar;    // 信息条（独立一行，不与按钮同行）
    // 按钮引用集中保存，供按可用性（有无父/子/兄弟、是否已冻结）显隐
    state.highlightBtns = btns;
    return host;
  };

  /**
   * 创建高亮标签栏里的四个导航按钮，并绑定点击事件。
   * 所有按钮共用同一份样式；点击时阻止冒泡，避免被页面逻辑截获。
   * @param {string} btnCss 按钮公共样式文本
   * @returns {Object} { up, down, sibling, unlock } 四个按钮元素
   */
  A._buildHighlightButtons = function (btnCss) {
    // 按钮定义：文字、提示、点击动作
    const defs = [
      { key: 'up', text: '↑', title: '上钻：选中当前元素的父元素', action: () => A.drillHighlight('up') },
      { key: 'down', text: '↓', title: '下钻：选中当前元素的第一个子元素', action: () => A.drillHighlight('down') },
      { key: 'sibling', text: '⇄', title: '兄弟切换：在同级兄弟元素间循环', action: () => A.drillHighlight('sibling') },
      { key: 'unlock', text: '✕', title: '解锁：解除锁定，高亮重新跟随鼠标', action: () => A.setSelectFrozen(false) },
    ];
    const out = {};
    defs.forEach((d) => {
      const btn = document.createElement('button');
      btn.className = 'ai-style-highlight-btn';
      btn.type = 'button';
      btn.textContent = d.text;
      btn.title = d.title;
      btn.style.cssText = btnCss;
      // 阻止事件冒泡到页面，避免点击被页面逻辑截获
      btn.addEventListener('click', (e) => {
        e.preventDefault(); e.stopPropagation(); d.action();
      });
      out[d.key] = btn;
    });
    return out;
  };
})();
