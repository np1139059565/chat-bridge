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
    const isWhitelist = cur === 'project_whitelist';
    // 紧凑布局：档位横排一行，描述收进悬停提示；白名单仅在对应档展开
    return h('div', { class: 'perms-body' }, [
      h('div', { class: 'perms-line' }, [
        h('span', { class: 'perms-title' }, '文件访问权限'),
        h('div', { class: 'perms-modes' }, MODES.map((m) => h('label', {
          class: 'perms-opt' + (cur === m.key ? ' active' : ''),
          key: m.key,
          title: m.desc,
        }, [
          h('input', {
            type: 'radio',
            name: 'file-access',
            checked: cur === m.key,
            onChange: () => ctx.setFileAccess(m.key),
          }),
          h('span', {}, m.label),
        ]))),
      ]),
      isWhitelist ? h('div', { class: 'perms-whitelist' }, [
        h('div', { class: 'hint' }, '白名单目录（每行一个）：'),
        h('textarea', {
          class: 'perms-dirs',
          spellcheck: false,
          value: (perms.whitelist_dirs || []).join('\n'),
          onChange: (ev) => ctx.setWhitelistDirs(ev.target.value),
        }),
      ]) : null,
    ]);
  };
})();
