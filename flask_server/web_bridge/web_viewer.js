/* ============================================================
 * 网页版机器人 —— 图片看大图浮层（手势缩放平移）
 * 职责：点击消息里的图片时，在页面内浮层放大查看，支持滚轮/双指缩放、
 *       拖动平移、轻点关闭。
 *
 * 为什么不新开标签页：新文档必然重新请求图片；本模块把被点图片地址
 * 交给浮层 img，同址 + 后端强缓存 → 命中浏览器缓存，零请求。
 *
 * 从 web_page.js 抽出，使主脚本保持在行库行数上限内，
 * 也让「图片查看器」这一独立交互关注点集中一处。
 *
 * 用法：window.WebViewer.show(src)；由 web_page.js 在图片点击时调用。
 * ============================================================ */
(function () {
  'use strict';

  var viewer = null;
  var vimg = null;
  var vstate = { scale: 1, tx: 0, ty: 0 };   // 缩放倍数与平移量
  var MIN_SCALE = 1, MAX_SCALE = 8;          // 缩放范围：不小于适配尺寸，最大 8 倍
  var pointers = {};                          // 活动指针 id → 坐标
  var pinchDist = 0;                          // 双指初始间距（捏合基准）
  var moved = 0;                              // 本次按下累计移动，用于区分点击与拖动

  /** 应用当前缩放平移（只改 transform，不动布局，手势跟手）。 */
  function applyTransform() {
    if (vimg) vimg.style.transform =
      'translate(' + vstate.tx + 'px,' + vstate.ty + 'px) scale(' + vstate.scale + ')';
  }

  /** 重置缩放平移：每次打开大图都回到初始适配状态。 */
  function resetView() {
    vstate.scale = 1; vstate.tx = 0; vstate.ty = 0;
    applyTransform();
  }

  /** 双指间距。 */
  function pinchDistance() {
    var ids = Object.keys(pointers);
    var a = pointers[ids[0]], b = pointers[ids[1]];
    return Math.sqrt(Math.pow(a.x - b.x, 2) + Math.pow(a.y - b.y, 2));
  }

  /** 以某点为中心缩放：保持该点下图像位置不跑（跟手缩放）。 */
  function zoomAt(cx, cy, factor) {
    var ns = Math.max(MIN_SCALE, Math.min(MAX_SCALE, vstate.scale * factor));
    var real = ns / vstate.scale;
    var rect = viewer.getBoundingClientRect();
    var ox = cx - (rect.left + rect.width / 2);
    var oy = cy - (rect.top + rect.height / 2);
    vstate.tx = ox - (ox - vstate.tx) * real;
    vstate.ty = oy - (oy - vstate.ty) * real;
    vstate.scale = ns;
    applyTransform();
  }

  /** 构造浮层并绑手势（只建一次，复用后续）。 */
  function buildViewer() {
    viewer = document.createElement('div');
    viewer.className = 'img-viewer';
    vimg = document.createElement('img');
    vimg.className = 'img-viewer-img';
    viewer.appendChild(vimg);
    var tip = document.createElement('div');
    tip.className = 'img-viewer-tip';
    tip.textContent = '滚轮或双指缩放 · 拖动平移 · 轻点关闭';
    viewer.appendChild(tip);

    // 按下：记录指针；单指拖动、双指捏合
    viewer.addEventListener('pointerdown', function (e) {
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      try { viewer.setPointerCapture(e.pointerId); } catch (err) { /* 忽略 */ }
      if (Object.keys(pointers).length === 1) { moved = 0; viewer.classList.add('grabbing'); }
      else if (Object.keys(pointers).length === 2) {
        pinchDist = pinchDistance();
        // 双指一出现即视为「已交互」：抬手时不得误判为轻点而关闭浮层。
        moved = 999;
      }
    });

    // 移动：单指平移，双指缩放
    viewer.addEventListener('pointermove', function (e) {
      if (!pointers[e.pointerId]) return;
      var ids = Object.keys(pointers);
      var prev = pointers[e.pointerId];
      var dx = e.clientX - prev.x, dy = e.clientY - prev.y;
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      if (ids.length === 1) {
        moved += Math.abs(dx) + Math.abs(dy);   // 累计位移，供点击判定
        vstate.tx += dx; vstate.ty += dy;
        applyTransform();
      } else if (ids.length === 2) {
        var d = pinchDistance();
        var cx = (pointers[ids[0]].x + pointers[ids[1]].x) / 2;
        var cy = (pointers[ids[0]].y + pointers[ids[1]].y) / 2;
        if (pinchDist > 0) zoomAt(cx, cy, d / pinchDist);
        pinchDist = d;
      }
    });

    // 抬起：清理；从未移动视为轻点 → 关闭
    function onUp(e) {
      if (!pointers[e.pointerId]) return;
      delete pointers[e.pointerId];
      if (Object.keys(pointers).length === 0) {
        viewer.classList.remove('grabbing');
        if (moved < 6) viewer.classList.remove('on');
      } else if (Object.keys(pointers).length === 1) {
        pinchDist = 0;   // 回到单指，重置捏合基准
      }
    }
    viewer.addEventListener('pointerup', onUp);
    viewer.addEventListener('pointercancel', onUp);

    // 滚轮缩放（桌面端）
    viewer.addEventListener('wheel', function (e) {
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15);
    }, { passive: false });

    document.body.appendChild(viewer);
  }

  /** 打开大图浮层，显示指定图片地址。 */
  function show(src) {
    if (!viewer) buildViewer();
    vimg.src = src;
    resetView();
    viewer.classList.add('on');
  }

  window.WebViewer = { show: show };
})();
