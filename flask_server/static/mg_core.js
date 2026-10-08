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
  MG.maxId = 0;              // 已加载的最大节点 id，用于增量轮询
  MG._incTimer = null;       // 增量轮询定时器
  MG.alpha = 1;              // 力导向衰减系数：每帧衰减，到 0 即静止
  MG.ALPHA_DECAY = 0.985;    // 每帧衰减比；越小收敛越快
  MG.ALPHA_MIN = 0.005;      // 低于此值视为收敛，停帧

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
    // 尺寸变化后重新布局：重置衰减系数，让图重新收敛
    MG.settled = false; MG.alpha = 1;
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
  // 力导向：斥力 + 弹簧 + 向心力，力的大小乘以衰减系数 alpha。
  // 关键：alpha 每帧衰减，力随之趋零，图自然静止——
  // 缺了这一步，力会持续叠加、节点永不停息（曾出现的「拼命跳」）。
  MG.tick = function () {
    var nodes = MG.nodes, edges = MG.edges;
    var i, j, a, b, dx, dy, d2, d, f;
    var alpha = MG.alpha;
    for (i = 0; i < nodes.length; i++) {
      a = nodes[i];
      for (j = i + 1; j < nodes.length; j++) {
        b = nodes[j];
        dx = a.x - b.x; dy = a.y - b.y;
        d2 = dx * dx + dy * dy + 0.01;
        f = 800 / d2 * alpha;          // 斥力随 alpha 衰减
        d = Math.sqrt(d2);
        a.vx += dx / d * f; a.vy += dy / d * f;
        b.vx -= dx / d * f; b.vy -= dy / d * f;
      }
      a.vx += (MG.W / 2 - a.x) * 0.002 * alpha;
      a.vy += (MG.H / 2 - a.y) * 0.002 * alpha;
    }
    for (var e = 0; e < edges.length; e++) {
      var ed = edges[e];
      if (!MG.edgeOn[ed.kind]) continue;   // 关掉的边类型不参与力计算
      var s = ed.s, t = ed.t;
      if (!s || !t) continue;
      dx = t.x - s.x; dy = t.y - s.y;
      d = Math.sqrt(dx * dx + dy * dy) + 0.01;
      f = (d - 90) * 0.01 * (ed.weight || 1) * alpha;
      s.vx += dx / d * f; s.vy += dy / d * f;
      t.vx -= dx / d * f; t.vy -= dy / d * f;
    }
    for (i = 0; i < nodes.length; i++) {
      a = nodes[i];
      if (a === MG.drag) continue;
      a.vx *= 0.6; a.vy *= 0.6;      // 阻尼：抑制速度，配合 alpha 衰减更快静止
      a.x += a.vx; a.y += a.vy;
    }
    // 位置更新后做硬分离：纯斥力在节点密集时不足以保证最小间距，
    // 这里显式把重叠节点推开，保证任意两节点间距 >= 半径之和 + MIN_GAP。
    MG.separateOverlaps();
    // alpha 衰减到阈值以下：视为收敛，停帧省性能
    MG.alpha *= MG.ALPHA_DECAY;
    if (MG.alpha < MG.ALPHA_MIN) {
      MG.alpha = 0;
      MG.settled = true;
    }
  };

  // 节点间最小间隙（像素）：两节点边缘至少隔开这么多，避免视觉重叠。
  MG.MIN_GAP = 5;

  // 硬分离：把间距小于「半径和 + MIN_GAP」的节点对推开。
  // 迭代若干轮直至无重叠或达到轮数上限；被拖动的节点固定不动，只推对方。
  // 这是确定性约束（不依赖 alpha），保证收敛后仍维持最小间距。
  MG.separateOverlaps = function () {
    var nodes = MG.nodes;
    var passes = 3;                   // 迭代轮数：太多会拖慢每帧
    for (var pass = 0; pass < passes; pass++) {
      var moved = false;
      for (var i = 0; i < nodes.length; i++) {
        var a = nodes[i];
        for (var j = i + 1; j < nodes.length; j++) {
          var b = nodes[j];
          var dx = b.x - a.x, dy = b.y - a.y;
          var d = Math.sqrt(dx * dx + dy * dy);
          var need = MG.radiusOf(a) + MG.radiusOf(b) + MG.MIN_GAP;
          if (d >= need) continue;    // 间距足够，跳过
          // 完全重合时给一个随机方向，避免除零、让它们分开
          if (d < 0.01) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; d = Math.sqrt(dx * dx + dy * dy) + 0.001; }
          var push = (need - d) / 2;  // 各推一半
          var ux = dx / d, uy = dy / d;
          if (a !== MG.drag) { a.x -= ux * push; a.y -= uy * push; }
          if (b !== MG.drag) { b.x += ux * push; b.y += uy * push; }
          moved = true;
        }
      }
      if (!moved) break;              // 已无重叠，提前结束
    }
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

  // 径向树布局：以 rootId 为根建树，按「子树叶子数」分配角度扇区。
  // 子树大的占更宽扇区、小的占窄扇区，保持树形结构、避免同层节点挤成一圈。
  MG.layoutRadial = function (rootId) {
    var nodes = MG.nodes;
    var byId = {};
    nodes.forEach(function (n) { byId[n.id] = n; });
    if (!byId[rootId]) return;
    var adj = MG.buildAdj();
    // 1) BFS 建树：确立父子关系（首次访问即定为父）
    var children = {};
    var depth = {}; depth[rootId] = 0;
    var order = [rootId];
    var visited = {}; visited[rootId] = true;
    nodes.forEach(function (n) { children[n.id] = []; });
    for (var qi = 0; qi < order.length; qi++) {
      var cur = order[qi];
      (adj[cur] || []).forEach(function (nb) {
        if (visited[nb]) return;
        visited[nb] = true;
        depth[nb] = depth[cur] + 1;
        children[cur].push(nb);
        order.push(nb);
      });
    }
    // 2) 逆 BFS 序算子树叶子数（子节点先算好，父节点再累加）
    var leaf = {};
    for (var ri = order.length - 1; ri >= 0; ri--) {
      var rid = order[ri];
      var ch = children[rid];
      if (!ch.length) { leaf[rid] = 1; continue; }
      var sum = 0;
      for (var ci = 0; ci < ch.length; ci++) sum += leaf[ch[ci]];
      leaf[rid] = sum;
    }
    // 3) 自上而下按叶子数比例切分父扇区，节点落在自己扇区中点
    var cx = MG.W / 2, cy = MG.H / 2;
    var maxDepth = 0;
    Object.keys(depth).forEach(function (k) { maxDepth = Math.max(maxDepth, depth[k]); });
    var ringGap = maxDepth > 0 ? (Math.min(MG.W, MG.H) / 2 - 40) / maxDepth : 0;
    var span = {};
    span[rootId] = { start: -Math.PI / 2, size: Math.PI * 2 };
    for (var oi = 0; oi < order.length; oi++) {
      var nid = order[oi];
      var sp = span[nid];
      var nd = byId[nid];
      if (nd) {
        var mid = sp.start + sp.size / 2;
        var r = depth[nid] * ringGap;
        nd.x = cx + r * Math.cos(mid);
        nd.y = cy + r * Math.sin(mid);
        nd.vx = nd.vy = 0;
      }
      var kids = children[nid];
      var total = leaf[nid] || 1;
      var acc = sp.start;
      for (var ki = 0; ki < kids.length; ki++) {
        var kk = kids[ki];
        var ks = sp.size * (leaf[kk] / total);
        span[kk] = { start: acc, size: ks };
        acc += ks;
      }
    }
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
