// 记忆图谱·数据与详情：拉取图数据、会话下拉、搜索过滤、节点详情弹框（含硬删）。
(function () {
  'use strict';
  var MG = window.MG;

  // 搜索过滤：精华或关键词命中即保留
  function matchFilter(n) {
    var kw = MG.keywordFilter.toLowerCase();
    if ((n.essence || '').toLowerCase().indexOf(kw) >= 0) return true;
    return (n.keywords || []).some(function (k) {
      return String(k).toLowerCase().indexOf(kw) >= 0;
    });
  }

  // 用图数据构建节点与边；节点超上限时截断，防海量数据卡死。
  MG.build = function (data) {
    MG.nodes = []; MG.edges = [];
    var map = {};
    var all = data.nodes || [];
    var truncated = all.length > MG.MAX_NODES;
    all = all.slice(0, MG.MAX_NODES);
    all.forEach(function (n) {
      if (MG.keywordFilter && !matchFilter(n)) return;
      var o = { id: n.id, source: n.source, tier: n.tier, strength: n.strength,
                keywords: n.keywords, essence: n.essence, created_at: n.created_at,
                x: Math.random() * MG.W, y: Math.random() * MG.H, vx: 0, vy: 0 };
      MG.nodes.push(o); map[n.id] = o;
    });
    (data.edges || []).forEach(function (e) {
      var s = map[e.src_node], t = map[e.dst_node];
      if (!s || !t) return;   // 节点被截断时，避免收进悬空边
      // keywords：导致关联的关键词，供悬停连线时说明「因哪些词相连」
      MG.edges.push({ s: s, t: t, kind: e.kind, weight: e.weight, keywords: e.keywords || [] });
    });
    var note = truncated ? ('（节点超 ' + MG.MAX_NODES + '，仅显示前 ' + MG.MAX_NODES + ' 个）') : '';
    document.getElementById('stat').textContent =
      MG.nodes.length + ' 节点 / ' + MG.edges.length + ' 边' + note;
    // 记录最大节点 id，供增量轮询从此之后拉取
    MG.maxId = data.max_id || 0;
    MG.selected = null; MG.selectedSet = {};
    MG.settled = false; MG.alpha = 1;   // 新数据：重置衰减，重新布局
    MG.applyMode();
  };

  // 增量更新：拉取 id 大于 MG.maxId 的新节点，追加进图。
  // 只加不重排——新节点给一个靠近中心的初始位置 + 很小的 alpha，
  // 让图轻微调整而非整图重排，实现「随 AI 生成逐个增加」的静态更新。
  MG.pollIncrement = function () {
    var conv = document.getElementById('conv') ? document.getElementById('conv').value.trim() : '';
    var url = '/memory/graph?since_id=' + encodeURIComponent(MG.maxId)
      + (conv ? ('&conv_id=' + encodeURIComponent(conv)) : '');
    fetch(url).then(function (r) { return r.json(); }).then(function (data) {
      var newNodes = (data && data.nodes) || [];
      if (!newNodes.length) return;
      var map = {};
      MG.nodes.forEach(function (n) { map[n.id] = n; });
      var added = 0;
      newNodes.forEach(function (n) {
        if (map[n.id]) return;   // 已存在，跳过
        if (MG.nodes.length >= MG.MAX_NODES) return;   // 超上限不再加
        var o = { id: n.id, source: n.source, tier: n.tier, strength: n.strength,
                  keywords: n.keywords, essence: n.essence, created_at: n.created_at,
                  // 从中心附近出现，随力导向轻微散开
                  x: MG.W / 2 + (Math.random() - 0.5) * 40,
                  y: MG.H / 2 + (Math.random() - 0.5) * 40, vx: 0, vy: 0 };
        MG.nodes.push(o); map[n.id] = o; added++;
      });
      ((data && data.edges) || []).forEach(function (e) {
        var s = map[e.src_node], t = map[e.dst_node];
        if (!s || !t) return;
        MG.edges.push({ s: s, t: t, kind: e.kind, weight: e.weight, keywords: e.keywords || [] });
      });
      MG.maxId = data.max_id || MG.maxId;
      if (added) {
        document.getElementById('stat').textContent =
          MG.nodes.length + ' 节点 / ' + MG.edges.length + ' 边（持续增加中）';
        // 很小的 alpha：新节点轻微落位，不打乱已稳定的布局
        MG.alpha = Math.max(MG.alpha, 0.25);
        MG.settled = false;
      }
    }).catch(function () { /* 后端未就绪时静默重试 */ });
  };

  // 启动/停止增量轮询（幂等）
  MG.startIncrement = function () {
    if (MG._incTimer) return;
    MG._incTimer = setInterval(MG.pollIncrement, 3000);
  };
  MG.stopIncrement = function () {
    if (MG._incTimer) { clearInterval(MG._incTimer); MG._incTimer = null; }
  };

  // 选根：优先输入框 id，否则取第一个用户发言节点
  MG.pickRoot = function () {
    var raw = document.getElementById('rootId').value.trim();
    if (raw) return parseInt(raw, 10);
    for (var i = 0; i < MG.nodes.length; i++) {
      if (MG.nodes[i].source === 'user') return MG.nodes[i].id;
    }
    return MG.nodes.length ? MG.nodes[0].id : 0;
  };

  // 应用当前视图：切换按钮高亮，径向/时间轴立即重排
  MG.applyMode = function () {
    document.getElementById('modeForce').className = MG.MODE === 'force' ? '' : 'ghost';
    document.getElementById('modeRadial').className = MG.MODE === 'radial' ? '' : 'ghost';
    document.getElementById('modeTimeline').className = MG.MODE === 'timeline' ? '' : 'ghost';
    if (MG.MODE === 'radial') MG.layoutRadial(MG.pickRoot());
    else if (MG.MODE === 'timeline') {
      MG.layoutTimeline();
      // 时间轴按时间与来源定位，同一时刻/同一来源的节点会重叠；
      // 布局后跑一次硬分离，保证节点间至少留 MIN_GAP 的间距。
      MG.separateOverlaps();
    }
    else { MG.settled = false; MG.alpha = 1; }   // 回力导向需重新布局
  };

  // 按当前下拉选择拉取图数据
  MG.load = function () {
    var conv = document.getElementById('conv').value.trim();
    var url = '/memory/graph' + (conv ? ('?conv_id=' + encodeURIComponent(conv)) : '');
    fetch(url).then(function (r) { return r.json(); }).then(MG.build);
  };

  // 初始加载：填会话下拉并自动载入最近一个会话（避免一进来查全库卡死）
  MG.loadDefaultConv = function () {
    fetch('/memory/conversations').then(function (r) { return r.json(); }).then(function (d) {
      var list = (d && d.conversations) || [];
      var sel = document.getElementById('conv');
      list.forEach(function (c) {
        var opt = document.createElement('option');
        opt.value = c.conv_id || '';
        opt.textContent = (c.title || c.conv_id || '(无标题)').slice(0, 40);
        sel.appendChild(opt);
      });
      if (list.length) { sel.value = list[0].conv_id || ''; MG.load(); }
      else { document.getElementById('stat').textContent = '暂无会话'; }
    }).catch(function () {
      document.getElementById('stat').textContent = '加载会话列表失败';
    });
  };

  // ---------- 详情弹框 ----------
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/"/g, '&quot;'); }

  // 从 blocks 抽纯文本，供详情展示原始内容
  function blocksToText(blocks) {
    var parts = [];
    (blocks || []).forEach(function (b) {
      if (!b || typeof b !== 'object') return;
      var t = b.text || b.code || '';
      if (t) parts.push(String(t));
    });
    return parts.join('\n');
  }

  // 双击节点：拉取完整节点，弹出详情（原始文本 / 关键词 / 蒸馏结果 / 时间，可编辑）
  MG.showDetail = function (n) {
    fetch('/memory/node/' + n.id).then(function (r) { return r.json(); }).then(function (d) {
      var node = (d && d.node) || {};
      var raw = blocksToText(node.blocks);
      var html = '';
      html += '<div class="dt-row"><b>节点</b> #' + n.id + '　[' + (node.source || '') + '/' + (node.tier || '') + ']</div>';
      html += '<div class="dt-row"><b>时间</b> ' + (node.created_at ? new Date(node.created_at * 1000).toLocaleString() : '') + '</div>';
      html += '<div class="dt-row"><b>强度</b> ' + (node.strength != null ? node.strength : '') + '　<b>命中</b> ' + (node.hit_count || 0) + '</div>';
      html += '<div class="dt-row"><b>关键词（逗号分隔）</b></div><input id="dtKw" class="dt-in" value="' + escapeAttr((node.keywords || []).join(', ')) + '" />';
      html += '<div class="dt-row"><b>蒸馏结果（可编辑）</b></div><textarea id="dtEssence" class="dt-ta">' + escapeHtml(node.essence || '') + '</textarea>';
      html += '<div class="dt-row"><b>原始文本</b></div><textarea class="dt-ta" readonly>' + escapeHtml(raw.slice(0, 3000)) + '</textarea>';
      html += '<div class="dt-actions">';
      html += '<button id="dtSave">保存修改</button>';
      html += '<button id="dtDel" class="danger">删除此节点</button>';
      html += '<button id="dtClose" class="ghost">关闭</button>';
      html += '</div>';
      var box = document.getElementById('detail');
      document.getElementById('detailBody').innerHTML = html;
      box.style.display = 'flex';
      document.getElementById('dtClose').onclick = function () { box.style.display = 'none'; };
      document.getElementById('dtSave').onclick = function () { MG.saveDetail(n.id); };
      document.getElementById('dtDel').onclick = function () { MG.deleteNode(n.id); };
    });
  };

  // 保存详情：写回精华与关键词
  MG.saveDetail = function (nodeId) {
    var essence = document.getElementById('dtEssence').value;
    var kwRaw = document.getElementById('dtKw').value;
    var keywords = kwRaw.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    fetch('/memory/set', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: nodeId, essence: essence, keywords: keywords })
    }).then(function () { alert('已保存'); }).catch(function () { alert('保存失败'); });
  };

  // 硬删节点：二次确认后真删，不可恢复
  MG.deleteNode = function (nodeId) {
    if (!confirm('确定永久删除节点 #' + nodeId + '？此操作不可恢复。')) return;
    fetch('/memory/node/delete', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: nodeId })
    }).then(function () {
      document.getElementById('detail').style.display = 'none';
      MG.load();
    }).catch(function () { alert('删除失败'); });
  };
})();
