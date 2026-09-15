/* 悬浮对话框 Vue 应用入口（本地 Vue3 全局构建，无打包工具）
 * 注意：Manifest V3 扩展页 CSP 禁止 unsafe-eval，因此不能用 template 字符串
 * （运行期编译会触发 new Function）。这里改用渲染函数 h()，无需编译器。
 *
 * 实现已按职责拆分到 dialog/parts/ 目录（需按序号先加载）：
 *   00_data.js          命名空间、常量、data / computed / mounted
 *   01_backend.js       后端交互：地址发现、配置读写、外部卡片轮询
 *   02_rules.js         规则文件增删改与优先级
 *   03_custom_tools.js  自定义工具读取、上下线、扫描与安装
 *   04_sessions.js      多会话切换 / 恢复 / 持久化、历史卡片删除
 *   05_messages.js      工具列表、System Prompt、消息接收与卡片构建、导出
 *   06_execute.js       卡片执行与自动回传倒计时
 *   07_render.js        渲染函数
 * 本文件仅负责把这些分片装配成 createApp 的选项并挂载。
 */
(function () {
  const D = window.AIMirrorDialog;

  const app = Vue.createApp({
    data: D.data,
    computed: D.computed,
    mounted: D.mounted,
    methods: D.methods,
    render: D.render
  });

  app.mount('#app');
})();
