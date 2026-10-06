// 记忆图谱·绘制：清屏、画边、画节点、主循环。
(function () {
  'use strict';
  var MG = window.MG;

  // 绘制一帧：先边后节点，最后画标签。
  // 选中节点时，与它相连的边加粗高亮；其余照常，不淡化。
  MG.draw = function () {
    var ctx = MG.ctx, nodes = MG.nodes, edges = MG.edges;
    ctx.clearRect(0, 0, MG.W, MG.H);
    ctx.save();
    ctx.translate(MG.view.x, MG.view.y);
    ctx.scale(MG.view.k, MG.view.k);
    var hasSel = !!MG.selected;

    for (var e = 0; e < edges.length; e++) {
      var ed = edges[e];
      if (!MG.edgeOn[ed.kind] || !ed.s || !ed.t) continue;
      var conn = hasSel && (ed.s.id === MG.selected.id || ed.t.id === MG.selected.id);
      ctx.beginPath();
      ctx.moveTo(ed.s.x, ed.s.y);
      ctx.lineTo(ed.t.x, ed.t.y);
      // 线宽调大、提高不透明度：原线太细，颜色几乎看不出
      ctx.lineWidth = conn ? 4 : 2;
      if (ed.kind === 'associative') {
        ctx.setLineDash([5, 4]);
        ctx.strokeStyle = 'rgba(224,178,58,0.8)';
      } else if (ed.kind === 'branch') {
        ctx.setLineDash([3, 4]);
        ctx.strokeStyle = 'rgba(170,170,170,0.85)';
      } else {
        ctx.setLineDash([]);
        ctx.strokeStyle = 'rgba(120,120,120,0.6)';
      }
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.lineWidth = 1;

    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      var isSel = hasSel && n.id === MG.selected.id;
      var isNb = hasSel && !isSel && MG.selectedSet[n.id];
      // 高亮时放大：选中 1.6 倍、邻居 1.25 倍，其余原尺寸
      var r = MG.radiusOf(n) * (isSel ? 1.6 : (isNb ? 1.25 : 1));
      // 发光：选中/邻居先画一圈半透明大光晕，再画实体，视觉更醒目
      if (isSel || isNb) {
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + (isSel ? 10 : 6), 0, Math.PI * 2);
        ctx.fillStyle = isSel ? 'rgba(255,255,255,0.28)' : 'rgba(255,255,255,0.14)';
        ctx.fill();
      }
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fillStyle = MG.colorOf(n);
      ctx.fill();
      // 描边：选中亮白加粗、邻居淡白
      if (isSel || isNb) {
        ctx.lineWidth = isSel ? 3 : 2;
        ctx.strokeStyle = isSel ? '#fff' : 'rgba(255,255,255,0.7)';
        ctx.stroke();
        ctx.lineWidth = 1;
      }
      // 关键词标签：仅非高亮状态显示，高亮时避免遮挡
      if (!hasSel && n.keywords && n.keywords.length) {
        ctx.fillStyle = 'rgba(200,200,200,0.75)';
        ctx.font = '11px system-ui';
        ctx.fillText(n.keywords[0].slice(0, 8), n.x + r + 2, n.y + 3);
      }
    }
    ctx.restore();
  };

  // 主循环：力导向收敛后停帧（只在拖动/尺寸变化时继续），省性能。
  MG.loop = function () {
    if (MG.MODE === 'force' && !MG.settled) MG.tick();
    MG.draw();
    requestAnimationFrame(MG.loop);
  };
})();
