// 模块：高亮层与层级导航
// 用途：构建/维护高亮浮层（高亮框、尺寸标签栏、钻取按钮、信息条），
//       以及悬停冻结、上下钻取与兄弟切换、高亮位置刷新与隐藏。
// 依赖：content/00_namespace.js（命名空间 A 与共享状态 state）
// 说明：所有对外能力均挂到 window.AIStyleDebug（A）上，供元素选择与消息模块调用。
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;

  // 高亮层：直接挂在顶层文档，用一个零尺寸容器承载高亮框与尺寸标签。
  // 关键属性一律带 !important，尽量压过宿主网页的全局 CSS（如通配选择器、
  // transition、transform 等），保证高亮框始终可控、可见。
  A.getHighlightLayer = function () {
    // 已创建且仍挂在文档上：直接复用，避免重复挂载
    if (state.highlightLayer && state.highlightLayer.isConnected) return state.highlightLayer;
    // 宿主容器：零尺寸、不拦截事件、层级取上限，确保浮于页面之上
    const host = document.createElement('div');
    host.id = 'ai-style-highlight-host';
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

    // 上钻：把高亮移到父元素
    const upBtn = document.createElement('button');
    upBtn.className = 'ai-style-highlight-btn';
    upBtn.type = 'button';
    upBtn.textContent = '↑';
    upBtn.title = '上钻：选中当前元素的父元素';
    upBtn.style.cssText = btnCss;

    // 下钻：把高亮移到第一个子元素
    const downBtn = document.createElement('button');
    downBtn.className = 'ai-style-highlight-btn';
    downBtn.type = 'button';
    downBtn.textContent = '↓';
    downBtn.title = '下钻：选中当前元素的第一个子元素';
    downBtn.style.cssText = btnCss;

    // 兄弟切换：在同级兄弟元素间循环
    const sibBtn = document.createElement('button');
    sibBtn.className = 'ai-style-highlight-btn';
    sibBtn.type = 'button';
    sibBtn.textContent = '⇄';
    sibBtn.title = '兄弟切换：在同级兄弟元素间循环';
    sibBtn.style.cssText = btnCss;

    // 解锁：解除悬停冻结，让高亮重新跟随鼠标
    const unlockBtn = document.createElement('button');
    unlockBtn.className = 'ai-style-highlight-btn';
    unlockBtn.type = 'button';
    unlockBtn.textContent = '✕';
    unlockBtn.title = '解锁：解除锁定，高亮重新跟随鼠标';
    unlockBtn.style.cssText = btnCss;

    // 阻止事件冒泡到页面，避免点击按钮被页面逻辑截获；
    // 左键点击不在扩展的选中手势范围内，因此不会误触发选中。
    upBtn.addEventListener('click', (e) => {
      e.preventDefault(); e.stopPropagation(); A.drillHighlight('up');
    });
    downBtn.addEventListener('click', (e) => {
      e.preventDefault(); e.stopPropagation(); A.drillHighlight('down');
    });
    sibBtn.addEventListener('click', (e) => {
      e.preventDefault(); e.stopPropagation(); A.drillHighlight('sibling');
    });
    unlockBtn.addEventListener('click', (e) => {
      e.preventDefault(); e.stopPropagation(); A.setSelectFrozen(false);
    });

    // 按「文字 → 钻取按钮 → 解锁按钮」的顺序装配标签栏
    bar.appendChild(tagText);
    bar.appendChild(upBtn);
    bar.appendChild(downBtn);
    bar.appendChild(sibBtn);
    bar.appendChild(unlockBtn);

    // 高亮框、标签栏、信息条统一挂到宿主容器
    host.appendChild(box);
    host.appendChild(bar);
    host.appendChild(infoBar);
    // 状态回存：供其它函数按字段取用
    state.highlightLayer = host;
    state.highlightBox = box;
    state.highlightTag = bar;        // 复用既有字段：hideHighlight 据此隐藏整条标签栏
    state.highlightBar = bar;        // 标签栏容器
    state.highlightTagText = tagText; // 标签栏内的文字节点
    state.highlightInfo = infoBar;    // 信息条（独立一行，不与按钮同行）
    // 按钮引用集中保存，供按可用性（有无父/子/兄弟、是否已冻结）显隐
    state.highlightBtns = {
      up: upBtn, down: downBtn, sibling: sibBtn, unlock: unlockBtn
    };
    return host;
  };

  /** 悬停选元素是否处于冻结状态。 */
  A.isSelectFrozen = function () {
    return !!state.selectFrozen;
  };

  /**
   * 设置/解除悬停冻结，并同步标签栏的视觉状态。
   * 冻结后，鼠标悬停与移出都不再改动高亮，高亮锁定在当前元素上，
   * 按钮不会因标签栏挪位而漂移，可稳定连续点击。
   * @param {boolean} frozen 是否冻结
   */
  A.setSelectFrozen = function (frozen) {
    const wasFrozen = !!state.selectFrozen;
    state.selectFrozen = !!frozen;
    const bar = state.highlightBar;
    if (bar) {
      // 冻结时给标签栏加黄色描边，提示「已锁定」，用户知道当前可安心操作按钮
      bar.style.boxShadow = frozen
        ? '0 0 0 2px #faad14, 0 1px 3px rgba(0,0,0,0.3)'
        : '0 1px 3px rgba(0,0,0,0.3)';
    }
    // 仅在「刚刚进入锁定」时提示一次，连续钻取不再重复弹出，避免刷屏
    if (frozen && !wasFrozen) {
      A.showToast('已锁定当前元素，可用按钮、方向键连续钻取；按 ✕ 或 Esc 解锁');
    }
    // 冻结状态变化影响解锁按钮（✕）的显隐，立即刷新标签栏
    A.updateBarState(state.highlightTarget);
  };

  /**
   * 刷新标签栏：按元素可用性显隐钻取按钮，按冻结状态显隐解锁按钮，并更新基础信息。
   *  - 钻取按钮（↑/↓/⇄）：只按元素是否真有父/子/兄弟显隐，与冻结状态无关；
   *    未冻结时同样显示，因为它们是进入冻结的入口，隐藏会导致永远无法用按钮进入冻结。
   *  - 解锁按钮（✕）：仅在冻结时显示，无锁可解时无需出现。
   *  - 信息区：显示选择器与源码字符数，便于确认选中目标，减少盲选。
   * @param {Element|null} el 当前高亮元素
   */
  A.updateBarState = function (el) {
    const btns = state.highlightBtns;
    if (!btns) return;
    const frozen = !!state.selectFrozen;
    // 钻取按钮只看元素结构是否支持该方向，与冻结状态无关
    let canUp = false;
    let canDown = false;
    let canSib = false;
    if (el && el.isConnected) {
      const parent = el.parentElement;
      canUp = !!(parent && parent !== document.body && parent !== document.documentElement);
      canDown = !!el.firstElementChild;
      if (parent) canSib = parent.children.length > 1;
    }
    const show = (btn, visible) => {
      if (btn) btn.style.display = visible ? 'inline-block' : 'none';
    };
    show(btns.up, canUp);
    show(btns.down, canDown);
    show(btns.sibling, canSib);
    // 解锁按钮只在冻结时出现：它是「退出锁定」的入口，无锁可解时不必显示
    show(btns.unlock, frozen);
    // 信息区：选择器 + 源码字符数
    const info = state.highlightInfo;
    if (!info) return;
    if (el && el.isConnected) {
      const selectorInfo = A.generateSelector(el);
      const chars = (el.outerHTML || '').length;
      info.textContent = selectorInfo.selector + ' · ' + chars + ' 字符';
      info.title = selectorInfo.selector;
    } else {
      info.textContent = '';
      info.title = '';
    }
  };

  /**
   * 层级导航：把高亮按方向移动到相邻元素。
   * @param {string} dir 'up'（父元素）/ 'down'（第一个子元素）/ 'sibling'（后一个兄弟）
   *   / 'sibling-prev'（前一个兄弟）
   */
  A.drillHighlight = function (dir) {
    const cur = state.highlightTarget;
    if (!cur || !cur.isConnected) {
      A.showToast('当前没有可导航的元素，请先把鼠标移到元素上');
      return;
    }
    // 确认有目标后再进入冻结锁定：标签栏挪走后，浏览器会按新的鼠标命中重新派发
    // mouseover/mouseout；不冻结时高亮会被瞬间改写、栏位来回漂移，按钮难以点准。
    A.setSelectFrozen(true);
    let next = null;
    if (dir === 'up') {
      const parent = cur.parentElement;
      // 到 body / html 为止，不再往上
      if (parent && parent !== document.body && parent !== document.documentElement) next = parent;
      if (!next) { A.showToast('已到最外层，无法继续上钻'); return; }
    } else if (dir === 'down') {
      next = cur.firstElementChild;
      if (!next) { A.showToast('该元素没有子元素，无法下钻'); return; }
    } else if (dir === 'sibling' || dir === 'sibling-prev') {
      const parent = cur.parentElement;
      if (!parent) { A.showToast('该元素没有兄弟元素'); return; }
      const siblings = Array.from(parent.children);
      if (siblings.length <= 1) { A.showToast('该元素没有其它兄弟元素'); return; }
      const idx = siblings.indexOf(cur);
      // 正/反向都首尾回绕，形成循环
      const step = dir === 'sibling-prev' ? -1 : 1;
      next = siblings[(idx + step + siblings.length) % siblings.length];
    } else {
      return;
    }
    // 新目标可能不在视口内，先滚动到可见位置，再刷新高亮
    try { next.scrollIntoView({ block: 'nearest', inline: 'nearest' }); } catch (e) { /* 忽略 */ }
    A.updateHighlight(next);
  };

  /**
   * 把高亮框、标签栏与信息条刷新到目标元素上。
   * @param {Element} el 目标元素
   */
  A.updateHighlight = function (el) {
    A.getHighlightLayer();
    const rect = el.getBoundingClientRect();
    const box = state.highlightBox;
    // 高亮框：完全贴合目标元素的位置与尺寸
    box.style.left = rect.left + 'px';
    box.style.top = rect.top + 'px';
    box.style.width = rect.width + 'px';
    box.style.height = rect.height + 'px';
    box.style.display = 'block';

    // 记录当前高亮目标：钻取按钮据此在 DOM 中上下移动
    state.highlightTarget = el;

    // 标签栏贴在元素左上角上方；靠近视口顶部时改放到元素内侧，避免被裁掉
    const tagText = state.highlightTagText;
    if (tagText) {
      tagText.textContent = el.tagName.toLowerCase() + ' '
        + Math.round(rect.width) + '×' + Math.round(rect.height);
    }
    const bar = state.highlightBar;
    if (bar) {
      bar.style.display = 'flex';
      bar.style.left = rect.left + 'px';
      bar.style.top = (rect.top >= 20 ? rect.top - 18 : rect.top) + 'px';
    }
    // 信息条独立一行：默认贴在高亮框下方；下方空间不足（超出视口底部）时改放到元素上方。
    // 下方那一大块区域正是可用空间，信息条放这里不挤按钮，也更接近被选元素。
    const infoBar = state.highlightInfo;
    if (infoBar) {
      const infoTop = (rect.bottom + 22 > window.innerHeight)
        ? Math.max(0, rect.top - 18)
        : rect.bottom + 2;
      infoBar.style.left = rect.left + 'px';
      infoBar.style.top = infoTop + 'px';
      infoBar.style.display = 'block';
    }
    // 同步按钮显隐与信息：钻取按钮按元素结构显隐，解锁按钮按冻结状态显隐
    A.updateBarState(el);
  };

  /** 隐藏高亮浮层各部分，并解除冻结、清空高亮目标。 */
  A.hideHighlight = function () {
    if (state.highlightBox) state.highlightBox.style.display = 'none';
    if (state.highlightBar) state.highlightBar.style.display = 'none';
    if (state.highlightInfo) state.highlightInfo.style.display = 'none';
    state.highlightTarget = null;
    // 隐藏即结束本轮操作，解除冻结，恢复为跟随鼠标
    A.setSelectFrozen(false);
  };
})();
