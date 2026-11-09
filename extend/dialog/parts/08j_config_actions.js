// 模块：方案 v3 配置动作层——刷新比对 / 本地缓存 / 逐项还原 / 覆盖确认与提交。
// 依赖 08i_config_cache.js（纯函数）与 08g_site_profiles.js（草稿渲染）。
// 关键口径：刷新只更新后端快照，绝不覆盖本地缓存；点【覆盖】才写后端；
// 公共配置整份提交（影响所有页面与电脑），站点配置只提交当前页面档案。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;
  const M = D.methods;
  const NL = String.fromCharCode(10);

  /** 当前页面适配的档案 id：按 hosts 匹配 siteKey（hostname），未登记兜底 glm。 */
  M.currentProfileId = function () {
    const host = String(this.siteKey || '').toLowerCase();
    const profs = (this.configCache && this.configCache.profiles)
      || this.siteProfiles || {};
    const ids = Object.keys(profs);
    if (!host) return profs.glm ? 'glm' : (ids[0] || '');
    for (let i = 0; i < ids.length; i++) {
      const raw = profs[ids[i]] && profs[ids[i]].hosts;
      const arr = Array.isArray(raw) ? raw : String(raw || '').split(NL);
      for (let j = 0; j < arr.length; j++) {
        const hx = String(arr[j] || '').trim().toLowerCase();
        if (hx && (host === hx || host.slice(-hx.length - 1) === '.' + hx)) return ids[i];
      }
    }
    return profs.glm ? 'glm' : (ids[0] || '');
  };

  M.configLoadAndDiff = async function (backend) {
    this.configBackend = backend;
    this.configOffline = false;
    let cache = await D.configCacheGet(this.siteKey);
    if (!cache) {
      cache = JSON.parse(JSON.stringify(backend));
      await D.configCacheSet(this.siteKey, cache);
    }
    this.configCache = cache;
    this.siteProfiles = cache.profiles || {};
    if (!this._siteProfLoaded) {
      this._siteProfLoaded = true;
      this.resetSiteProfDraft();
    }
    this.recomputeConfigDiff();
  };

  M.recomputeConfigDiff = function () {
    const cache = this.configCache || {}, backend = this.configBackend || {};
    const cp = cache.profiles || {}, bp = backend.profiles || {};
    const ids = {}, diff = {};
    Object.keys(cp).forEach(function (k) { ids[k] = 1; });
    Object.keys(bp).forEach(function (k) { ids[k] = 1; });
    Object.keys(ids).forEach(function (pid) {
      const d = D.profileFieldDiff(D.profileToDraft(cp[pid]), D.profileToDraft(bp[pid]));
      if (Object.keys(d).length) diff[pid] = d;
    });
    const pl = D.configPublic(cache), pb = D.configPublic(backend), pd = {};
    Object.keys(pl).concat(Object.keys(pb)).forEach(function (k) {
      if (JSON.stringify(pl[k]) !== JSON.stringify(pb[k])) pd[k] = pb[k];
    });
    this.configDiff = diff;
    this.configPublicDiff = pd;
    const nSite = Object.keys(diff).reduce(function (a, k) {
      return a + Object.keys(diff[k]).length; }, 0);
    this.configDirty = nSite > 0 || Object.keys(pd).length > 0;
    this.configDiffCount = nSite + Object.keys(pd).length;
  };

  M.persistConfigCache = async function () {
    const cache = this.configCache || (this.configCache = {});
    const out = D.serializeProfilesDraft(this.siteProfDraft || {});
    const old = cache.profiles || {};
    this._configRemovedSites = Object.keys(old)
      .filter(function (pid) { return !(pid in out); });
    // 直接用序列化结果：删掉的站点不能从 old 里复活，否则本地缓存与删除意图相反。
    cache.profiles = out;
    await D.configCacheSet(this.siteKey, cache);
    if (this.configBackend) this.recomputeConfigDiff();
  };

  M.syncPublicToCache = async function () {
    const cache = this.configCache || (this.configCache = {});
    if (this.configTools) cache.tools = this.configTools;
    if (this.toolConfig) cache.tool_config = this.toolConfig;
    if (this.systemConfig) cache.system_config = this.systemConfig;
    if (this.maxJsonChars) {
      cache.limits = Object.assign({}, cache.limits, { max_json_chars: this.maxJsonChars });
    }
    if (this.config && this.config.profile) cache.default_profile = this.config.profile;
    await D.configCacheSet(this.siteKey, cache);
    if (this.configBackend) this.recomputeConfigDiff();
  };

  M.restoreProfileField = async function (pid, field) {
    const bp = (this.configBackend && this.configBackend.profiles) || {};
    const bk = bp[pid] || {};
    if (!this.siteProfDraft[pid]) this.siteProfDraft[pid] = {};
    this.siteProfDraft[pid][field] = D.configFieldToText(bk[field]);
    await this.persistConfigCache();
    this.toast('已按服务端还原 ' + pid + '.' + field);
  };

  M.restorePublicKey = async function (key) {
    const val = (this.configBackend || {})[key];
    this.configCache[key] = val;
    if (key === 'tools') this.configTools = val;
    if (key === 'limits' && val) this.maxJsonChars = val.max_json_chars;
    if (key === 'tool_config') this.toolConfig = val;
    if (key === 'system_config') this.systemConfig = val;
    await D.configCacheSet(this.siteKey, this.configCache);
    this.recomputeConfigDiff();
    this.toast('已按服务端还原 ' + key);
  };

  M.toggleSiteScope = function () { this.siteProfShowAll = !this.siteProfShowAll; };
  M.confirmConfigOverwrite = function () { this.siteProfConfirmOpen = true; };
  M.cancelConfigOverwrite = function () { this.siteProfConfirmOpen = false; };

  M.applyConfigOverwrite = async function () {
    await this.persistConfigCache();
    const cache = this.configCache || {};
    const body = D.configPublicToBody(D.configPublic(cache));
    const pid = this.currentProfileId();
    const out = D.serializeProfilesDraft(this.siteProfDraft || {});
    if (pid && out[pid]) body.profiles = { [pid]: out[pid] };
    const removed = (this._configRemovedSites || []).slice();
    if (removed.length) body.profiles_remove = removed;
    try {
      await D.apiFetch(this, '/config', { method: 'POST', body: body });
      this.configBackend = JSON.parse(JSON.stringify(cache));
      await D.configCacheSet(this.siteKey, cache);
      window.parent.postMessage({ type: 'profiles_refresh' }, '*');
      this.siteProfConfirmOpen = false;
      this.recomputeConfigDiff();
      this.toast('已覆盖服务端配置');
    } catch (e) {
      this.toast('覆盖失败：' + e);
    }
  };

  D.renderConfigStatusBar = function (ctx) {
    const offline = !!ctx.configOffline;
    const dirty = !!ctx.configDirty;
    const pubKeys = Object.keys(ctx.configPublicDiff || {});
    return h('div', { class: 'sp-config-bar' }, [
      h('span', {}, offline ? '（后端未连接：仅显示本地缓存，不做比对）'
        : (dirty ? '有 ' + (ctx.configDiffCount || 0) + ' 项与服务端不一致，运行仍用服务端版本'
          : h('span', { class: 'sp-config-ok' }, '本地与服务端一致'))),
      h('button', { onClick: () => ctx.toggleSiteScope() },
        ctx.siteProfShowAll ? '只看当前站点' : '显示全部站点'),
      h('button', { onClick: () => ctx.confirmConfigOverwrite() }, '覆盖'),
      offline ? null : h('span', { class: 'sp-site-scope' },
        '当前站点：' + (ctx.currentProfileId ? ctx.currentProfileId() : '')),
      ...pubKeys.map(function (k) {
        return h('span', { key: k }, [
          h('span', {}, '公共差异：' + k + ' '),
          h('button', { class: 'sp-restore-btn',
            onClick: () => ctx.restorePublicKey(k) }, '还原')
        ]);
      })
    ]);
  };

  D.renderConfigConfirmBar = function (ctx) {
    if (!ctx.siteProfConfirmOpen) return null;
    const pid = ctx.currentProfileId ? ctx.currentProfileId() : '';
    const removed = ctx._configRemovedSites || [];
    return h('div', { class: 'sp-confirm' }, [
      h('b', {}, '确认覆盖服务端配置？'),
      h('div', { class: 'sp-confirm-col' },
        '【公共配置】整份提交：端口、工具上下线、体积上限、工具与系统配置等。'
        + '其它页面、其它电脑都会受影响。'),
      h('div', { class: 'sp-confirm-col' },
        '【网页 AI 站点配置】只提交当前页面【' + pid + '】的档案；'
        + '其它站点不受影响，但其它电脑上同一个页面会被覆盖。'
        + (removed.length ? '（将删除站点：' + removed.join('、') + '）' : '')),
      h('div', {}, [
        h('button', { onClick: () => ctx.applyConfigOverwrite() }, '确认覆盖'),
        h('button', { onClick: () => ctx.cancelConfigOverwrite() }, '取消')
      ])
    ]);
  };
})();
