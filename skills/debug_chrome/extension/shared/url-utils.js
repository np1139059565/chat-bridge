// 模块：skills/debug_chrome/extension/shared/url-utils.js
// 用途：调试扩展内共享的 URL 归一工具，供 content 脚本与抽屉页面共同调用。
// 对外接口：window.AIUrlUtils = { normalizeUrl }
// 依赖：无（仅使用标准 URL API）
//
// 说明：content 脚本与 drawer iframe 属不同执行环境，各自命名空间独立，
// 因此本文件挂在通用全局对象 window.AIUrlUtils 上，两侧分别引用同一实现，
// 避免同一段归一逻辑在 content/04_element-selector.js 与 drawer/00_config.js 中重复维护。
(function (global) {
  'use strict';

  /**
   * 归一 URL：去掉查询串与锚点，仅保留「协议 + 主机 + 路径」。
   * 映射以「页面路径」为单位，参数变化不影响匹配。
   * chrome-extension:// 等非 http(s) 协议的 origin 为 "null"，
   * 必须改用 protocol + host 重建，否则插件自身页面会变成 "null/..."。
   * @param {string} url 原始 URL
   * @returns {string} 归一化后的 URL；解析失败返回空串
   */
  function normalizeUrl(url) {
    if (!url) return '';
    try {
      const u = new URL(url, location.href);
      // 路径末尾的斜杠去掉（根路径 "/" 除外），保证同一页面只有一种写法
      let path = u.pathname;
      if (path.length > 1 && path.endsWith('/')) path = path.slice(0, -1);
      // origin 为 "null" 时（如 chrome-extension://）退回 protocol + host 拼接
      const base = (u.origin && u.origin !== 'null') ? u.origin : (u.protocol + '//' + u.host);
      return base + path;
    } catch (e) {
      return '';
    }
  }

  // 暴露到全局，供 <script> 引入与 content script 注入后直接使用
  global.AIUrlUtils = { normalizeUrl: normalizeUrl };
})(typeof window !== 'undefined' ? window : this);
