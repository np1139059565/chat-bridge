// 模块：extend/dialog/parts/01b_bridge.js
// 用途：远程桥接（QQ ↔ 网页 AI）的全部前端逻辑。
//       从 01_backend.js（后端交互）与 05_messages.js（消息处理）中抽出，
//       使各文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 说明：这些方法原本挂在 D.methods 上，抽出后仍挂在同一命名空间，
//       调用方式不变（app.js 装配时统一并入 Vue 实例）。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 加载远程桥接配置与状态。
   * 凭证（AppID / AppSecret）从后端读回，供设置页回填。
   */
  M.loadBridge = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/config', {
        headers: { 'Accept': 'application/json' }
      });
      const cfg = data.config || {};
      const st = data.status || {};
      this.bridgeEnabled = !!cfg.enabled;
      this.bridgeAppId = cfg.app_id || '';
      this.bridgeAppSecret = cfg.app_secret || '';
      this.bridgePush = Object.assign({ user: true, tool: true, ai: true, thinking: false }, cfg.push || {});
      this.bridgeCommands = cfg.commands || [];
      this.bridgeConnected = !!st.connected;
    } catch (e) {
      // 桥接未启用 / 后端不可达：保持默认值，不打扰用户
      this.bridgeConnected = false;
    }
  };

  /**
   * 保存远程桥接配置：写回后端并重启桥接。
   * 凭证或开关变化需要重建长连接，因此保存后后端会自动重启。
   */
  M.saveBridge = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/config', {
        method: 'POST',
        body: {
          enabled: this.bridgeEnabled,
          app_id: this.bridgeAppId,
          app_secret: this.bridgeAppSecret,
          push: this.bridgePush,
          commands: this.bridgeCommands
        }
      });
      const st = data.status || {};
      this.bridgeConnected = !!st.connected;
      this.toast(this.bridgeEnabled ? '桥接已保存并重启' : '桥接已关闭');
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

  /** 切换某类消息的推送开关（用户 / 工具 / AI / 思考）。 */
  M.toggleBridgePush = function (kind) {
    this.bridgePush[kind] = !this.bridgePush[kind];
    this.saveBridge();
  };

  /** 新增一条 QQ 指令。 */
  M.addBridgeCommand = function () {
    const c = this.bridgeNewCmd;
    if (!c.name || !c.label) { this.toast('命令名与显示名必填'); return; }
    this.bridgeCommands.push({
      name: c.name, label: c.label, action: c.action || '', arg: c.arg || ''
    });
    this.bridgeNewCmd = { name: '', label: '', action: '', arg: '' };
    this.saveBridge();
  };

  /** 删除一条 QQ 指令。 */
  M.removeBridgeCommand = function (idx) {
    this.bridgeCommands.splice(idx, 1);
    this.saveBridge();
  };

  /**
   * 把当前可见切片上报给远程桥接层（QQ ↔ 网页 AI）。
   *
   * 注意：上报的是**全量可见切片**，不是「本轮新增」——
   * sendPage 每次都全量推送，桥接层自己与「已推送集合」比对取差集。
   * 抽屉在这里只是「小喇叭」：把看见的消息喊给桥接层，
   * 分类、去重、往 QQ 推全由桥接层完成。抽屉不用懂 QQ。
   *
   * 只推 generate 来源：那是「AI 刚说完新话」的时刻；
   * scroll / switch / manual 都是用户回看历史或切上下文，不该推。
   * @param {string} [reason] 触发来源
   */
  M.reportToBridge = function (reason) {
    // 只推 generate：其余来源是回看 / 切换，推了会刷屏
    if (reason !== 'generate') return;
    // 面板未打开时不推：关闭抽屉就代表用户此刻不需要远程工作
    if (!this.panelVisible) return;
    const conv = this.curConv || {};
    const tree = conv.msgTree || {};
    const messages = [];
    (conv.visibleKeys || []).forEach((k) => {
      const node = tree[k];
      if (!node || node.deleted) return;
      const id = window.AIMirrorDomUtils.messageFingerprint(node);
      messages.push({ id: id, role: node.role, blocks: node.blocks || [] });
    });
    if (!messages.length) return;
    // 静默上报：失败不打扰用户，桥接层没开时后端直接返回 0
    try {
      D.apiFetch(this, '/api/bridge/report', {
        method: 'POST',
        body: { conversationId: this.activeConv, messages: messages }
      }).catch(function () { /* 桥接未启用时忽略 */ });
    } catch (e) { /* 忽略 */ }
  };
})();
