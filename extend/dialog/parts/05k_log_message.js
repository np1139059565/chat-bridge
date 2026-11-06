// 模块：extend/dialog/parts/05k_log_message.js
// 用途：处理内容脚本上报的日志相关消息——构建版本应答与诊断日志。
//
// 拆分原因：这些逻辑只服务日志上报，与消息树、卡片无关；
// 原先内联在 05_messages.js 的 onPageMessage 里，把该文件撑破了行数上限。
//
// 为什么由抽屉代发：内容脚本跑在网页的源里，请求本地 HTTP 服务会被
// 混合内容策略拦截；抽屉是扩展页面，不受该限制——工具调用正是经这条
// 通道到达后端的，已被验证可行。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 统一处理日志相关消息。
   *
   * @param {Object} d 消息体
   * @returns {boolean} 是否已处理（true 则调用方直接返回）
   */
  M._handleLogMessage = function (d) {
    // 构建应答：收得到说明本页内容脚本是新版，收不到则是旧版
    //（旧版没有应答代码，常见于「只刷新页面、没重载扩展」）。
    if (d.type === 'pong_content') {
      this._postClientLog([{ tag: 'ext-版本', msg: '内容脚本已加载 build=' + (d.build || '(旧版无应答)') }]);
      return true;
    }
    if (d.type !== 'ext_log') return false;
    // 内容脚本的诊断日志
    const items = d.batch || [];
    if (items.length) this._postClientLog(items);
    return true;
  };

  /**
   * 向后端上报一批日志。
   *
   * 抽屉初始化是异步的（discoverFlask 要探测端口），在此之前 flaskUrl 为空。
   * 而内容脚本在页面刷新时就立刻开始发日志，会撞在这个窗口期。
   * 此时不能丢——先存起来，等 initBackend 完成后统一补发（见 flushPendingExtLogs）。
   *
   * @param {Array} items 日志数组
   */
  M._postClientLog = function (items) {
    if (!items || !items.length) return;
    if (!this.config || !this.config.flaskUrl) {
      this.pendingExtLogs = (this.pendingExtLogs || []).concat(items);
      return;
    }
    D.apiFetch(this, '/api/web/client_log', { method: 'POST', body: items })
      .catch(function () { /* 静默 */ });
  };
})();
