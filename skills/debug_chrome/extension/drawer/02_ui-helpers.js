// 渲染辅助函数
(function () {
  const { h } = Vue;
  const D = window.AIDrawer;

  D.h = h;

  D.field = function (labelText, inputNode) {
    return h('div', [h('label', labelText), inputNode]);
  };

  D.textInput = function (value, onInput, placeholder, attrs) {
    return h('input', Object.assign({ value, placeholder, onInput: (e) => onInput(e.target.value) }, attrs || {}));
  };

  D.numInput = function (value, onInput, attrs) {
    return h('input', Object.assign({ type: 'number', value, onInput: (e) => onInput(Number(e.target.value)) }, attrs || {}));
  };

  D.checkBox = function (checked, onChange, labelText) {
    return h('label', { class: 'checkbox' }, [
      h('input', { type: 'checkbox', checked, onChange: (e) => onChange(e.target.checked) }),
      ' ' + labelText,
    ]);
  };

  D.selectBox = function (value, onChange, options) {
    return h('select', { value, onChange: (e) => onChange(e.target.value) }, options.map((o) => h('option', { value: o.value }, o.label)));
  };

  D.textArea = function (value, onInput, placeholder) {
    return h('textarea', { value, placeholder, onInput: (e) => onInput(e.target.value) });
  };
})();
