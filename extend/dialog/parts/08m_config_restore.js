// 模块：extend/dialog/parts/08m_config_restore.js
// 用途：块头 / 状态栏徽标点击后，把该区块（或全部）未覆盖改动批量还原到服务端母本。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const deep = (v) => JSON.parse(JSON.stringify(v));

  D.applyRestore = async function (ctx, bids, items) {
    if (!ctx) return;
    const cache = ctx.configCache || (ctx.configCache = {});
    const backend = ctx.configBackend || {};
    const wanted = (b) => bids.indexOf(b) >= 0;
    const picked = items.filter((it) => wanted(it.block));
    if (wanted('site_profiles') && picked.some((it) => it.block === 'site_profiles')) {
      ctx.siteProfiles = deep(backend.profiles || {});
      if (ctx.resetSiteProfDraft) ctx.resetSiteProfDraft();
      cache.profiles = deep(backend.profiles || {});
      if (ctx._configRemovedSites) ctx._configRemovedSites = [];
    }
    const segs = {};
    picked.forEach((it) => {
      if ((it.block === 'tools' || it.block === 'general') && it.key && backend[it.key] !== undefined) segs[it.key] = 1;
    });
    // 公共配置区块：即使快照里没有可匹配的明细项（假差异键后端不存在），
    // 也整组对齐服务端白名单键，保证点击还原后计数归零、警告真的消失。
    if (bids.some(function (b) { return b === 'general' || b === 'tools'; })) {
      ['tools', 'tool_config', 'system_config', 'limits', 'flask', 'default_profile'].forEach(function (k) {
        if (backend[k] !== undefined) segs[k] = 1;
      });
    }
    Object.keys(segs).forEach((k) => {
      const v = deep(backend[k]);
      cache[k] = v;
      if (k === 'tools' && ctx.configTools !== undefined) ctx.configTools = deep(v);
      if (k === 'tool_config' && ctx.toolConfig !== undefined) ctx.toolConfig = deep(v);
      if (k === 'system_config' && ctx.systemConfig !== undefined) ctx.systemConfig = deep(v);
      if (k === 'limits' && ctx.maxJsonChars !== undefined && v && v.max_json_chars !== undefined) ctx.maxJsonChars = v.max_json_chars;
      if (k === 'default_profile' && ctx.config) ctx.config.profile = v;
    });
    if (Array.isArray(cache.pending)) cache.pending = cache.pending.filter((w) => !wanted(w.block));
    bids.forEach((b) => { if (cache.blockFields && cache.blockFields[b]) delete cache.blockFields[b]; });
    if (ctx.persistConfigCache) await ctx.persistConfigCache();
    else if (ctx.recomputeConfigDiff) ctx.recomputeConfigDiff();
    if (ctx.toast) ctx.toast(bids.length > 1 ? '已批量还原全部未覆盖改动' : '已批量还原该区块的未覆盖改动');
  };

  D.restoreBlockDiff = async function (ctx, bid) {
    const snap = ((ctx && ctx.configDiffItems) || []).slice();
    await D.applyRestore(ctx, [bid], snap);
  };

  D.restoreAllDiff = async function (ctx) {
    const snap = ((ctx && ctx.configDiffItems) || []).slice();
    const bids = [];
    snap.forEach((it) => { if (bids.indexOf(it.block) < 0) bids.push(it.block); });
    await D.applyRestore(ctx, bids, snap);
  };
})();
