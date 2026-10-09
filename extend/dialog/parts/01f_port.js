// 模块：extend/dialog/parts/01f_port.js
// 用途：端口修改流程——探测新端口、以新端口启动新服务、探通后切换并退出旧服务。
// 从 01_backend.js 抽出，避免主文件超长。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 从地址字符串里解析端口；解析不到返回 NaN。
   * @param {string} s 形如 http://127.0.0.1:5006
   * @returns {number} 端口号
   */
  M.parsePort = function (s) {
    const m = /:(\d+)\b/.exec(s || '');
    return m ? parseInt(m[1], 10) : NaN;
  };

  /**
   * 探测某端口是否已有服务在监听：通了返回其 base 地址，超时返回 null。
   * 每 500ms 试一次，直到 timeoutMs。
   * @param {number} port 端口
   * @param {number} timeoutMs 总超时（毫秒）
   * @returns {Promise<string|null>} base 地址或 null
   */
  M.probePort = async function (port, timeoutMs) {
    const base = 'http://127.0.0.1:' + port;
    const deadline = Date.now() + (timeoutMs || 25000);
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
   * 保存并重启：按「比对 → 启动新服务 → 探测 → 探通才切换 → 超时还原」流程。
   * 处理期间把 portSwitching 置真，界面据此禁用输入框与按钮，禁止再改端口。
   */
  M.savePort = async function () {
    if (this.portSwitching) return;   // 正在切换，忽略重复点击
    // 输入框草稿；为空时用当前实际地址
    const draft = this.flaskUrlDraft || this.config.flaskUrl || '';
    const newPort = this.parsePort(draft);
    if (!newPort || newPort < 1 || newPort > 65535) {
      this.toast('请填写形如 http://127.0.0.1:端口的地址');
      return;
    }
    // 1) 与旧接口比对：端口一致则什么都不做
    const curPort = this.parsePort(this.config.flaskUrl);
    if (newPort === curPort) {
      this.toast('端口未变化，无需重启');
      this.flaskUrlDraft = '';   // 还原输入框到回显态
      return;
    }
    // 2) 锁死：处理期间禁止改端口
    this.portSwitching = true;
    this.toast('正在以新端口 ' + newPort + ' 启动新服务…');
    try {
      // 3) 请求后端启动新服务（此请求会因旧进程稍后退出而中断，属正常）
      try {
        await D.apiFetch(this, '/config/restart-port', {
          method: 'POST', body: { port: newPort }, lenientJson: true
        });
      } catch (e) { /* 连接中断属预期，忽略 */ }
      // 4) 不断探测新端口
      const base = await this.probePort(newPort, 25000);
      if (!base) {
        // 5a) 超时未通：还原输入框内容并提示；实际连接始终未变，服务仍在旧端口
        this.flaskUrlDraft = '';
        this.toast('新端口 ' + newPort + ' 未在时限内就绪，已还原；服务仍在旧端口');
        return;
      }
      // 5b) 探通：替换所有旧接口——切换实际连接地址
      this.config.flaskUrl = base;
      this.flaskUrlDraft = '';
      try { chrome.storage.local.set({ aiMirrorFlaskUrl: base }); } catch (e) { /* 忽略 */ }
      // 把端口写进 runtime.yaml（此后重启也读得到）
      try {
        await D.apiFetch(this, '/config', {
          method: 'POST', body: { flask: { port: newPort } }, lenientJson: true
        });
      } catch (e) { /* 写盘失败不致命，端口已生效 */ }
      await this.initBackend();
      this.toast('端口已切换为 ' + newPort);
    } finally {
      this.portSwitching = false;
    }
  };
})();
