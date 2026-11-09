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
      // 记下本抽屉所在页面的地址与站点：上报消息、登记在线页面都要用它。
      // 为什么从应答里拿而不是自己读 location：抽屉跑在扩展 iframe 里，
      // location 指向 drawer.html，只有内容脚本知道宿主页面的真实地址。
      if (d.page_url) this.page_url = d.page_url;   // 记下宿主页地址，后续上线/取件都要用
      if (d.site_key) this.profileId = d.site_key;   // 记下站点 id，站点档案热更新依赖它
      this._postClientLog([{ tag: 'ext-版本', msg: '内容脚本已加载 build=' + (d.build || '(旧版无应答)') }]);
      // 显式上报上线：页面地址一到手就登记，不等轮询、不等超时。
      // 这样抽屉打开的瞬间手机端就能把消息投到本页，不会因为「还没登记」而落到别处。
      this.reportPageOnline();
      // 顺带拉一次卡片：上线同时把已积压的卡片取走
      this.pollExternalCards();
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
  /**
   * 显式上报本页已上线。
   *
   * 上线是事件而非状态推断：抽屉打开、拿到宿主页地址的这一刻就通知后端，
   * 后端立即把本页列入在线列表。不设任何延迟或超时窗口。
   */
  M.reportPageOnline = function () {
    if (!this.page_url) return;                                    // 地址未知则无从上报
    this._reportPageState('/api/pages/online');                     // 走统一上报
  };

  /**
   * 显式上报本页已下线。
   *
   * 抽屉关闭、页面卸载时调用。后端据此立即把本页移出在线列表，
   * 之后发往该站点的消息会明确报「无在线页面」，而不是悄悄改投别处。
   */
  M.reportPageOffline = function () {
    if (!this.page_url) return;                                    // 地址未知则无从上报
    this._reportPageState('/api/pages/offline');                    // 走统一上报
  };

  /**
   * 上报页面上下线状态的统一实现。
   *
   * 用 fetch 的 keepalive 而非 apiFetch：下线常发生在页面卸载过程中，
   * 普通 XHR 会被浏览器中断，keepalive 保证请求能发出去。
   *
   * @param {string} path 接口路径（/api/pages/online 或 /api/pages/offline）
   */
  M._reportPageState = function (path) {
    const base = (this.config && this.config.flaskUrl) || '';       // 后端地址；初始化前为空
    if (!base) return;                                              // 地址未就绪则放弃（下次轮询会兜底登记）
    const url = String(base).replace(/\/+$/, '') + path;            // 拼出完整地址，去掉尾部斜杠
    const page = this.page_url;                                     // 本页地址快照，避免异步期间被改
    try {
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page: page }),
        keepalive: true                                             // 卸载阶段也能发出
      }).catch(function () { /* 上报失败不影响页面行为 */ });
    } catch (e) { /* 扩展上下文失效等：忽略 */ }
  };

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
