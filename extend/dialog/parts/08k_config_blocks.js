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
      } },
    { id: 'general', label: '通用配置', write: null, read: null },
    { id: 'site_profiles', label: '网页 AI 站点配置', write: null, read: null }
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

  /** 把待覆盖写入的 body 统一解析成对象；字符串按 JSON 解析，失败返回空。 */
  function parseWriteBody(w) {
    let body = w && w.body;
    if (typeof body === 'string') {
      try { body = JSON.parse(body); } catch (e) { return null; }
    }
    return (body && typeof body === 'object' && !Array.isArray(body)) ? body : null;
  }

  /** 从 /skills/<name>/enabled 取技能名；路径不匹配返回空串。 */
  function skillNameOf(w) {
    const m = /^\/skills\/([^/]+)\/enabled/.exec(String((w && w.path) || ''));
    return m ? decodeURIComponent(m[1]) : '';
  }

  /** 从 /custom_tools/<name> 取工具名；路径不匹配返回空串。 */
  function toolNameOf(w) {
    const m = /^\/custom_tools\/([^/]+)/.exec(String((w && w.path) || ''));
    return m ? decodeURIComponent(m[1]) : '';
  }

  /**
   * 技能块待覆盖写入合并到管理视图数组行。
   * 每条写入只改同名技能行的开关、其工具开关与上线计数，不向顶层挂字段。
   */
  D.applySkillsPending = function (data, writes) {
    if (!data || !Array.isArray(data.skillsManage)) return data;
    writes.forEach(function (w) {
      const name = skillNameOf(w);
      const body = parseWriteBody(w);
      if (!name || !body || typeof body.enabled !== 'boolean') return;
      const on = body.enabled;
      data.skillsManage = data.skillsManage.map(function (s) {
        if (s.name !== name) return s;
        const row = Object.assign({}, s, { enabled: on });
        if (Array.isArray(s.tools)) {
          row.tools = s.tools.map(function (t) { return Object.assign({}, t, { enabled: on }); });
          row.enabled_count = on ? row.tools.length : 0;
        }
        return row;
      });
    });
    return data;
  };

  /**
   * 自定义工具块待覆盖写入合并到工具数组行。
   * 每条写入只改同名工具行；删除类写入没有 body，保持原列表。
   */
  D.applyCustomToolsPending = function (data, writes) {
    if (!data || !Array.isArray(data.tools)) return data;
    writes.forEach(function (w) {
      const name = toolNameOf(w);
      const body = parseWriteBody(w);
      if (!name || !body) return;
      data.tools = data.tools.map(function (t) {
        return t.name === name ? Object.assign({}, t, body) : t;
      });
    });
    return data;
  };

  /**
   * 把该读端点所属区块的全部待覆盖写入合并进 GET 响应。
   * 数组型响应（技能管理视图、自定义工具列表）按名称逐行合并；
   * 其余区块沿用通用形状合并，保持既有端点行为。
   */
  D.applyPendingToRead = function (ctx, path, data, block) {
    const cache = ctx && ctx.configCache;
    const list = cache && cache.pending;
    if (!list || !list.length) return data;
    const writes = [];
    for (let i = 0; i < list.length; i++) {
      if (block && list[i].block === block.id) writes.push(list[i]);
      else if (!block && list[i].path === path) writes.push(list[i]);
    }
    if (!writes.length) return data;
    let out = data;
    if (out && typeof out === 'object') {
      try { out = JSON.parse(JSON.stringify(out)); } catch (e) { return data; }
    }
    if (block && block.id === 'skills') return D.applySkillsPending(out, writes);
    if (block && block.id === 'custom_tools') return D.applyCustomToolsPending(out, writes);
    let w = null;
    for (let i = 0; i < list.length; i++) if (list[i].path === path) w = list[i];
    if (!w && block) {
      for (let i = 0; i < list.length; i++) if (list[i].block === block.id) w = list[i];
    }
    if (!w) return out;
    const body = parseWriteBody(w);
    if (!body) return out;
    return D.mergeIntoShape(out, body);
  };
})();
