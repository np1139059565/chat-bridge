// 元素选择器（续）：选择模式、高亮层、已选元素管理与统一选中入口
(function () {
  const A = window.AIStyleDebug;
  const state = A.state;


  A.isInsideDrawer = function (el) {
    const frame = document.getElementById(A.DRAWER_IFRAME_ID);
    if (!frame) return false;
    return frame === el || frame.contains(el);
  };

  A.toggleSelectMode = function (active) {
    state.selectMode = active;
    if (state.selectMode) {
      document.body.classList.add('ai-style-select-mode');
      A.showToast('已进入元素选择模式，鼠标中键（滚轮键）点击页面元素即可连续多选；右键单击或按 Esc 退出');
    } else {
      document.body.classList.remove('ai-style-select-mode');
      A.hideHighlight();
    }
    A.broadcastSelectToIframes(active);
  };

  // 向页面内所有 iframe（含 Shadow DOM 中的抽屉 iframe）广播选择模式开关。
  // 装了点选补丁的 iframe 会据此在自身文档内启用点选，
  // 解决「iframe 内元素无法被点选」的问题。
  A.broadcastSelectToIframes = function (active) {
    const frames = A.collectAllIframes();
    for (let i = 0; i < frames.length; i++) {
      try {
        if (frames[i].contentWindow) {
          frames[i].contentWindow.postMessage(
            { source: 'ai-debug-parent', type: 'toggle-select', selecting: !!active },
            '*'
          );
        }
      } catch (e) { /* 跨域 iframe 忽略 */ }
    }
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

  A.updateHighlight = function (el) {
    A.getHighlightLayer();
    const rect = el.getBoundingClientRect();
    const box = state.highlightBox;
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

  A.hideHighlight = function () {
    if (state.highlightBox) state.highlightBox.style.display = 'none';
    if (state.highlightBar) state.highlightBar.style.display = 'none';
    if (state.highlightInfo) state.highlightInfo.style.display = 'none';
    state.highlightTarget = null;
    // 隐藏即结束本轮操作，解除冻结，恢复为跟随鼠标
    A.setSelectFrozen(false);
  };

  // 给每个已选元素分配唯一 selId：抽屉与内容脚本据此增删，
  // 避免用下标定位元素带来的错位。
  let _selSeq = 0;
  function nextSelId() {
    _selSeq += 1;
    return 'sel-' + Date.now() + '-' + _selSeq;
  }

  // 去重键：同一文档内、DOM 内容相同的元素视为同一元素。
  // 不能只用选择器去重：同一元素在不同状态下的 DOM 内容不同，用户可能
  // 需要把「展开态」与「折叠态」各选一份，用选择器判重会把后一次误当作重复。
  // DOM 内容为空时退回选择器，保证键始终可用。
  function selectedKey(data) {
    const dom = String(data.dom_html || '');
    const sig = dom || ('\u0001' + String(data.selector || ''));
    return String(data.page_url || '') + '\u0000' + sig;
  }

  A.pushSelected = function (elementData, screenshot) {
    if (screenshot) elementData.screenshot = screenshot;
    const key = selectedKey(elementData);
    // 已选过同一元素：跳过入列，只回传当前完整列表，保持抽屉与内容脚本一致
    if (state.selectedElements.some((el) => selectedKey(el) === key)) {
      A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
      return false;
    }
    if (!elementData.selId) elementData.selId = nextSelId();
    state.selectedElements.push(elementData);
    A.postToDrawer({ type: 'element-selected', element: elementData });
    return true;
  };

  // 元素去重（压缩）：仅当选择器相同时可用。
  // 以同选择器的首个元素为基准，把当前元素 DOM 中「与基准相同的公共前后缀」
  // 用省略标记代替，只保留约 2% 的样本让人知道此处有省略；差异部分完整保留。
  // 结果写入 dom_html（回传给 AI 的就是它），原始完整内容另存 dom_html_full
  // （仅本地保留，发送给 AI 前会剔除），因此可随时还原。
  // 计算 dom 中哪些 token 属于与 base 的公共子序列（按顺序匹配）。
  // 不用「集合有无」判定：那会忽略顺序，dom 中结构上独有的片段只要文字在 base
  // 别处出现过就会被误判为公共而省略。这里用最长公共子序列，只有按顺序能对上的
  // token 才算公共；对不上的一定是 dom 的差异，调用方据此原样保留。
  // token 过多时退回「token 级公共前后缀」，避免 O(n*m) 的内存与耗时。
  A.commonTokenFlags = function (baseTokens, tokens) {
    const n = baseTokens.length;
    const m = tokens.length;
    const flags = new Array(m);
    for (let k = 0; k < m; k++) flags[k] = false;
    // 贪心顺序匹配：不设规模上限，也不做「超限就退化成前后缀」的兜底。
    // 真实 DOM 的 token 数可能上千，一旦退化，中间大段公共内容（如带几千字符
    // accept 列表的 <input>）就无法被省略，出现「该省的没省」。
    // 两边按顺序推进，相等即记为公共；失配时在小窗口内找最近的重同步点，
    // 被跳过的 dom token 一律判为差异、原样保留（宁可少省，绝不吞掉差异）。
    let a = 0;
    let b = 0;
    const WINDOW = 40;
    while (b < m) {
      if (a < n && baseTokens[a] === tokens[b]) {
        flags[b] = true;
        a += 1;
        b += 1;
        continue;
      }
      const maxK = Math.min(WINDOW, n - a);
      const maxL = Math.min(WINDOW, m - b);
      let best = null;
      for (let k = 0; k <= maxK; k++) {
        for (let l = 0; l <= maxL; l++) {
          if (k + l === 0) continue;
          if (a + k < n && b + l < m && baseTokens[a + k] === tokens[b + l]) {
            const cost = k + l;
            if (!best || cost < best.cost) best = { k: k, l: l, cost: cost };
            break;
          }
        }
      }
      if (!best) { b += 1; continue; }
      a += best.k;
      b += best.l;
    }
    return flags;
  };

  A.compactDomAgainst = function (baseDom, dom) {
    if (!baseDom || !dom || baseDom === dom) return dom;
    // 按 '<' 边界切分为 token。
    // 匹配用「按顺序的公共子序列」，保证 dom 中独有的片段（哪怕文字与 base 别处相同）
    // 只要顺序对不上就被判为差异、原样保留，不再出现整块结构被误吞的情况。
    const splitTokens = (s) => s.split(/(?=<)/);
    const baseTokens = splitTokens(baseDom);
    const tokens = splitTokens(dom);
    const common = A.commonTokenFlags(baseTokens, tokens);

    const out = [];
    let i = 0;
    while (i < tokens.length) {
      // 独有 token：直接保留
      if (!common[i]) { out.push(tokens[i]); i += 1; continue; }
      // 收集一段连续的公共 token
      let j = i;
      let runChars = 0;
      while (j < tokens.length && common[j]) {
        runChars += tokens[j].length;
        j += 1;
      }
      const runStr = tokens.slice(i, j).join('');
      // 公共段按「字符数」判断是否压缩，不能按 token 个数：
      // 单个超长 token（如带几千字符 accept 列表的 <input>）虽然只占 1 个 token，
      // 体积却很大，按 token 个数判断会被漏掉、原样输出，导致「该省的没省」。
      if (runStr.length < 60) {
        out.push(runStr);
      } else {
        // 保留约 2% 的头尾字符作样本，让人知道此处有省略
        const keep = Math.max(1, Math.floor(runStr.length * 0.02));
        const headPart = runStr.slice(0, keep);
        const tailPart = runStr.slice(runStr.length - keep);
        const omittedChars = runStr.length - headPart.length - tailPart.length;
        out.push(headPart);
        out.push('…[省略 ' + omittedChars + ' 字符]…');
        out.push(tailPart);
      }
      i = j;
    }
    return out.join('');
  };

  // 对某元素执行去重：以同选择器的首个元素为基准。
  A.dedupElementById = function (selId) {
    const idx = state.selectedElements.findIndex((el) => el.selId === selId);
    if (idx < 0) return;
    const el = state.selectedElements[idx];
    const base = state.selectedElements.find((x, i) => i < idx && x
      && x.selector && x.selector === el.selector);
    if (!base) { A.showToast('没有可对比的同选择器元素'); return; }
    const src = String(el.dom_html_full || el.dom_html || '');
    if (!src) { A.showToast('该元素没有 DOM 内容'); return; }
    const baseSrc = String(base.dom_html_full || base.dom_html || '');
    const compacted = A.compactDomAgainst(baseSrc, src);
    if (!el.dom_html_full) el.dom_html_full = src;
    el.dom_html = compacted;
    el.dom_html_length = compacted.length;
    A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
    A.showToast('已与首个同选择器元素对比去重');
  };

  // 还原某元素为完整 DOM
  A.restoreElementById = function (selId) {
    const idx = state.selectedElements.findIndex((el) => el.selId === selId);
    if (idx < 0) return;
    const el = state.selectedElements[idx];
    if (!el.dom_html_full) return;
    el.dom_html = el.dom_html_full;
    el.dom_html_length = el.dom_html.length;
    delete el.dom_html_full;
    A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
    A.showToast('已还原为完整 DOM');
  };

  // 按 selId 移除单个元素，回传最新列表
  A.removeElementById = function (selId) {
    const idx = state.selectedElements.findIndex((el) => el.selId === selId);
    if (idx >= 0) state.selectedElements.splice(idx, 1);
    A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
  };

  A.removeElementAt = function (index) {
    if (index >= 0 && index < state.selectedElements.length) {
      state.selectedElements.splice(index, 1);
    }
    A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
  };

  A.clearElements = function () {
    state.selectedElements.length = 0;
    A.postToDrawer({ type: 'elements-updated', elements: state.selectedElements });
  };

  /**
   * 按主世界脚本打的一次性标记，跨 world 找回元素。
   * 主世界脚本无法直接传元素引用过来，只能给元素打标记再通知；这里按标记
   * 在顶层文档与各同源 iframe 文档中查找。跨域 iframe 读不到 contentDocument，
   * 其内部元素无法找回，返回 null 由调用方提示。
   * @param {string} mark 标记值
   * @returns {Element|null} 命中的元素
   */
  A.findElementByMark = function (mark) {
    if (!mark) return null;
    const sel = '[data-ai-debug-pick="' + mark + '"]';
    const top = document.querySelector(sel);
    if (top) return top;
    const frames = A.collectAllIframes();
    for (let i = 0; i < frames.length; i++) {
      try {
        const d = frames[i].contentDocument;
        if (!d) continue;
        const hit = d.querySelector(sel);
        if (hit) return hit;
      } catch (e) { /* 跨域 iframe，忽略 */ }
    }
    return null;
  };

  /**
   * 传入一个 DOM 元素即完成选中：生成选择器、构建元素数据、入列并通知抽屉。
   * 这是所有「选中」路径的统一入口——鼠标中键、iframe 补丁回传、外部脚本调用
   * 都收敛到这里，避免同一套三步流程在多处重复实现（也便于日后统一加约束）。
   * 供无法用鼠标点选的元素使用：被遮挡、pointer-events:none、或由脚本动态生成
   * 而难以用指针命中的元素，用户可自行取得 DOM 对象后调用此函数。
   * @param {Element} el 目标 DOM 元素
   * @returns {boolean} 是否受理（元素非法 / 在抽屉内 / 超上限时返回 false）
   */
  A.selectElement = function (el) {
    if (!el || el.nodeType !== 1) {
      A.showToast('selectElement：请传入一个 DOM 元素');
      return false;
    }
    // 此处不拦「抽屉自身」：selectElement 是显式调用入口（用户主动传入元素，
    // 或主世界脚本按标记找回），用户意图明确，允许选中包括抽屉 iframe 在内的任何元素。
    // 鼠标点选路径的「不选抽屉」约束由 onAuxClick 单独负责，不受此影响。
    if (state.selectedElements.length >= A.MAX_ELEMENTS) {
      A.showToast('最多选择 ' + A.MAX_ELEMENTS + ' 个元素，已自动退出选择模式');
      A.toggleSelectMode(false);
      return false;
    }
    const selectorInfo = A.generateSelector(el);
    // 未开启截图：直接入列；开启截图：截取后再入列，截取失败也不阻断选中
    if (!state.screenshotEnabled) {
      A.pushSelected(A.buildElementData(el, selectorInfo));
      return true;
    }
    A.requestScreenshot()
      .then((shot) => A.pushSelected(A.buildElementData(el, selectorInfo), shot))
      .catch(() => A.pushSelected(A.buildElementData(el, selectorInfo)));
    return true;
  };
})();
