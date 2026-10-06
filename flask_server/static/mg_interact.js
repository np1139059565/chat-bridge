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

  // 边的可读说明：类型 + 含义（悬停连线时展示，解释「为什么连这条线」）
  MG.edgeLabel = function (ed) {
    var w = (ed.weight || 0).toFixed(2);
    if (ed.kind === 'associative') return '突触边：关键词相关（权重 ' + w + '）';
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
        MG.drag.x = g.x; MG.drag.y = g.y; MG.drag.vx = MG.drag.vy = 0;
        MG.settled = false; return;
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
      if (hit) { if (MG.MODE === 'force') { MG.drag = hit; MG.settled = false; } }
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

  // ---------- 顶栏控件 ----------
  MG.bindBar = function () {
    document.getElementById('reload').addEventListener('click', MG.load);
    document.getElementById('modeForce').addEventListener('click', function () { MG.MODE = 'force'; MG.applyMode(); });
    document.getElementById('modeRadial').addEventListener('click', function () { MG.MODE = 'radial'; MG.applyMode(); });
    document.getElementById('modeTimeline').addEventListener('click', function () { MG.MODE = 'timeline'; MG.applyMode(); });
    document.getElementById('search').addEventListener('input', function (ev) {
      MG.keywordFilter = ev.target.value.trim();
      MG.load();   // 重新拉取并按关键词过滤
    });
    ['parent_child', 'branch', 'associative'].forEach(function (k) {
      var el = document.getElementById('edge-' + k);
      if (el) el.addEventListener('change', function (ev) {
        MG.edgeOn[k] = ev.target.checked;
        MG.settled = false; MG.settleCount = 0;
      });
    });
  };

  // 绑定全部交互
  MG.bindAll = function () {
    MG.bindWheel(); MG.bindMouseMove(); MG.bindMouseDown();
    MG.bindClick(); MG.bindDblClick(); MG.bindBar();
  };
})();
