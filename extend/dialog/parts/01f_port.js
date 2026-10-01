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
   * 保存端口：先带新端口重启后端（不落盘），探到新端口通了才写配置文件。
   * 顺序刻意如此——文件最后写，避免写错端口把服务写死。
   */
  M.savePort = async function () {
    const port = parseInt(this.config.flaskPort, 10);
    if (!port || port < 1 || port > 65535) { this.toast('端口非法'); return; }
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
    // 3) 探到了才写进 config.yaml
    this.config.flaskUrl = base;
    try {
      await D.apiFetch(this, '/config', {
        method: 'POST', body: { flask: { port: port } }, lenientJson: true
      });
    } catch (e) { /* 写盘失败不致命，端口已生效 */ }
    await this.initBackend();
    this.toast('端口已切换为 ' + port + ' 并保存');
  };
})();
