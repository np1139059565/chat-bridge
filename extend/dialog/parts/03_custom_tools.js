// 模块：extend/dialog/parts/03_custom_tools.js
// 用途：自定义工具（来自标准 skill 的 tool.json）的读取、上下线、编辑、
//       目录扫描与安装。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /** 读取已安装的自定义工具列表与可扫描的默认根目录。 */
  M.loadCustomTools = async function () {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/custom_tools', { headers: { 'Accept': 'application/json' } });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const data = await r.json();
      this.customTools = data.tools || [];
      this.scanRoots = data.scanRoots || [];
    } catch (e) {
      this.customTools = [];
    }
  };

  /** 展开 / 收起某个自定义工具。 */
  M.toggleCustom = function (name) {
    this.customExpanded[name] = !this.customExpanded[name];
  };

  /** 自定义工具上 / 下线（乐观更新，失败回滚）；上线影响 System Prompt。 */
  M.setCustomEnabled = async function (name, enabled) {
    const t = this.customTools.find((x) => x.name === name);
    if (t) t.enabled = enabled;  // 乐观更新
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/custom_tools/' + encodeURIComponent(name), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: enabled }),
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      await this.loadCustomTools();
      await this.fetchTools();  // 上线影响 System Prompt
      this.toast(enabled ? ('已上线：' + name) : ('已下线：' + name));
    } catch (e) {
      if (t) t.enabled = !enabled;
      this.toast('保存失败：' + e);
    }
  };

  /** 删除自定义工具（需二次确认）；删除影响工具列表与技能说明段落。 */
  M.removeCustom = async function (name) {
    if (!confirm('确认删除自定义工具 ' + name + '？此操作不可撤销。')) return;
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/custom_tools/' + encodeURIComponent(name), { method: 'DELETE' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      await this.loadCustomTools();
      await this.fetchTools();   // 删除影响工具列表与技能说明段落
      this.toast('已删除：' + name);
    } catch (e) {
      this.toast('删除失败：' + e);
    }
  };

  /** 选择 skill 父目录（依赖 chrome.fileSystem，不可用时提示手动输入）。 */
  M.pickDir = function () {
    const fs = (window.chrome && chrome.fileSystem) || null;
    if (!fs || !fs.chooseEntry) {
      this.toast('当前环境不支持目录选择，请手动输入路径');
      return;
    }
    fs.chooseEntry({ type: 'openDirectory' }, (entry) => {
      if (chrome.runtime.lastError || !entry) return;
      fs.getDisplayPath(entry, (p) => {
        if (p) { this.skillScanDir = p; this.scanSkills(); }
      });
    });
  };

  /** 扫描指定目录下的可安装 skill。 */
  M.scanSkills = async function () {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/custom_tools/scan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dir: this.skillScanDir }),
      });
      const data = await r.json();
      if (!data.ok) throw new Error(data.error);
      this.scanResults = data.skills || [];
    } catch (e) {
      this.toast('扫描失败：' + e);
    }
  };

  /** 用默认根目录扫描。 */
  M.scanDefaults = async function () {
    if (this.scanRoots && this.scanRoots.length) this.skillScanDir = this.scanRoots[0];
    await this.scanSkills();
  };

  /** 安装指定 skill 中的某个工具，并即时更新扫描列表中的安装态。 */
  M.installSkill = async function (dir, name) {
    try {
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/custom_tools/install', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dir: dir, names: [name] }),
      });
      const data = await r.json();
      if (!data.ok) throw new Error(data.error);
      await this.loadCustomTools();
      await this.fetchTools();   // 安装后刷新工具列表与技能说明段落
      // 即时更新扫描列表中的安装态，无需重新扫描
      this.scanResults.forEach((skill) => {
        (skill.tools || []).forEach((ts) => {
          if (ts.name === name) ts.installed = true;
        });
      });
      this.toast('已安装：' + name);
    } catch (e) {
      this.toast('安装失败：' + e);
    }
  };

  /** 进入某个自定义工具的编辑态，把可编辑字段序列化为 JSON。 */
  M.editCustom = function (name) {
    const t = this.customTools.find((x) => x.name === name);
    if (!t) return;
    this.customEdit[name] = JSON.stringify({
      description: t.description,
      arg_style: t.arg_style,
      interpreter: t.interpreter,
      parameters: t.parameters,
    }, null, 2);
    this.customEditing[name] = true;
    this.$forceUpdate();
  };

  /** 保存自定义工具编辑内容（校验 description 与参数结构）。 */
  M.saveCustom = async function (name) {
    try {
      const obj = JSON.parse(this.customEdit[name]);
      if (typeof obj.description !== 'string' || !obj.description.trim()) {
        throw new Error('description 不能为空');
      }
      obj.parameters = (obj.parameters || []).map((p) => ({
        name: String(p.name || ''),
        type: p.type || 'string',
        required: !!p.required,
        description: String(p.description || ''),
      }));
      const base = this.config.flaskUrl.replace(/\/+$/, '');
      const r = await fetch(base + '/custom_tools/' + encodeURIComponent(name), {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: obj.description,
          arg_style: obj.arg_style,
          interpreter: obj.interpreter,
          parameters: obj.parameters,
        }),
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      await this.loadCustomTools();
      this.customEditing[name] = false;
      this.toast('已保存：' + name);
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };
})();
