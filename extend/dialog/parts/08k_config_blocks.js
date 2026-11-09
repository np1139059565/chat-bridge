// 模块：受管配置区块注册表（方案 v3 扩展）
// 后端 GET /config 只装一份母版；远程桥接 / 微信 / 企业微信 / 投递策略 /
// 技能 / 规则 / 自定义工具 / 指令各自走独立端点。此处登记为「受管配置区块」，
// 由 00a_api.js 统一拦截写操作进草稿、读响应合并本地改动。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;

  D.CONFIG_BLOCKS = [
    { id: 'bridge', label: '远程桥接 / 投递策略',
      write: /^\/api\/bridge\/config/, read: /^\/api\/bridge\/config/ },
    { id: 'weixin', label: '微信通道',
      write: /^\/api\/bridge\/weixin\/config/, read: /^\/api\/bridge\/weixin\/(config|status)/ },
    { id: 'wecom', label: '企业微信通道',
      write: /^\/api\/bridge\/wecom\/config/, read: /^\/api\/bridge\/wecom\/(config|status)/ },
    { id: 'skills', label: '技能',
      write: /^\/skills\/[^/]+\/enabled/, read: /^\/prompt_sections/ },
    { id: 'rules', label: '规则',
      write: /^\/rules(\/|\?|$)/, read: /^\/rules(\/|\?|$)/ },
    { id: 'custom_tools', label: '自定义工具',
      write: /^\/custom_tools\/(?!scan|install)[^/]+/, read: /^\/custom_tools$/ },
    { id: 'commands', label: '指令',
      write: /^\/api\/bridge\/commands/, read: /^\/api\/bridge\/commands/,
      guard: function (body) {
        if (!body || typeof body !== 'object') return false;
        // 下发 / 执行类请求带这些字段，不是配置保存，必须放行。
        return !(body.action || body.exec || body.command_id || body.run);
      } }
  ];

  D.matchConfigBlock = function (path, method, isWrite) {
    const m = String(method || 'GET').toUpperCase();
    if (isWrite) {
      if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') return null;
    } else if (m !== 'GET') return null;
    for (let i = 0; i < D.CONFIG_BLOCKS.length; i++) {
      const b = D.CONFIG_BLOCKS[i];
      const re = isWrite ? b.write : b.read;
      if (re && re.test(path)) return b;
    }
    return null;
  };

  /** 把待覆盖的 body 合并进 GET 响应；顶层命中多数则顶层合，否则找子对象合。 */
  D.mergeIntoShape = function (backend, body) {
    if (!backend || typeof backend !== 'object' || Array.isArray(backend)) return backend;
    if (!body || typeof body !== 'object' || Array.isArray(body)) return backend;
    const keys = Object.keys(body);
    if (!keys.length) return backend;
    const half = Math.ceil(keys.length / 2);
    let topHit = 0;
    keys.forEach(function (k) { if (k in backend) topHit++; });
    if (topHit >= half) return Object.assign({}, backend, body);
    const bk = Object.keys(backend);
    for (let i = 0; i < bk.length; i++) {
      const v = backend[bk[i]];
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        let hit = 0;
        keys.forEach(function (k) { if (k in v) hit++; });
        if (hit >= half) {
          const out = Object.assign({}, backend);
          out[bk[i]] = Object.assign({}, v, body);
          return out;
        }
      }
    }
    return Object.assign({}, backend, body);
  };

  D.applyPendingToRead = function (ctx, path, data, block) {
    const cache = ctx && ctx.configCache;
    const list = cache && cache.pending;
    if (!list || !list.length) return data;
    let w = null;
    for (let i = 0; i < list.length; i++) if (list[i].path === path) w = list[i];
    if (!w && block) {
      for (let i = 0; i < list.length; i++) if (list[i].block === block.id) w = list[i];
    }
    if (!w) return data;
    let body = w.body;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch (e) { return data; }
    }
    return D.mergeIntoShape(data, body);
  };
})();
