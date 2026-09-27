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
  };

  /**
   * 保存指令：新增或修改。
   * 走独立接口而非 saveBridge —— 后者是全量覆盖，曾导致指令丢失。
   */
  M.saveBridgeCommand = async function () {
    const name = (this.bridgeNewCmdName || '').trim();
    const label = (this.bridgeNewCmdLabel || '').trim();
    const picked = this.bridgePicked;
    if (!name || !label) { this.toast('命令名与显示名必填'); return; }
    if (!name.startsWith('/')) { this.toast('命令名需以 / 开头'); return; }
    if (!picked || !picked.selector) { this.toast('请先选择要点击的元素'); return; }
    // 命令名去重（修改时排除自身）
    const dup = (this.bridgeCommands || []).some((c, i) =>
      i !== this.bridgeEditIdx && (c.name || '').toLowerCase() === name.toLowerCase());
    if (dup) { this.toast('该命令名已存在'); return; }
    const entry = {
      name: name, label: label,
      selector: picked.selector, page_url: picked.page_url || ''
    };
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
    this.bridgePicked = { selector: c.selector || '', page_url: c.page_url || '', tag: '' };
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
