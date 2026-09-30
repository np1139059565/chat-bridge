// 模块：skills/debug_chrome/extension/drawer/02_ui-helpers.js
// 用途：抽屉界面的渲染辅助函数集合。
//       把 Vue 的 h() 与一组常用表单控件的构造封装成 D.xxx，
//       让各界面分片（03_ui-chat / 04_ui-settings / 05_main）用统一方式拼 UI。
// 依赖：Vue 全局对象（h 函数）、window.AIDrawer（命名空间 D）。
(function () {
  const { h } = Vue;
  const D = window.AIDrawer;

  // 把 Vue 的 h 暴露到命名空间，供其它分片直接调用 D.h。
  D.h = h;

  /**
   * 构造「标签 + 输入控件」的一行表单字段。
   * @param {string} labelText 标签文字
   * @param {Object} inputNode 已构造好的输入控件 VNode
   */
  D.field = function (labelText, inputNode) {
    return h('div', [h('label', labelText), inputNode]);
  };

  /**
   * 构造单行文本输入框。
   * @param {string} value 当前值
   * @param {Function} onInput 输入回调（收到字符串值）
   * @param {string} placeholder 占位提示
   * @param {Object} attrs 附加属性（透传给 input）
   */
  D.textInput = function (value, onInput, placeholder, attrs) {
    return h('input', Object.assign({ value, placeholder, onInput: (e) => onInput(e.target.value) }, attrs || {}));
  };

  /**
   * 构造数字输入框，回调时已转为 Number。
   * @param {number} value 当前值
   * @param {Function} onInput 输入回调（收到数字）
   * @param {Object} attrs 附加属性
   */
  D.numInput = function (value, onInput, attrs) {
    return h('input', Object.assign({ type: 'number', value, onInput: (e) => onInput(Number(e.target.value)) }, attrs || {}));
  };

  /**
   * 构造带文字标签的复选框。
   * @param {boolean} checked 是否勾选
   * @param {Function} onChange 勾选回调（收到布尔值）
   * @param {string} labelText 复选框后的文字
   */
  D.checkBox = function (checked, onChange, labelText) {
    return h('label', { class: 'checkbox' }, [
      h('input', { type: 'checkbox', checked, onChange: (e) => onChange(e.target.checked) }),
      ' ' + labelText,
    ]);
  };

  /**
   * 构造下拉选择框。
   * @param {string} value 当前选中值
   * @param {Function} onChange 变更回调（收到选中值）
   * @param {Array} options 选项数组 [{ value, label }]
   */
  D.selectBox = function (value, onChange, options) {
    return h('select', { value, onChange: (e) => onChange(e.target.value) }, options.map((o) => h('option', { value: o.value }, o.label)));
  };

  /**
   * 构造多行文本域。
   * @param {string} value 当前值
   * @param {Function} onInput 输入回调（收到字符串值）
   * @param {string} placeholder 占位提示
   */
  D.textArea = function (value, onInput, placeholder) {
    return h('textarea', { value, placeholder, onInput: (e) => onInput(e.target.value) });
  };
})();
