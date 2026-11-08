// 模块：extend/content/03c_rich_editor.js
// 用途：富文本编辑器（contenteditable）的写值与清空。
//
// 背景：各网页 AI 的输入框分两类。传统表单控件（textarea / input）有 value 属性，
// 用原生 setter 写值即可触发框架响应式更新；富文本编辑器（千问的 Slate、
// 元宝的 Quill）是 contenteditable div，没有 value 属性，原生 setter 会直接抛
// Illegal invocation，表现为「框里没字、发送按钮始终禁用、根本没办法输入」。
// 这类编辑器唯一的可靠路径是派发 paste 事件——编辑器监听 paste 后按自身模型插入
// 内容，DOM 与内部状态同步更新。
//
// 来源：自 03_bridge.js 拆出（2026-11-09：原文件 490 行超出仓库 450 行上限）。
// 同挂 window.AIMirrorContent 命名空间；在 03_bridge.js 之后载入，
// 03_bridge.js 的 writeInputValue 运行期读取这里挂上的函数，故先后顺序不影响调用。
// 依赖：content/00_state.js（A.log / A.warn）

(function () {
  'use strict';
  const A = window.AIMirrorContent;

  /**
   * 判断元素是否为富文本编辑器（contenteditable）。
   * 兼容 contenteditable="true" 与空字符串两种写法（后者等价于 true）。
   * @param {Element} el 待判定元素
   * @returns {boolean} 是则返回 true
   */
  A.isRichEditor = function (el) {
    if (!el || el.nodeType !== 1) return false;
    const editable = el.getAttribute && el.getAttribute('contenteditable');
    return editable === 'true' || editable === '';
  };

  /**
   * 向富文本编辑器写入文本。
   *
   * 改 innerHTML / textContent 只会改 DOM，编辑器自身的内部状态不会更新，
   * 表现为「框里有字但发送按钮仍是禁用」。paste 事件是唯一能让二者同步的路径。
   * 写入前先清空残留，避免与上一次未发送的文本拼在一起。
   *
   * @param {Element} ed 编辑器元素
   * @param {string} text 文本
   * @returns {boolean} 是否已派发成功
   */
  A.writeRichEditor = function (ed, text) {
    if (!ed) return false;
    try {
      A.clearRichEditor(ed);
      const dt = new DataTransfer();
      dt.setData('text/plain', String(text || ''));
      ed.dispatchEvent(new ClipboardEvent('paste', {
        clipboardData: dt, bubbles: true, cancelable: true,
      }));
      return true;
    } catch (e) {
      A.warn('writeRichEditor: paste 注入失败：' + (e && e.message));
      return false;
    }
  };

  /**
   * 清空富文本编辑器的内容。
   *
   * 只清 DOM 层：execCommand 不会同步编辑器的内部状态，残留状态无害
   * （空文本点发送无实际效果），继续扰动页面反而可能触发额外渲染。
   * 本就为空时直接返回，不做任何扰动。
   *
   * @param {Element} ed 编辑器元素
   */
  A.clearRichEditor = function (ed) {
    if (!ed) return;
    try {
      ed.focus();
      if (!String(ed.textContent || '').trim()) return;
      document.execCommand('selectAll', false, null);
      document.execCommand('delete', false, null);
    } catch (e) {
      A.warn('clearRichEditor: 清空失败（忽略）：' + (e && e.message));
    }
  };
})();
