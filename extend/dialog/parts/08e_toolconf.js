// 模块：extend/dialog/parts/08e_toolconf.js
// 用途：工具配置的通用渲染界面。按后端返回的声明（类型 / 范围 / 选项）
//       自动生成对应控件，不针对任何具体工具写专属代码。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /**
   * 按声明渲染单个配置控件。
   * @param {Object} ctx  Vue 实例
   * @param {string} tool 工具名
   * @param {Object} spec 配置声明（含 key / label / type / value / min / max / options）
   * @returns {VNode} 一行控件
   */
  function renderField(ctx, tool, spec) {
    const key = spec.key;
    const val = spec.value;
    let control;
    if (spec.type === 'integer') {
      control = h('input', {
        type: 'number',
        class: 'tc-num',
        value: val,
        min: spec.min,
        max: spec.max,
        onChange: (ev) => ctx.setToolConfig(tool, key, Number(ev.target.value)),
      });
    } else if (spec.type === 'boolean') {
      control = h('input', {
        type: 'checkbox',
        checked: !!val,
        onChange: (ev) => ctx.setToolConfig(tool, key, ev.target.checked),
      });
    } else if (spec.type === 'multiselect') {
      // 多选：每个选项一个复选框，勾选结果组成数组回写
      const cur = Array.isArray(val) ? val : [];
      control = h('div', { class: 'check-row' }, (spec.options || []).map((opt) =>
        h('label', { class: 'check-item', key: opt }, [
          h('input', {
            type: 'checkbox',
            checked: cur.indexOf(opt) >= 0,
            onChange: (ev) => {
              const next = cur.slice();
              const i = next.indexOf(opt);
              if (ev.target.checked && i < 0) next.push(opt);
              if (!ev.target.checked && i >= 0) next.splice(i, 1);
              ctx.setToolConfig(tool, key, next);
            },
          }),
          h('span', {}, opt),
        ])
      ));
    } else {
      control = h('input', {
        type: 'text',
        value: val == null ? '' : String(val),
        onChange: (ev) => ctx.setToolConfig(tool, key, ev.target.value),
      });
    }
    return h('div', { class: 'tc-row', key: key }, [
      h('div', { class: 'tc-label' }, [
        h('span', {}, spec.label),
        spec.hint ? h('div', { class: 'tc-hint' }, spec.hint) : null,
      ]),
      h('div', { class: 'tc-control' }, control),
    ]);
  }

  /**
   * 渲染某个工具自己的配置项，挂在该工具展开区内。
   *
   * 配置跟随工具：每个工具只渲染自己声明的配置，不集中到独立区块。
   * @param {Object} ctx  Vue 实例
   * @param {string} tool 工具名
   * @returns {VNode|null} 配置节点；该工具无配置声明时返回 null
   */
  D.renderToolConfig = function (ctx, tool) {
    const rows = (ctx.toolConfig || {})[tool] || [];
    if (!rows.length) return null;
    return h('div', { class: 'tc-body' }, rows.map((spec) => renderField(ctx, tool, spec)));
  };
})();
