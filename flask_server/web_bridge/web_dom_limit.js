/* ============================================================
 * 网页版机器人 —— DOM 数量上限与向前懒加载
 * 职责：限制页面保留的消息节点数，并在滑到底部时按锚点向前翻页。
 *
 * 解决什么问题：
 *   页面原先只插入节点、从不移除，500 条消息连同语音播放器与图片常驻内存。
 *   手机浏览器在后台按内存压力回收标签页，回到前台时整页重载、
 *   重建全部 DOM，表现为「切回来卡死」。
 *   本模块把 DOM 节点数限制在 MAX_DOM 内；更早的历史改为滑到底部时按需拉取。
 *
 * 依赖：由 web_page.js 在初始化时注入容器、渲染函数与日志函数，
 *   避免本模块反向依赖主模块的内部状态（渲染标记表、请求封装）。
 * ============================================================ */
(function () {
  'use strict';

  // 页面最多保留的消息节点数。50 条足够一屏以上阅读，且远低于触发内存回收的量级。
  var MAX_DOM = 50;
  // 翻历史时的宽松硬上限倍数：超过 MAX_DOM 的这么多倍才裁剪，
  // 避免刚加载的旧消息立刻被删（那会让用户往回滑时出现断层）。
  var HARD_CAP_FACTOR = 4;
  // 触发懒加载的底部距离（像素）：滑到离底部这么近就加载下一批
  var LOAD_TRIGGER_PX = 80;
  // 单批加载条数
  var PAGE_SIZE = 50;

  // 运行时状态
  var listEl = null;        // 消息列表容器
  var render = null;        // 渲染单条消息的回调 (m, allowAuto, atBottom) => bool
  var evict = null;         // 节点被裁掉时的回调（反注册已渲染标记）
  var log = null;           // 日志回调 (tag, msg)
  var domCount = 0;         // 当前 DOM 中的消息节点数
  var minSeqInDom = Infinity;  // DOM 中最早一条的 seq（向前翻页锚点）
  var maxSeqInDom = 0;         // DOM 中最晚一条的 seq
  var loading = false;      // 防止重复触发懒加载
  var noMore = false;       // 已翻到最早，无需再翻

  /**
   * 初始化：注入依赖并据现有 DOM 重算状态，同时挂上滚动监听。
   * @param {Object} opts { listEl, render, evict, log }
   */
  function init(opts) {
    opts = opts || {};
    listEl = opts.listEl || null;
    render = opts.render || null;
    evict = opts.evict || null;
    log = opts.log || function () {};
    recompute();
    if (listEl) listEl.addEventListener('scroll', onScroll);
  }

  /** 渲染一条后登记其 seq，维护 DOM 的 seq 范围。 */
  function note(seq) {
    var s = parseInt(seq, 10) || 0;
    if (!s) return;
    if (s < minSeqInDom) minSeqInDom = s;
    if (s > maxSeqInDom) maxSeqInDom = s;
    domCount++;
  }

  /** 从 DOM 重算 seq 范围与节点数（裁剪后调用）。 */
  function recompute() {
    minSeqInDom = Infinity;
    maxSeqInDom = 0;
    domCount = 0;
    if (!listEl) return;
    var n = listEl.children;
    for (var i = 0; i < n.length; i++) {
      var s = parseInt(n[i].getAttribute('data-seq'), 10) || 0;
      if (!s) continue;
      domCount++;
      if (s < minSeqInDom) minSeqInDom = s;
      if (s > maxSeqInDom) maxSeqInDom = s;
    }
  }

  /**
   * 裁剪 DOM 到上限。
   * @param {string} keep newest=保留顶部最新、从底部删；oldest=保留底部、从顶部删
   */
  function trim(keep) {
    if (!listEl) return;
    var removedH = 0;
    while (domCount > MAX_DOM) {
      var node = (keep === 'oldest') ? listEl.firstChild : listEl.lastChild;
      if (!node) break;
      var h = node.offsetHeight || 0;
      var seq = parseInt(node.getAttribute('data-seq'), 10) || 0;
      // 通知主模块反注册：被裁掉的消息若再次拉取（如回翻历史）仍能重新渲染
      if (seq && evict) {
        try { evict(seq); } catch (e) { /* 回调失败不影响裁剪 */ }
      }
      listEl.removeChild(node);
      domCount--;
      if (keep === 'oldest') removedH += h;
    }
    // 从顶部删除时补偿滚动位置，避免正在阅读的内容跳动
    if (keep === 'oldest' && removedH) listEl.scrollTop = Math.max(0, listEl.scrollTop - removedH);
    recompute();
  }

  /** 新消息到达后调用：用户停在顶部时裁掉最旧节点，防止 DOM 无限增长。 */
  function afterAppend() {
    if (!listEl) return;
    // 用户已向下翻看历史时不裁，避免正在读的内容被抽走
    if (listEl.scrollTop < 40) trim('newest');
  }

  /** 向前翻页：加载比 DOM 中最早一条更早的消息，追加到列表末尾。 */
  function loadOlder() {
    if (loading || noMore || !isFinite(minSeqInDom) || !render) return;
    loading = true;
    fetch('/api/web/messages?before=' + minSeqInDom + '&limit=' + PAGE_SIZE,
      { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        var list = d.messages || [];
        if (!list.length) { noMore = true; return; }
        // 列表倒序（最新在顶部），故追加更早的一批时须按「新→旧」顺序逐个插到末尾，
        // 否则批内较旧的消息会排到较新的下方，视觉顺序颠倒。
        list.slice().reverse().forEach(function (m) { render(m, false, true); });
        noMore = !d.has_more;
        // 翻历史时保留已加载内容：只在超过宽松硬上限时才裁剪
        if (domCount > MAX_DOM * HARD_CAP_FACTOR) trim('oldest');
        log('older', 'loaded=' + list.length + ' has_more=' + (d.has_more ? 1 : 0));
      })
      .catch(function (e) { log('older', 'fail ' + (e && e.message ? e.message : e)); })
      .then(function () { loading = false; });
  }

  /** 滚动监听：接近底部时加载更早的消息。 */
  function onScroll() {
    if (!listEl) return;
    if (listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < LOAD_TRIGGER_PX) loadOlder();
  }

  window.WebDom = {
    MAX_DOM: MAX_DOM,
    init: init,
    note: note,
    trim: trim,
    recompute: recompute,
    afterAppend: afterAppend,
    loadOlder: loadOlder,
    // 只读访问器
    count: function () { return domCount; },
    minSeq: function () { return minSeqInDom; }
  };
})();
