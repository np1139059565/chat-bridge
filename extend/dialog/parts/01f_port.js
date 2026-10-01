// 模块：extend/dialog/parts/01f_port.js
// 用途：端口修改流程——探测新端口、以新端口重启后端、探通后写配置。
// 从 01_backend.js 抽出，避免主文件超长。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 探测某端口是否已有后端在监听：通了返回其 base 地址，超时返回 null。
   * 每 500ms 试一次，直到 timeoutMs。
   * @param {number} port 端口
   * @param {number} timeoutMs 总超时（毫秒）
   * @returns {Promise<string|null>} base 地址或 null
   */
  M.probePort = async function (port, timeoutMs) {
    const base = 'http://127.0.0.1:' + port;
    const deadline = Date.now() + (timeoutMs || 20000);
    while (Date.now() < deadline) {
      try {
        const r = await fetch(base + '/config', { headers: { 'Accept': 'application/json' } });
        if (r.ok) return base;
      } catch (e) { /* 还没起来，继续等 */ }
      await new Promise((res) => setTimeout(res, 500));
    }
    return null;
  };

  /**
   * 保存端口：从「工具服务地址」输入框解析端口，带新端口滚动重启后端
   * （先起新、探通再退旧），探到新端口通了才写配置文件。
   * 顺序刻意如此——文件最后写，避免写错端口把服务写死。
   */
  M.savePort = async function () {
    // 从输入框草稿里解析端口；草稿为空时退回当前实际地址。
    const src = this.flaskUrlDraft || this.config.flaskUrl || '';
    const m = /:(\d+)\b/.exec(src);
    const port = m ? parseInt(m[1], 10) : NaN;
    if (!port || port < 1 || port > 65535) { this.toast('请填写形如 http://127.0.0.1:端口的地址'); return; }
    // 1) 让后端带新端口重启（此请求会因进程重启而中断，属正常）
    this.toast('正在以新端口 ' + port + ' 重启服务…');
    try {
      await D.apiFetch(this, '/config/restart-port', {
        method: 'POST', body: { port: port }, lenientJson: true
      });
    } catch (e) { /* 重启掐断连接，忽略 */ }
    // 2) 探测新端口，直到通或超时
    const base = await this.probePort(port, 20000);
    if (!base) {
      this.toast('新端口 ' + port + ' 未在时限内就绪，服务可能未起来，请检查');
      return;
    }
    // 3) 探到了才写进 config.yaml，并把新地址落盘，
    // 避免后续探测优先命中浏览器里存的旧地址。
    // 此刻才切换实际连接地址——探通之前，连接地址始终保持旧值。
    this.config.flaskUrl = base;
    this.flaskUrlDraft = '';   // 清空草稿，输入框回到回显实际地址的状态
    try { chrome.storage.local.set({ aiMirrorFlaskUrl: base }); } catch (e) { /* 忽略 */ }
    try {
      await D.apiFetch(this, '/config', {
        method: 'POST', body: { flask: { port: port } }, lenientJson: true
      });
    } catch (e) { /* 写盘失败不致命，端口已生效 */ }
    await this.initBackend();
    this.toast('端口已切换为 ' + port + ' 并保存');
  };
})();
