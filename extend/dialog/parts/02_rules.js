// 模块：extend/dialog/parts/02_rules.js
// 用途：规则文件（rules/*.md）的读取与增删改，优先级设置。
//       AI 通过 list_rules / read_rule 按需读取这些规则。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /** 读取规则列表与规则目录；规则变动会影响 System Prompt，故随后重新生成。 */
  M.loadRules = async function () {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/rules', { headers: { 'Accept': 'application/json' } });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      this.rules = data.rules || [];
      this.rulesDir = data.rulesDir || '';
    } catch (e) {
      this.rules = [];
    }
    // 规则列表进入 System Prompt，规则变动后需重新生成
    this.systemPrompt = this.generateSystemPrompt();
  };

  /** 展开 / 收起某条规则。 */
  M.toggleRule = function (name) {
    this.rulesExpanded[name] = !this.rulesExpanded[name];
  };

  /** 设置规则读取优先级（乐观更新，失败回滚）。 */
  M.setRulePriority = async function (name, priority) {
    const r = this.rules.find((x) => x.name === name);
    const old = r ? r.priority : null;
    if (r) r.priority = priority;   // 乐观更新
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const resp = await fetch(base + '/rules/' + encodeURIComponent(name), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ priority: priority }),
      });
      const data = await resp.json();
      if (!data.ok) throw new Error(data.error);
      await this.loadRules();   // 优先级影响 System Prompt，重新生成
      this.toast('已设置优先级：' + name + ' → ' + priority);
    } catch (e) {
      if (r) r.priority = old;   // 回滚
      this.toast('设置优先级失败：' + e);
    }
  };

  /** 进入某条规则的编辑态，拉取完整内容。 */
  M.editRule = async function (name) {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/rules/' + encodeURIComponent(name), { headers: { 'Accept': 'application/json' } });
      const data = await r.json();
      if (!data.ok) throw new Error(data.error);
      this.rulesEdit[name] = data.content || '';
      this.rulesEditing[name] = true;
      this.rulesExpanded[name] = true;
      this.$forceUpdate();
    } catch (e) {
      this.toast('读取规则失败：' + e);
    }
  };

  /** 保存规则内容。 */
  M.saveRule = async function (name) {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/rules/' + encodeURIComponent(name), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: this.rulesEdit[name] || '' }),
      });
      const data = await r.json();
      if (!data.ok) throw new Error(data.error);
      this.rulesEditing[name] = false;
      await this.loadRules();
      this.toast('已保存规则：' + name);
    } catch (e) {
      this.toast('保存规则失败：' + e);
    }
  };

  /** 新建规则：校验命名后创建，并立即进入编辑态。 */
  M.createRule = async function () {
    const name = (this.newRuleName || '').trim();
    if (!/^[A-Za-z0-9_-]+$/.test(name)) { this.toast('规则名非法（仅字母、数字、下划线、连字符）'); return; }
    if (this.rules.some((x) => x.name === name)) { this.toast('规则已存在：' + name); return; }
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, content: '# ' + name + '\n\n' }),
      });
      const data = await r.json();
      if (!data.ok) throw new Error(data.error);
      this.newRuleName = '';
      await this.loadRules();
      await this.editRule(name);
      this.toast('已创建规则：' + name);
    } catch (e) {
      this.toast('创建规则失败：' + e);
    }
  };

  /** 删除规则（需二次确认）。 */
  M.removeRule = async function (name) {
    if (!confirm('确认删除规则 ' + name + '？此操作不可撤销。')) return;
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/rules/' + encodeURIComponent(name), { method: 'DELETE' });
      const data = await r.json();
      if (!data.ok) throw new Error('HTTP ' + r.status);
      await this.loadRules();
      this.toast('已删除规则：' + name);
    } catch (e) {
      this.toast('删除规则失败：' + e);
    }
  };
})();
