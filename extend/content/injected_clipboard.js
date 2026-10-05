// 模块：extend/content/injected_clipboard.js
// 运行世界：MAIN（页面主世界）
// 用途：
//   1. hook navigator.clipboard.writeText，截获页面自身写入剪贴板的内容；
//   2. 在主世界执行「元素表达式」并点击。
//
// 为什么求值要放主世界：
//   MV3 内容脚本运行在隔离世界，受扩展 CSP 约束（script-src 不含 unsafe-eval），
//   new Function / eval 会直接抛错——导致任何带 JS 的表达式（如
//   Array.from(document.querySelectorAll("...")).reverse()[0]）都报「语法无效」。
//   主世界不受扩展 CSP 约束，能正常执行这类表达式。
//
// 通信：主世界无法直接用 chrome.*，统一用 window.postMessage 与内容脚本互通。
(function () {
  'use strict';

  // ---------- 一、剪贴板 hook ----------
  try {
    const clip = navigator.clipboard;
    if (clip && typeof clip.writeText === 'function') {
      const orig = clip.writeText.bind(clip);
      clip.writeText = function (text) {
        // 把页面写入的内容原样回传；不阻断原行为，页面复制照常生效
        try {
          window.postMessage({
            source: 'ai-mirror-clip',
            type: 'copied',
            text: String(text == null ? '' : text)
          }, '*');
        } catch (e) { /* 忽略 */ }
        return orig(text);
      };
    }
  } catch (e) { /* 环境不支持则静默退出 */ }

  // ---------- 二、主世界执行元素表达式 ----------
  // 内容脚本发来：{ source:'ai-mirror-exec', type:'click', reqId, expr, mode }
  //   mode='unique'（默认）：表达式须得到「一个且唯一」的元素，才点击；
  //   mode='last'：取最后一个匹配元素点击（采集 Markdown 用，面向最新一条）。
  // 回传：{ source:'ai-mirror-exec', type:'click_result', reqId, ok, reason, count }

  /** 把表达式结果规整成元素数组（单个元素 / NodeList / HTMLCollection / 数组）。 */
  function collectElements(val) {
    let list = [];
    if (val && val.nodeType === 1) list = [val];
    else if (val && typeof val.length === 'number') list = Array.prototype.slice.call(val);
    return list.filter(function (n) { return n && n.nodeType === 1; });
  }

  /** 滚动到可见位置并点击。 */
  function clickEl(el) {
    try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) { /* 忽略 */ }
    el.click();
  }

  window.addEventListener('message', function (e) {
    const d = e.data;
    if (!d || d.source !== 'ai-mirror-exec' || d.type !== 'click') return;
    const result = {
      source: 'ai-mirror-exec', type: 'click_result',
      reqId: d.reqId, ok: false, reason: '', count: 0
    };
    // 统一语法：表达式一律按 JS 求值（选择器用 document.querySelectorAll('...') 写法）。
    // 不再对纯 CSS 选择器做回退——旧数据已迁移到新语法，执行端只认一套，
    // 避免「兼容两套」带来的歧义与误判。
    const exprStr = String(d.expr == null ? '' : d.expr);
    let val;
    try {
      val = (new Function('return (' + exprStr + ');'))();
    } catch (err) {
      // 求值失败：如实回传原因，不误报、不隐瞒
      result.reason = 'invalid';
      result.error = String(err);
      window.postMessage(result, '*');
      return;
    }
    const list = collectElements(val);
    result.count = list.length;
    if (!list.length) {
      result.reason = 'not_found';
    } else if (d.mode === 'last') {
      clickEl(list[list.length - 1]);
      result.ok = true;
    } else if (list.length > 1) {
      // 唯一性要求：得到多个元素即不算「一个且唯一」，如实报告
      result.reason = 'not_unique';
    } else {
      clickEl(list[0]);
      result.ok = true;
    }
    window.postMessage(result, '*');
  });
})();
