// 模块：shared/backend-default.js
// 用途：工具服务（chat-bridge）后端地址的唯一默认值来源，以及「存储值 → 默认值」的解析规则。
//       内容脚本、抽屉、后台脚本三处运行环境互不相通（页面隔离环境 / iframe 文档 / MV3 worker），
//       无法共享同一个 JS 变量；因此把默认值与解析规则收拢到本文件，三处各自引用本文件的结果。
//       换端口时只改本文件顶部的 DEFAULT_BACKEND_URL 一处。
// 依赖：无
// 导出：挂到全局（浏览器为 window，worker 为 self）的 AIStyleBackend
(function (root) {
  'use strict';

  // 工具服务的默认地址，与 chat-bridge 的 flask.port 默认值一致。
  // 用户可在抽屉设置页修改，修改后的值存在 chrome.storage.local。
  const DEFAULT_BACKEND_URL = 'http://127.0.0.1:5000';

  /**
   * 从存储值解析出最终使用的后端地址。
   * 优先级：独立的 backendUrl 键 → 配置对象里的 backend_url → 默认值。
   * 空串按「未设置」处理，避免历史遗留的空值让连接地址变成空。
   *
   * @param {string} storedUrl chrome.storage.local 里的 backendUrl
   * @param {Object} cfg       chrome.storage.local 里的 aistyleCfg
   * @param {string} [fallback] 解析不到时使用的地址，缺省为本文件的默认值
   * @returns {string} 最终使用的后端地址
   */
  function resolve(storedUrl, cfg, fallback) {
    const base = fallback || DEFAULT_BACKEND_URL;
    const fromCfg = (cfg && cfg.backend_url) || '';
    return storedUrl || fromCfg || base;
  }

  root.AIStyleBackend = {
    DEFAULT_BACKEND_URL: DEFAULT_BACKEND_URL,
    resolve: resolve,
  };
})(typeof window !== 'undefined' ? window : self);
