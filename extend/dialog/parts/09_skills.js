// 模块：extend/dialog/parts/09_skills.js
// 用途：设置页「技能」区块——技能清单渲染、技能一键上下线、技能内工具开关、
//       SKILL.md 文档的查看与编辑。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
//
// 说明：技能是「容器」，工具是「能力」。本区块把技能提升为一等实体：
// 每个技能一行，展开后可见其包含的全部工具，并提供一键上下线；
// 技能内含的工具同时仍出现在「工具」区块，两处开关同源。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;
  const h = Vue.h;

  /** 读取技能管理视图：全部技能 + 其包含工具 + 开关状态。 */
  M.loadSkillsManage = async function () {
    try {
      const data = await D.apiFetch(this, '/prompt_sections', {
        headers: { 'Accept': 'application/json' }
      });
      this.skillsManage = (data && data.skillsManage) || [];
    } catch (e) {
      this.skillsManage = [];
    }
  };

  /** 展开 / 收起某个技能。 */
  M.toggleSkill = function (name) {
    this.skillsExpanded[name] = !this.skillsExpanded[name];
  };

  /**
   * 技能一键上 / 下线：批量设置该技能下全部工具的开关。
   * 乐观更新本技能与「工具」区块中同名工具的开关，失败回滚。
   */
  M.setSkillEnabled = async function (name, enabled) {
    const skill = this.skillsManage.find((s) => s.name === name);
    const affected = skill ? skill.tools.map((t) => t.name) : [];
    // 乐观更新：技能内工具 + 自定义工具列表中的同名项
    if (skill) {
      skill.tools.forEach((t) => { t.enabled = enabled; });
      skill.enabled_count = enabled ? skill.tools.length : 0;
    }
    affected.forEach((tn) => {
      const ct = this.customTools.find((x) => x.name === tn);
      if (ct) ct.enabled = enabled;
    });
    try {
      await D.apiFetch(this, '/skills/' + encodeURIComponent(name) + '/enabled', {
        method: 'PUT',
        body: { enabled: enabled },
      });
      await this.loadCustomTools();
      await this.fetchTools();        // 影响 System Prompt 与工具树
      await this.loadSkillsManage();  // 回读真实状态，避免乐观值与后端不一致
      this.toast(enabled ? ('技能已上线：' + name) : ('技能已下线：' + name));
    } catch (e) {
      if (skill) {
        skill.tools.forEach((t) => { t.enabled = !enabled; });
        skill.enabled_count = enabled ? 0 : skill.tools.length;
      }
      affected.forEach((tn) => {
        const ct = this.customTools.find((x) => x.name === tn);
        if (ct) ct.enabled = !enabled;
      });
      this.toast('保存失败：' + e);
    }
  };

  /** 展开 / 收起某个技能的说明文档编辑区；首次展开时按需拉取文档。 */
  M.toggleSkillDoc = function (name) {
    const open = !this.skillDocOpen[name];
    this.skillDocOpen[name] = open;
    if (open && this.skillDocText[name] == null) this.loadSkillDoc(name);
  };

  /** 读取技能说明文档（默认 SKILL.md）文本。 */
  M.loadSkillDoc = async function (name) {
    try {
      const data = await D.apiFetch(this, '/skills/' + encodeURIComponent(name) + '/doc?file=SKILL.md', {
        headers: { 'Accept': 'application/json' }
      });
      if (!data.ok) throw new Error(data.error || '读取失败');
      this.skillDocText[name] = data.text || '';
      this.skillDocEdit[name] = data.text || '';
    } catch (e) {
      this.toast('读取文档失败：' + e);
    }
  };

  /** 进入文档编辑态。 */
  M.editSkillDoc = function (name) {
    if (this.skillDocText[name] == null) { this.loadSkillDoc(name); return; }
    this.skillDocEdit[name] = this.skillDocText[name];
    this.skillDocEditing[name] = true;
  };

  /** 保存文档编辑内容并回写磁盘。 */
  M.saveSkillDoc = async function (name) {
    try {
      const data = await D.apiFetch(this, '/skills/' + encodeURIComponent(name) + '/doc', {
        method: 'PUT',
        body: { file: 'SKILL.md', text: this.skillDocEdit[name] || '' },
      });
      if (!data.ok) throw new Error(data.error || '保存失败');
      this.skillDocText[name] = this.skillDocEdit[name] || '';
      this.skillDocEditing[name] = false;
      this.toast('已保存：' + name + '/SKILL.md');
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

  /** 退出文档编辑态，丢弃未保存改动。 */
  M.cancelSkillDoc = function (name) {
    this.skillDocEditing[name] = false;
  };

  /**
   * 技能区块：列出全部技能；每个技能可展开查看其工具与说明文档。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderSkillsBlock = function (ctx) {
    const list = ctx.skillsManage || [];
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', { title: '技能是工具的容器；一键开关控制该技能下全部工具是否上线' }, '技能（' + list.length + '）'),
        h('button', { onClick: () => { ctx.skillsOpen = !ctx.skillsOpen; } }, ctx.skillsOpen ? '▾' : '▸')
      ]),
      h('p', { class: 'hint' }, '技能内的工具同时出现在下方「工具」区块，两处开关同源。'),
      ctx.skillsOpen ? h('div', { class: 'skill-list' },
        list.length
          ? list.map((s) => D.renderSkillRow(ctx, s))
          : [h('div', { class: 'empty' }, '（未发现技能，可在下方扫描目录添加）')]
      ) : null,
      // 添加技能：扫描 skill 目录并安装其中的工具（概念上属于技能管理）
      D.renderCustomInstallBlock(ctx)
    ]);
  };

  /**
   * 单个技能行：头部（名称 / 摘要 / 工具数 / 一键开关）+ 展开区（工具列表 + 文档编辑）。
   * @param {Object} ctx Vue 实例
   * @param {Object} s 技能管理项
   * @returns {VNode} 列表项节点
   */
  D.renderSkillRow = function (ctx, s) {
    const name = s.name;
    const total = s.tool_count || 0;
    const onCount = (s.tools || []).filter((t) => t.enabled).length;
    const allOn = total > 0 && onCount === total;
    return h('div', { class: 'skill-item', key: name }, [
      h('div', { class: 'tree-node', onClick: () => ctx.toggleSkill(name) }, [
        h('span', { class: 'caret' }, ctx.skillsExpanded[name] ? '▾' : '▸'),
        h('b', name),
        h('span', { class: 'desc' }, s.summary || ''),
        h('span', { class: 'badge skill-count' }, onCount + '/' + total + ' 工具')
      ]),
      h('div', { class: 'tool-btns' }, [
        h('button', {
          class: 'switch ' + (allOn ? 'on' : 'off'),
          disabled: total === 0,
          title: '一键控制该技能下全部工具的上下线',
          onClick: () => ctx.setSkillEnabled(name, !allOn)
        }, allOn ? '技能已上线' : '技能已下线')
      ]),
      ctx.skillsExpanded[name] ? h('div', { class: 'tree-detail' }, [
        // 工具列表：每项可单独上下线，改动与「工具」区块同源
        total
          ? h('div', { class: 'skill-tools' }, (s.tools || []).map((t) => h('div', { class: 'skill-tool-row', key: name + ':' + t.name }, [
            h('div', { class: 'skill-tool-info' }, [
              h('b', t.name),
              h('span', { class: 'desc' }, t.description || ''),
              t.provider ? h('span', { class: 'badge' }, '提供方: ' + t.provider) : null
            ]),
            h('button', {
              class: 'switch ' + (t.enabled ? 'on' : 'off'),
              onClick: () => ctx.setCustomEnabled(t.name, !t.enabled)
            }, t.enabled ? '已上线' : '已下线')
          ])))
          : h('div', { class: 'hint' }, '（该技能暂无工具）'),
        // 说明文档：查看 / 编辑 SKILL.md
        h('div', { class: 'skill-doc' }, [
          h('div', { class: 'row' }, [
            h('button', { onClick: () => ctx.toggleSkillDoc(name) }, ctx.skillDocOpen[name] ? '收起说明文档' : '查看/编辑说明文档'),
            ctx.skillDocOpen[name] && ctx.skillDocText[name] != null && !ctx.skillDocEditing[name]
              ? h('button', { onClick: () => ctx.editSkillDoc(name) }, '编辑')
              : null
          ]),
          ctx.skillDocOpen[name] ? (
            ctx.skillDocEditing[name]
              ? h('div', { class: 'custom-edit' }, [
                h('textarea', {
                  value: ctx.skillDocEdit[name] || '',
                  onInput: (e) => { ctx.skillDocEdit[name] = e.target.value; }
                }),
                h('div', { class: 'row' }, [
                  h('button', { onClick: () => ctx.saveSkillDoc(name) }, '保存'),
                  h('button', { onClick: () => ctx.cancelSkillDoc(name) }, '取消')
                ])
              ])
              : h('pre', { class: 'skill-doc-view' }, ctx.skillDocText[name] == null ? '（加载中…）' : ctx.skillDocText[name])
          ) : null
        ])
      ]) : null
    ]);
  };
})();
