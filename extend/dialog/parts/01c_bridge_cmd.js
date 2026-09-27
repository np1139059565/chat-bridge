// 模块：extend/dialog/parts/01c_bridge_cmd.js
// 用途：远程桥接的自定义指令管理（新增 / 修改 / 删除）与元素选择入口。
//       从 01b_bridge.js 抽出，避免该文件过长。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 为什么改走独立接口：saveBridge 是全量覆盖式保存，曾因抽屉重建时
// bridgeCommands 暂为空数组、用户碰了开关就把指令全清掉。
// 指令的增删改改走 /api/bridge/commands 独立接口，根治该问题。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /** 进入元素选择模式：请求内容脚本开始选元素。 */
  M.startPickElement = function () {
    this.bridgePicking = true;
    window.parent.postMessage({ type: 'picker_start' }, '*');
    this.toast('请在页面上点击要绑定的元素（Esc 取消）');
  };

  /** 停止元素选择模式。 */
  M.stopPickElement = function () {
    this.bridgePicking = false;
    window.parent.postMessage({ type: 'picker_stop' }, '*');
  };

  /** 复位指令录入表单。 */
  M._resetCmdForm = function () {
    this.bridgeNewCmdName = '';
    this.bridgeNewCmdLabel = '';
    this.bridgePicked = null;
    this.bridgeEditIdx = null;
    this.bridgeNewCmdIsCombo = false;
    this.bridgeNewCmdKeepCollect = false;   // 内部标记，不在界面暴露
    this.bridgeNewCmdSteps = '';
    this.bridgeNewCmdInterval = '1';
  };

  /**
   * 保存指令：新增或修改。
   * 走独立接口而非 saveBridge —— 后者是全量覆盖，曾导致指令丢失。
   */
  M.saveBridgeCommand = async function () {
    const name = (this.bridgeNewCmdName || '').trim();
    const label = (this.bridgeNewCmdLabel || '').trim();
    const isCombo = !!this.bridgeNewCmdIsCombo;
    const picked = this.bridgePicked;
    if (!name || !label) { this.toast('命令名与显示名必填'); return; }
    if (!name.startsWith('/')) { this.toast('命令名需以 / 开头'); return; }
    // 两类指令各自的必填项：组合要步骤，点击要选择器
    let steps = [];
    if (isCombo) {
      steps = (this.bridgeNewCmdSteps || '').split('\n')
        .map((s) => s.trim()).filter(Boolean);
      if (!steps.length) { this.toast('请填写至少一条步骤指令'); return; }
    } else if (!picked || !picked.selector) {
      this.toast('请先选择要点击的元素');
      return;
    }
    // 命令名去重与子指令校验统一交给后端（validate_command）。
    // 编辑既有指令时保留它原有的 collect 标记（内置 /md 靠它工作），
    // 但新增界面不再暴露这个类型——用户只需理解「点击」与「组合」。
    let interval = parseFloat(this.bridgeNewCmdInterval);
    if (!(interval > 0)) interval = 1;
    const keepCollect = this.bridgeEditIdx !== null && !!this.bridgeNewCmdKeepCollect;
    let entry;
    if (isCombo) {
      entry = { name: name, label: label, steps: steps, interval: interval };
    } else {
      entry = {
        name: name, label: label,
        selector: picked.selector, page_url: picked.page_url || ''
      };
      if (keepCollect) entry.collect = true;
    }
    try {
      const data = await D.apiFetch(this, '/api/bridge/commands', {
        method: 'POST',
        body: { index: this.bridgeEditIdx, entry: entry }
      });
      if (!data.success) throw new Error(data.error || '保存失败');
      this.bridgeCommands = data.commands || [];
      this.toast(this.bridgeEditIdx === null ? ('已添加指令：' + name) : ('已修改指令：' + name));
      this._resetCmdForm();
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

  /**
   * 编辑一条已有指令：把它的内容填进表单，供修改命令名 / 显示名 / 选择器。
   * @param {number} idx 指令下标
   */
  M.editBridgeCommand = function (idx) {
    const c = (this.bridgeCommands || [])[idx];
    if (!c) return;
    this.bridgeEditIdx = idx;
    this.bridgeNewCmdName = c.name || '';
    this.bridgeNewCmdLabel = c.label || '';
    // 回填：组合填步骤、点击填选择器。
    // collect 标记只记下来备用（编辑内置 /md 时保留它），不在界面暴露。
    const isCombo = !!(c.steps && c.steps.length);
    this.bridgeNewCmdIsCombo = isCombo;
    this.bridgeNewCmdKeepCollect = !!c.collect;
    this.bridgeNewCmdSteps = isCombo ? (c.steps || []).join('\n') : '';
    this.bridgeNewCmdInterval = isCombo ? String(c.interval || 1) : '1';
    this.bridgePicked = isCombo
      ? null
      : { selector: c.selector || '', page_url: c.page_url || '', tag: '' };
    this.toast('正在修改：' + (c.name || ''));
  };

  /** 取消编辑，复位表单。 */
  M.cancelEditBridgeCommand = function () {
    this._resetCmdForm();
  };

  /** 删除一条 QQ 指令（走独立接口）。 */
  M.removeBridgeCommand = async function (idx) {
    try {
      const data = await D.apiFetch(this, '/api/bridge/commands', {
        method: 'DELETE',
        body: { index: idx }
      });
      if (!data.success) throw new Error(data.error || '删除失败');
      this.bridgeCommands = data.commands || [];
      this.toast('已删除指令');
      this._resetCmdForm();
    } catch (e) {
      this.toast('删除失败：' + e);
    }
  };
})();
