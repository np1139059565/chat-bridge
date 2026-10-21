// 模块：extend/dialog/parts/08d_permissions.js
// 用途：文件访问权限的设置界面。独立成模块，避免侵入设置页主文件，
//       也使「权限」这一关注点自成一体。
// 设计：四档策略与后端 path_policy 一一对应；改动立即写回后端并生效，无需重启。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、00a_api.js（D.apiFetch）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  // 四档策略：与后端 core/path_policy.py 的 MODES 严格一致
  const MODES = [
    { key: 'project', label: '仅当前项目', desc: '只能访问工程目录内的文件。最安全，但读不了其它盘的项目。' },
    { key: 'project_whitelist', label: '工程 + 白名单', desc: '工程目录，外加下面填写的目录。常用项目加进白名单即可。' },
    { key: 'all_readonly', label: '全盘只读', desc: '任意文件都能读，但写入仍限工程目录内。' },
    { key: 'all', label: '完全放开', desc: '读写都不限制。最自由，也最没有保护。' },
  ];

  /**
   * 渲染「文件访问权限」区块。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderPermissionsBlock = function (ctx) {
    const perms = ctx.permissions || {};
    const cur = perms.file_access || 'all';
    const open = !!ctx.permsOpen;
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', {
          title: '控制文件类工具能访问哪些路径。改动立即生效，无需重启。'
        }, '文件访问权限'),
        h('button', { onClick: () => { ctx.permsOpen = !ctx.permsOpen; } }, open ? '▾' : '▸')
      ]),
      open ? h('div', { class: 'perms-body' }, [
        // 四档单选：每档都写明代价，避免用户只看名字就选了最宽的
        ...MODES.map((m) => h('label', {
          class: 'perms-mode' + (cur === m.key ? ' active' : ''),
          key: m.key,
        }, [
          h('input', {
            type: 'radio',
            name: 'file-access',
            checked: cur === m.key,
            onChange: () => ctx.setFileAccess(m.key),
          }),
          h('div', { class: 'perms-text' }, [
            h('b', {}, m.label),
            h('div', { class: 'perms-desc' }, m.desc),
          ]),
        ])),
        // 白名单目录：仅在该档下有意义，其它档位置灰提示
        h('div', { class: 'perms-whitelist' + (cur === 'project_whitelist' ? '' : ' dim') }, [
          h('div', { class: 'hint' }, '白名单目录（每行一个，仅「工程 + 白名单」档生效）：'),
          h('textarea', {
            class: 'perms-dirs',
            spellcheck: false,
            disabled: cur !== 'project_whitelist',
            value: (perms.whitelist_dirs || []).join('\n'),
            onChange: (ev) => ctx.setWhitelistDirs(ev.target.value),
          }),
        ]),
      ]) : null
    ]);
  };
})();
