// 模块：配置本地缓存与差异计算（方案 v3：差异可视化 + 人工确认）
//
// 设计：后端只留一份母版；浏览器按站点分键存一份全量 GET /config 快照（D3 全存）。
// 刷新只更新「后端快照」，绝不覆盖本地缓存/草稿；逐字段比出不一致供 UI 标色。
// 不设基准快照（N1）：本地与后端直接比，自己改的也会标色，点【还原】会擦掉该项。
// 所有函数都是纯函数或 Promise，不依赖 Vue / DOM，可独立单测。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const PREFIX = 'aiMirrorConfigCache_';
  const NL = String.fromCharCode(10);   // 避免多层转义：字面换行由 Python 写入会破坏 JS 字符串
  const MEM = Object.create(null);      // chrome.storage 不可用时的内存降级

  D.configCacheKey = function (siteKey) {
    return PREFIX + String(siteKey || 'unknown-site');
  };

  function localStore() {
    try {
      if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
        return chrome.storage.local;
      }
    } catch (e) { /* node / 非扩展环境 */ }
    return null;
  }

  D.configCacheGet = function (siteKey) {
    const key = D.configCacheKey(siteKey);
    const s = localStore();
    if (!s) return Promise.resolve(MEM[key] || null);
    return new Promise(function (res) {
      try { s.get([key], function (r) { res((r && r[key]) || MEM[key] || null); }); }
      catch (e) { res(MEM[key] || null); }
    });
  };

  D.configCacheSet = function (siteKey, cfg) {
    const key = D.configCacheKey(siteKey);
    MEM[key] = cfg;
    const s = localStore();
    if (!s) return Promise.resolve(true);
    return new Promise(function (res) {
      try { s.set({ [key]: cfg }, function () { res(true); }); }
      catch (e) { res(false); }
    });
  };

  /** 公共配置 = 除 profiles 外的全部顶层键。 */
  D.configPublic = function (cfg) {
    const out = {};
    Object.keys(cfg || {}).forEach(function (k) {
      if (k !== 'profiles') out[k] = cfg[k];
    });
    return out;
  };

  /** 数组 / 布尔 / 按行文本统一成可比较文本；仅用于标色，不改实际数据。 */
  D.configFieldToText = function (val) {
    if (val === undefined || val === null) return '';
    if (Array.isArray(val)) {
      return val.map(function (x) { return String(x).trim(); })
        .filter(Boolean).join(NL);
    }
    if (typeof val === 'boolean') return val ? 'true' : 'false';
    return String(val).split(NL)
      .map(function (s) { return s.trim(); }).filter(Boolean).join(NL);
  };

  /** 后端档案 → 编辑工作副本（数组转按行文本，布尔保留）。 */
  D.profileToDraft = function (entry) {
    const d = {};
    Object.keys(entry || {}).forEach(function (k) {
      const v = entry[k];
      d[k] = (typeof v === 'boolean') ? v : D.configFieldToText(v);
    });
    return d;
  };

  /** 逐字段比两份档案，返回 { field: backendText }（N1：无基准，直接比）。 */
  D.profileFieldDiff = function (local, backend) {
    const a = local || {}, b = backend || {}, keys = {}, out = {};
    Object.keys(a).forEach(function (k) { keys[k] = 1; });
    Object.keys(b).forEach(function (k) { keys[k] = 1; });
    Object.keys(keys).forEach(function (k) {
      const av = D.configFieldToText(a[k]);
      const bv = D.configFieldToText(b[k]);
      if (av !== bv) out[k] = bv;
    });
    return out;
  };

  /**
   * 公共配置快照 → POST /config 请求体。
   * GET 里 tool_config 是 {tool:[spec...]}、system_config 是 [spec...]，
   * 后端 _apply_tool_config_section 只吃 {tool:{key:value}}，故在此扁平化。
   * available_tools / site_profiles 是派生或只读字段，不提交。
   */
  D.configPublicToBody = function (pub) {
    const out = {};
    Object.keys(pub || {}).forEach(function (k) { out[k] = pub[k]; });
    const tc = pub && pub.tool_config;
    if (tc && typeof tc === 'object' && !Array.isArray(tc)) {
      const flat = {};
      Object.keys(tc).forEach(function (tool) {
        const rows = tc[tool];
        if (!Array.isArray(rows)) return;
        flat[tool] = {};
        rows.forEach(function (r) {
          if (r && r.key !== undefined) flat[tool][r.key] = r.value;
        });
      });
      out.tool_config = flat;
    }
    const sc = pub && pub.system_config;
    if (Array.isArray(sc)) {
      const flat = {};
      sc.forEach(function (r) { if (r && r.key !== undefined) flat[r.key] = r.value; });
      out.tool_config = out.tool_config || {};
      out.tool_config.system = flat;
    }
    delete out.system_config;
    delete out.default_profile;
    if (out.flask) {    out.flask = Object.assign({}, out.flask);    delete out.flask.url;  }
    delete out.available_tools;
    delete out.site_profiles;
    return out;
  };
})();
