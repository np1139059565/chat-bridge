// 记忆图谱·入口：初始化 DOM、绑定交互、启动主循环。
// 依赖加载顺序：mg_core → mg_render → mg_interact → mg_data → mg_main。
(function () {
  'use strict';
  var MG = window.MG;

  MG.initDom();
  MG.resize();
  window.addEventListener('resize', MG.resize);
  MG.bindAll();
  MG.loadDefaultConv();
  MG.startIncrement();   // 启动增量轮询：随 AI 生成逐个增加节点
  MG.loop();
})();
