// 模块：content/08_injected_main.js
// 用途：运行在页面「主世界」的脚本，向页面暴露 window.selectAiDebugElement(el)，
//       让用户能对无法用鼠标点选（被遮挡、pointer-events:none、动态生成）的元素，
//       自行取到 DOM 对象后直接触发选中。
// 关键约束：DOM 元素无法跨 world 传递。主世界拿不到隔离世界的选中逻辑，隔离世界
//       也拿不到主世界的元素引用，因此这里只给元素打一个一次性标记，再通过
//       postMessage 通知隔离世界的内容脚本按标记找回元素并完成选中。
// 加载方式：由内容脚本 07_index.js 以 <script src=...> 注入；同一页面只定义一次。
(function () {
  'use strict';
  // 已注入过则不重复定义（页面可能被多次注入，例如扩展重载）
  if (window.__AI_STYLE_DEBUG_MAIN__) return;
  window.__AI_STYLE_DEBUG_MAIN__ = true;

  // 临时标记属性名：内容脚本据此跨 world 找回同一个元素。
  // 用 data- 前缀，避免与页面自身属性冲突；用后即删，不留痕。
  var MARK_ATTR = 'data-ai-debug-pick';

  /**
   * 传入一个 DOM 元素即可触发选中，无需鼠标点选。
   * 元素可来自顶层文档，也可来自（同源）iframe 文档——通过 el.ownerDocument
   * 判定它所属的文档与 URL，选择结果会带上该文档地址，便于定位与路由。
   * @param {Element} el 目标 DOM 元素
   * @returns {boolean} 是否已成功发出选中请求
   */
  window.selectAiDebugElement = function (el) {
    // 只接受元素节点，拒绝文本 / 注释 / null 等无效入参
    if (!el || el.nodeType !== 1) {
      console.warn('[AI Style Debug] selectAiDebugElement: 请传入一个 DOM 元素');
      return false;
    }
    // 元素所属文档：可能不是顶层文档（元素在 iframe 内时）
    var doc = el.ownerDocument || document;
    // 生成一次性标记：时间戳 + 随机数，保证同页多次调用互不冲突
    var mark = 'ai-debug-pick-' + Date.now() + '-' + Math.floor(Math.random() * 1e9);
    try {
      el.setAttribute(MARK_ATTR, mark);
    } catch (e) {
      // 某些只读 / 冻结元素可能拒绝写属性，此时无法用标记法定位，直接失败
      console.warn('[AI Style Debug] selectAiDebugElement: 无法在元素上打标记', e);
      return false;
    }
    // 把标记与元素所属文档 URL 发给顶层内容脚本：
    // 内容脚本运行在顶层文档，故用 window.top 作为投递目标。
    var target = window.top || window;
    target.postMessage({
      source: 'ai-debug-main',
      type: 'select-by-mark',
      mark: mark,
      url: (doc.location && doc.location.href) || ''
    }, '*');
    return true;
  };
})();
