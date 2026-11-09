// 模块：extend/dialog/parts/00a_api.js
// 用途：统一的后端请求辅助 D.apiFetch —— 拼地址、按需序列化 JSON 请求体、
//       检查响应状态、解析 JSON；非 2xx 时把后端响应体里的具体错误透传出来。
// 依赖：00_data.js（须在其后加载，本文件挂到已存在的 window.AIMirrorDialog）。
//
// 拆出原因：原在 00_data.js 内，加入「错误透传」后该文件超出行数上限，
// 按工程拆分约定独立成文件。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;

  /**
   * 统一的后端请求辅助：拼地址、按需序列化 JSON 请求体、检查响应状态、解析 JSON。
   *
   * 失败处理：非 2xx 时不再只抛「HTTP 400」——会尝试读取响应体里的
   * error / message 字段并拼进错误消息，让调用方看到后端的真实原因
   * （曾因丢弃响应体导致「只看到 400、不知为何」）。
   * @param {Object} ctx Vue 实例（读取 config.flaskUrl）
   * @param {string} path 接口路径
   * @param {Object} [options] fetch 选项；额外支持 lenientJson（响应非 JSON 时返回空对象）
   * @returns {Promise<Object>} 解析后的 JSON
   */
  D.apiFetch = async function (ctx, path, options) {
    const opts = Object.assign({}, options || {});
    const commit = !!opts.__commit;
    delete opts.__commit;
    const lenientJson = !!opts.lenientJson;
    delete opts.lenientJson;
    const base = String((ctx && ctx.config && ctx.config.flaskUrl) || '').replace(/[\/]+$/, '');
    const method = String(opts.method || 'GET').toUpperCase();
    const draftOn = !!ctx && ctx.configDraftMode !== false && !commit;

    // v3 全区块草稿：命中受管配置写端点时不发请求，只登记待覆盖写入。
    if (draftOn && typeof D.matchConfigBlock === 'function') {
      const wb = D.matchConfigBlock(path, method, true);
      if (wb && (!wb.guard || wb.guard(opts.body))) {
        await D.queuePendingWrite(ctx, wb, path, method, opts.body);
        return { ok: true, success: true, draft: true };
      }
    }

    opts.headers = Object.assign({}, opts.headers || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    const r = await fetch(base + path, opts);
    if (!r.ok) {
      let detail = '';
      try {
        const body = await r.json();
        if (body) detail = body.error || body.message || '';
      } catch (e) { }
      throw new Error('HTTP ' + r.status + (detail ? ('：' + detail) : ''));
    }
    let data;
    if (lenientJson) data = await r.json().catch(function () { return {}; });
    else data = await r.json();
    // 读端点：把待覆盖的本地改动合并进响应，避免 setter 重读把 UI 冲回服务端旧值。
    if (draftOn && typeof D.applyPendingToRead === 'function') {
      const rb = D.matchConfigBlock(path, method, false);
      if (rb) data = D.applyPendingToRead(ctx, path, data, rb);
    }
    return data;
  };
})();
