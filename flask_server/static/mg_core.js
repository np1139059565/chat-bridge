// 记忆图谱·核心：共享状态、坐标变换、配色、力导向与各视图布局。
// 各文件通过全局命名空间 MG 共享状态，避免散落全局变量。
(function () {
  'use strict';
  var MG = window.MG = window.MG || {};

  // ---------- 共享状态 ----------
  MG.cv = null;              // canvas 元素
  MG.ctx = null;             // 2D 上下文
  MG.tip = null;             // 悬浮提示元素
  MG.nodes = [];             // 节点数组
  MG.edges = [];             // 边数组（s/t 指向节点对象）
  MG.W = 0; MG.H = 0;        // 画布逻辑尺寸
  MG.MODE = 'force';         // 视图：force / radial / timeline
  MG.selected = null;        // 单击选中的节点
  MG.selectedSet = {};       // 选中节点 + 一跳邻居 id 集合
  MG.drag = null;            // 正在拖动的节点
  MG.panning = false;        // 是否在平移
  MG.panLast = null;         // 平移上一帧鼠标位置
  MG.view = { x: 0, y: 0, k: 1 };   // 缩放平移：偏移与倍率
  MG.MAX_NODES = 500;        // 节点显示上限，防海量数据卡死
  MG.edgeOn = { parent_child: true, branch: true, associative: true };  // 边类型开关
  MG.keywordFilter = '';     // 关键词过滤
  MG.settled = false;        // 力导向是否已收敛（收敛后停帧省性能）
  MG.settleCount = 0;        // 连续稳定帧数

  // 初始化 DOM 引用（脚本在 body 末尾加载，元素已就绪）
  MG.initDom = function () {
    MG.cv = document.getElementById('cv');
    MG.ctx = MG.cv.getContext('2d');
    MG.tip = document.getElementById('tip');
  };

  // 适配设备像素比，保证高清屏不糊
  MG.resize = function () {
    var cv = MG.cv, ctx = MG.ctx;
    var dpr = window.devicePixelRatio || 1;
    MG.W = cv.clientWidth; MG.H = cv.clientHeight;
    cv.width = MG.W * dpr; cv.height = MG.H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    MG.settled = false; MG.settleCount = 0;   // 尺寸变化后重新收敛
  };

  // 屏幕坐标 → 图坐标（考虑缩放平移）
  MG.toGraph = function (mx, my) {
    return { x: (mx - MG.view.x) / MG.view.k, y: (my - MG.view.y) / MG.view.k };
  };

  // 分级配色：用户发言单独红色，其余按 tier
  MG.colorOf = function (n) {
    if (n.source === 'user') return '#e05a5a';
    if (n.tier === 'perm') return '#e0b23a';
    if (n.tier === 'mid') return '#3a8dde';
    return '#888';
  };

  // 节点半径：按强度（越大越强）
  MG.radiusOf = function (n) { return 4 + (n.strength || 0.5) * 10; };

  // ---------- 力导向 ----------
  // 斥力（节点互推）+ 弹簧（边拉近）+ 向心力，迭代收敛。
  MG.tick = function () {
    var nodes = MG.nodes, edges = MG.edges;
    var i, j, a, b, dx, dy, d2, d, f;
    var maxSpeed = 0;
    for (i = 0; i < nodes.length; i++) {
      a = nodes[i];
      for (j = i + 1; j < nodes.length; j++) {
        b = nodes[j];
        dx = a.x - b.x; dy = a.y - b.y;
        d2 = dx * dx + dy * dy + 0.01;
        f = 800 / d2;
        d = Math.sqrt(d2);
        a.vx += dx / d * f; a.vy += dy / d * f;
        b.vx -= dx / d * f; b.vy -= dy / d * f;
      }
      a.vx += (MG.W / 2 - a.x) * 0.002;
      a.vy += (MG.H / 2 - a.y) * 0.002;
    }
    for (var e = 0; e < edges.length; e++) {
      var ed = edges[e];
      if (!MG.edgeOn[ed.kind]) continue;   // 关掉的边类型不参与力计算
      var s = ed.s, t = ed.t;
      if (!s || !t) continue;
      dx = t.x - s.x; dy = t.y - s.y;
      d = Math.sqrt(dx * dx + dy * dy) + 0.01;
      f = (d - 90) * 0.01 * (ed.weight || 1);
      s.vx += dx / d * f; s.vy += dy / d * f;
      t.vx -= dx / d * f; t.vy -= dy / d * f;
    }
    for (i = 0; i < nodes.length; i++) {
      a = nodes[i];
      if (a === MG.drag) continue;
      a.vx *= 0.9; a.vy *= 0.9;      // 阻尼：加快速度衰减，减少弹跳
      a.x += a.vx; a.y += a.vy;
      var sp = Math.abs(a.vx) + Math.abs(a.vy);
      if (sp > maxSpeed) maxSpeed = sp;
    }
    // 收敛判定：整体速度极小即视为稳定，停帧省性能
    if (maxSpeed < 0.05) {
      MG.settleCount += 1;
      if (MG.settleCount > 30) MG.settled = true;
    } else { MG.settleCount = 0; }
  };

  // 构建无向邻接表（径向树 BFS 用，树边与突触边一视同仁）
  MG.buildAdj = function () {
    var adj = {};
    MG.nodes.forEach(function (n) { adj[n.id] = []; });
    MG.edges.forEach(function (ed) {
      if (!ed.s || !ed.t) return;
      adj[ed.s.id].push(ed.t.id);
      adj[ed.t.id].push(ed.s.id);
    });
    return adj;
  };

  // 径向树布局：以 rootId 为根 BFS 分层，深度定半径、同级均分角度
  MG.layoutRadial = function (rootId) {
    var nodes = MG.nodes;
    var byId = {};
    nodes.forEach(function (n) { byId[n.id] = n; });
    if (!byId[rootId]) return;
    var adj = MG.buildAdj();
    var depth = {}; depth[rootId] = 0;
    var order = [rootId];
    var visited = {}; visited[rootId] = true;
    for (var qi = 0; qi < order.length; qi++) {
      var cur = order[qi];
      (adj[cur] || []).forEach(function (nb) {
        if (visited[nb]) return;
        visited[nb] = true;
        depth[nb] = depth[cur] + 1;
        order.push(nb);
      });
    }
    var levels = {};
    Object.keys(depth).forEach(function (id) {
      var dpt = depth[id];
      (levels[dpt] = levels[dpt] || []).push(parseInt(id, 10));
    });
    var cx = MG.W / 2, cy = MG.H / 2;
    var maxDepth = 0;
    Object.keys(levels).forEach(function (k) { maxDepth = Math.max(maxDepth, parseInt(k, 10)); });
    var ringGap = maxDepth > 0 ? (Math.min(MG.W, MG.H) / 2 - 40) / maxDepth : 0;
    Object.keys(levels).forEach(function (k) {
      var dpt = parseInt(k, 10);
      var ids = levels[k];
      var r = dpt * ringGap;
      for (var i = 0; i < ids.length; i++) {
        var ang = -Math.PI / 2 + (ids.length === 1 ? 0 : (i / ids.length) * Math.PI * 2);
        var nd = byId[ids[i]];
        if (!nd) continue;
        nd.x = cx + r * Math.cos(ang);
        nd.y = cy + r * Math.sin(ang);
        nd.vx = nd.vy = 0;
      }
    });
  };

  // 时间轴布局：按创建时间沿水平轴排布，纵轴按来源分三道
  MG.layoutTimeline = function () {
    var sorted = MG.nodes.slice().sort(function (a, b) {
      return (a.created_at || 0) - (b.created_at || 0);
    });
    if (!sorted.length) return;
    var t0 = sorted[0].created_at || 0;
    var t1 = sorted[sorted.length - 1].created_at || 1;
    var span = Math.max(1, t1 - t0);
    var laneY = { user: MG.H * 0.2, assistant: MG.H * 0.5, tool: MG.H * 0.8 };
    sorted.forEach(function (n) {
      n.x = 60 + (MG.W - 120) * (((n.created_at || 0) - t0) / span);
      n.y = laneY[n.source] || MG.H * 0.5;
      n.vx = n.vy = 0;
    });
  };
})();
