// 记忆图谱·交互：命中检测、鼠标事件（悬停/拖动/平移/缩放/单击高亮/双击详情）、顶栏控件。
(function () {
  'use strict';
  var MG = window.MG;

  // ---------- 命中检测 ----------
  // 点到线段的最短距离平方
  MG.ptSegDist2 = function (px, py, x1, y1, x2, y2) {
    var dx = x2 - x1, dy = y2 - y1;
    var len2 = dx * dx + dy * dy;
    var t = len2 ? ((px - x1) * dx + (py - y1) * dy) / len2 : 0;
    t = Math.max(0, Math.min(1, t));
    var cx = x1 + t * dx, cy = y1 + t * dy;
    return (px - cx) * (px - cx) + (py - cy) * (py - cy);
  };

  // 命中节点：返回 (gx,gy) 处半径内的节点；无则 null
  MG.hitNodeAt = function (gx, gy) {
    var nodes = MG.nodes;
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var hr = MG.radiusOf(n) + 6;
      if ((n.x - gx) * (n.x - gx) + (n.y - gy) * (n.y - gy) < hr * hr) return n;
    }
    return null;
  };

  // 命中边：返回离 (gx,gy) 最近且在阈值内的边；无则 null
  MG.hitEdgeAt = function (gx, gy) {
    var best = null, bestD = 36;   // 6 像素阈值（平方）
    var edges = MG.edges;
    for (var i = 0; i < edges.length; i++) {
      var ed = edges[i];
      if (!MG.edgeOn[ed.kind] || !ed.s || !ed.t) continue;
      var d2 = MG.ptSegDist2(gx, gy, ed.s.x, ed.s.y, ed.t.x, ed.t.y);
      if (d2 < bestD) { bestD = d2; best = ed; }
    }
    return best;
  };

  // 边的可读说明：类型 + 含义 + 触发关键词（悬停连线时展示，解释「为什么连这条线」）
  MG.edgeLabel = function (ed) {
    var w = (ed.weight || 0).toFixed(2);
    if (ed.kind === 'associative') {
      var kw = (ed.keywords || []).join('、');
      return '突触边：关键词相关（权重 ' + w + '）' + (kw ? ('\n关键词：' + kw) : '\n（该边建立于旧版本，未记录关键词）');
    }
    if (ed.kind === 'branch') return '分支边：同一问题生成多个回答';
    if (ed.kind === 'parent_child') return '树边：消息回复关系';
    return '边类型：' + (ed.kind || '未知');
  };

  // 显示悬浮提示
  function showTip(ev, text) {
    MG.tip.style.display = 'block';
    MG.tip.style.left = (ev.clientX + 12) + 'px';
    MG.tip.style.top = (ev.clientY + 12) + 'px';
    MG.tip.textContent = text;
  }

  // ---------- 鼠标：滚轮缩放 ----------
  MG.bindWheel = function () {
    MG.cv.addEventListener('wheel', function (ev) {
      ev.preventDefault();
      var rect = MG.cv.getBoundingClientRect();
      var mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
      var factor = ev.deltaY < 0 ? 1.1 : 0.9;
      // 以鼠标位置为锚点缩放
      MG.view.x = mx - (mx - MG.view.x) * factor;
      MG.view.y = my - (my - MG.view.y) * factor;
      MG.view.k *= factor;
    }, { passive: false });
  };

  // ---------- 鼠标：移动（拖动节点 / 平移 / 悬停提示） ----------
  MG.bindMouseMove = function () {
    MG.cv.addEventListener('mousemove', function (ev) {
      var rect = MG.cv.getBoundingClientRect();
      var mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
      if (MG.panning) {
        MG.view.x += mx - MG.panLast.x; MG.view.y += my - MG.panLast.y;
        MG.panLast = { x: mx, y: my };
        return;
      }
      var g = MG.toGraph(mx, my);
      if (MG.drag && MG.MODE === 'force') {
        // 拖动期间：直接设定被拖节点位置，并把 alpha 维持在小值，
        // 让周围节点轻微让位；松手后 alpha 继续衰减、图自然静止。
        MG.drag.x = g.x; MG.drag.y = g.y; MG.drag.vx = MG.drag.vy = 0;
        MG.alpha = Math.max(MG.alpha, 0.3);
        MG.settled = false;
        return;
      }
      var hit = MG.hitNodeAt(g.x, g.y);
      if (hit) {
        showTip(ev, '#' + hit.id + ' [' + (hit.source || '') + '/' + (hit.tier || '') + '] ' + (hit.essence || ''));
        MG.cv.style.cursor = 'pointer';
        return;
      }
      var he = MG.hitEdgeAt(g.x, g.y);
      if (he) { showTip(ev, MG.edgeLabel(he)); MG.cv.style.cursor = 'crosshair'; }
      else { MG.tip.style.display = 'none'; MG.cv.style.cursor = 'default'; }
    });
  };

  // ---------- 鼠标：按下（拖节点 / 空白平移） ----------
  MG.bindMouseDown = function () {
    MG.cv.addEventListener('mousedown', function (ev) {
      var rect = MG.cv.getBoundingClientRect();
      var g = MG.toGraph(ev.clientX - rect.left, ev.clientY - rect.top);
      var hit = MG.hitNodeAt(g.x, g.y);
      if (hit) {
        if (MG.MODE === 'force') {
          MG.drag = hit;
          MG.settled = false;
          // 拖动时把 alpha 抬到一个小值：其他节点轻微让位，但不剧烈重排。
          // 松手后 alpha 继续按 decay 衰减到 0，图自然静止。
          MG.alpha = Math.max(MG.alpha, 0.3);
        }
      }
      else { MG.panning = true; MG.panLast = { x: ev.clientX - rect.left, y: ev.clientY - rect.top }; }
    });
    window.addEventListener('mouseup', function () { MG.drag = null; MG.panning = false; });
  };

  // ---------- 鼠标：单击高亮一跳邻居 ----------
  MG.bindClick = function () {
    MG.cv.addEventListener('click', function (ev) {
      var rect = MG.cv.getBoundingClientRect();
      var g = MG.toGraph(ev.clientX - rect.left, ev.clientY - rect.top);
      var hit = MG.hitNodeAt(g.x, g.y);
      if (!hit) { MG.selected = null; MG.selectedSet = {}; return; }
      if (MG.selected === hit) { MG.selected = null; MG.selectedSet = {}; return; }
      MG.selected = hit; MG.selectedSet = {}; MG.selectedSet[hit.id] = true;
      for (var e = 0; e < MG.edges.length; e++) {
        var ed = MG.edges[e];
        if (!ed.s || !ed.t) continue;
        if (ed.s.id === hit.id) MG.selectedSet[ed.t.id] = true;
        else if (ed.t.id === hit.id) MG.selectedSet[ed.s.id] = true;
      }
    });
  };

  // ---------- 鼠标：双击打开详情 ----------
  MG.bindDblClick = function () {
    MG.cv.addEventListener('dblclick', function (ev) {
      var rect = MG.cv.getBoundingClientRect();
      var g = MG.toGraph(ev.clientX - rect.left, ev.clientY - rect.top);
      var hit = MG.hitNodeAt(g.x, g.y);
      if (hit) MG.showDetail(hit);
    });
  };

  // 安全绑定：元素不存在时静默跳过，绝不让缺元素抛错拖垮整段初始化。
  // （曾因缓存旧页面缺少某按钮，getElementById 返回 null，
  //   addEventListener 抛错导致后续初始化全部不执行、页面空白。）
  function on(id, evt, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener(evt, fn);
  }

  // ---------- 右键菜单：用户发言节点的手动清理 ----------
  // 右键「用户发言」节点弹出：清理其下挂的 AI/工具节点、清理它之前的旧节点。
  // 两个动作都是破坏性的，执行前一律二次确认。
  MG.hideCtxMenu = function () {
    var m = document.getElementById('ctxMenu');
    if (m) m.style.display = 'none';
  };

  // 菜单项定义：仅对「用户发言」节点开放清理动作（AI/工具节点不提供）。
  MG.showCtxMenu = function (ev, node) {
    var menu = document.getElementById('ctxMenu');
    if (!menu) return;
    var items = [];
    items.push({ label: '查看详情', fn: function () { MG.showDetail(node); } });
    if (node.source === 'user') {
      items.push({ sep: true });
      items.push({
        label: '清理该节点下挂的 AI / 工具节点', danger: true,
        fn: function () { MG.cleanChildren(node); }
      });
      items.push({
        label: '清理该节点之前的全部旧节点', danger: true,
        fn: function () { MG.cleanOlder(node); }
      });
    }
    var html = '';
    items.forEach(function (it) {
      if (it.sep) { html += '<div class="sep"></div>'; return; }
      html += '<div class="mi' + (it.danger ? ' danger' : '') + '">' + it.label + '</div>';
    });
    menu.innerHTML = html;
    // 逐个绑定点击（重新生成后绑定，避免闭包串号）
    var idx = 0;
    Array.prototype.forEach.call(menu.children, function (el) {
      if (el.className.indexOf('sep') >= 0) return;
      var it = items.filter(function (x) { return !x.sep; })[idx++];
      el.onclick = function () { MG.hideCtxMenu(); it.fn(); };
    });
    menu.style.left = ev.clientX + 'px';
    menu.style.top = ev.clientY + 'px';
    menu.style.display = 'block';
  };

  // 清理某用户节点下挂的 AI/工具节点（二次确认）
  MG.cleanChildren = function (node) {
    if (!confirm('确定清理节点 #' + node.id + ' 下挂的全部 AI 与工具节点？\n此操作不可恢复。')) return;
    fetch('/memory/node/clean_children', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: node.id })
    }).then(function (r) { return r.json(); }).then(function (d) {
      alert('已清理 ' + ((d && d.deleted) || 0) + ' 个节点');
      MG.load();
    }).catch(function () { alert('清理失败'); });
  };

  // 清理某节点之前的全部旧节点（二次确认，破坏性最强）
  MG.cleanOlder = function (node) {
    if (!confirm('确定清理节点 #' + node.id + ' 之前的全部旧节点？\n此操作不可恢复，且数量可能很大。')) return;
    if (!confirm('再次确认：真的要删除所有这些旧节点吗？')) return;
    fetch('/memory/node/clean_older', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: node.id })
    }).then(function (r) { return r.json(); }).then(function (d) {
      alert('已清理 ' + ((d && d.deleted) || 0) + ' 个节点');
      MG.load();
    }).catch(function () { alert('清理失败'); });
  };

  // 绑定右键：命中用户节点则弹出清理菜单，否则隐藏
  MG.bindContextMenu = function () {
    MG.cv.addEventListener('contextmenu', function (ev) {
      var rect = MG.cv.getBoundingClientRect();
      var g = MG.toGraph(ev.clientX - rect.left, ev.clientY - rect.top);
      var hit = MG.hitNodeAt(g.x, g.y);
      if (!hit) { MG.hideCtxMenu(); return; }
      ev.preventDefault();
      MG.showCtxMenu(ev, hit);
    });
    // 点击别处 / 滚轮缩放时关闭菜单
    window.addEventListener('mousedown', function (ev) {
      var m = document.getElementById('ctxMenu');
      if (m && m.style.display === 'block' && !m.contains(ev.target)) MG.hideCtxMenu();
    });
    MG.cv.addEventListener('wheel', MG.hideCtxMenu, { passive: true });
  };

  // ---------- 顶栏控件 ----------
  MG.bindBar = function () {
    on('reload', 'click', MG.load);
    on('modeForce', 'click', function () { MG.MODE = 'force'; MG.applyMode(); });
    on('modeRadial', 'click', function () { MG.MODE = 'radial'; MG.applyMode(); });
    on('modeTimeline', 'click', function () { MG.MODE = 'timeline'; MG.applyMode(); });
    on('search', 'input', function (ev) {
      MG.keywordFilter = ev.target.value.trim();
      MG.load();   // 重新拉取并按关键词过滤
    });
    ['parent_child', 'branch', 'associative'].forEach(function (k) {
      on('edge-' + k, 'change', function (ev) {
        MG.edgeOn[k] = ev.target.checked;
        MG.settled = false; MG.alpha = 1;
      });
    });
  };

  // 绑定全部交互
  MG.bindAll = function () {
    MG.bindWheel(); MG.bindMouseMove(); MG.bindMouseDown();
    MG.bindClick(); MG.bindDblClick(); MG.bindBar(); MG.bindContextMenu();
  };
})();
