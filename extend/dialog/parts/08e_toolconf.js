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
      control = h('div', { class: 'tc-multi' }, (spec.options || []).map((opt) =>
        h('label', { class: 'tc-opt', key: opt }, [
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
   * 渲染「工具配置」区块：遍历全部已声明配置的工具。
   * @param {Object} ctx Vue 实例
   * @returns {VNode|null} 区块节点；无任何配置声明时返回 null
   */
  D.renderToolConfigBlock = function (ctx) {
    const all = ctx.toolConfig || {};
    const tools = Object.keys(all);
    if (!tools.length) return null;
    const open = !!ctx.toolConfOpen;
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', {
          title: '工具的可调参数，改动立即写回后端并生效'
        }, '工具配置'),
        h('button', { onClick: () => { ctx.toolConfOpen = !ctx.toolConfOpen; } }, open ? '▾' : '▸')
      ]),
      open ? h('div', { class: 'tc-body' }, tools.map((tool) =>
        h('div', { class: 'tc-group', key: tool }, [
          h('div', { class: 'tc-group-name' }, tool),
          ...(all[tool] || []).map((spec) => renderField(ctx, tool, spec)),
        ])
      )) : null
    ]);
  };
})();
