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
    if (!cache) cache = JSON.parse(JSON.stringify(backend));
    // 端口/连接地址由 discoverFlask + savePort 专管，不进本地草稿：
    // 否则后端改端口后，本地旧值会被【覆盖】写回去，把服务打到空端口。
    cache.flask = JSON.parse(JSON.stringify(backend.flask || {}));
    await D.configCacheSet(this.siteKey, cache);
    // 自愈：历史缓存曾因提交体扁平化被原地改成 {tool:{key:value}}，
    // renderToolConfig 对对象调 .map 会抛错，工具内部配置项整片消失。
    // spec 结构永远以服务端声明为准，本地只保留同名 key 的 value。
    function healSpecs(bSpec, cSpec) {
      const out = {};
      Object.keys(bSpec || {}).forEach(function (tool) {
        const rows = bSpec[tool], cur = (cSpec || {})[tool] || {};
        const local = {};
        if (Array.isArray(cur)) cur.forEach(function (r) { local[r.key] = r.value; });
        else Object.keys(cur).forEach(function (k) { local[k] = cur[k]; });
        out[tool] = (Array.isArray(rows) ? rows : []).map(function (sp) {
          const x = Object.assign({}, sp);
          if (sp.key in local) x.value = local[sp.key];
          return x;
        });
      });
      return out;
    }
    cache.tool_config = healSpecs(backend.tool_config, cache.tool_config);
    if (Array.isArray(backend.system_config)) {
      const localSys = {}, curSys = cache.system_config;
      if (Array.isArray(curSys)) {
        curSys.forEach(function (r) { localSys[r.key] = r.value; });
      } else if (curSys && typeof curSys === 'object') {
        // 历史缓存曾被提交体扁平化成 {key:value} 对象；只认数组会让资源上限值退回默认。
        Object.keys(curSys).forEach(function (k) { localSys[k] = curSys[k]; });
      }
      cache.system_config = backend.system_config.map(function (sp) {
        const x = Object.assign({}, sp);
        if (sp.key in localSys) x.value = localSys[sp.key];
        return x;
      });
    }
    this.toolConfig = cache.tool_config;
    this.systemConfig = cache.system_config;
    await D.configCacheSet(this.siteKey, cache);
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
    const pending = cache.pending || [], byBlock = {}, blockIds = {};
    pending.forEach(function (w) { byBlock[w.block] = (byBlock[w.block] || 0) + 1; blockIds[w.block] = 1; });
    // 输入态：未点保存的字段改动也要提示。同一区块已有 pending 时不重复计数。
    const bf = cache.blockFields || {};
    let fieldExtra = 0;
    Object.keys(bf).forEach(function (bid) {
      let n = 0;
      Object.keys(bf[bid] || {}).forEach(function (k) {
        const e = bf[bid][k];
        if (String(e.current) !== String(e.baseline)) n++;
      });
      if (!n) return;
      if (!byBlock[bid]) { byBlock[bid] = n; fieldExtra += n; }
    });
    this.configDiff = diff;
    this.configPublicDiff = pd;
    this.configBlockDirty = byBlock;
    const nSite = Object.keys(diff).reduce(function (a, k) {
      return a + Object.keys(diff[k]).length; }, 0);
    this.configDirty = nSite > 0 || Object.keys(pd).length > 0 || pending.length > 0 || fieldExtra > 0;
    this.configDiffCount = nSite + Object.keys(pd).length + pending.length + fieldExtra;
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

  /** 取后端某公共控件的当前值；供标色与逐项还原共用。 */
  M.publicBackendValue = function (section, name, key) {
    const b = this.configBackend || {};
    if (section === 'tools') {
      const t = (b.tools || {})[name];
      if (key === 'languages') return (t && t.languages) || [];
      return !t || t.enabled !== false;
    }
    if (section === 'system_config') {
      const row = (b.system_config || []).find(function (r) { return r.key === key; });
      return row ? row.value : undefined;
    }
    if (section === 'tool_config') {
      const row = ((b.tool_config || {})[name] || []).find(function (r) { return r.key === key; });
      return row ? row.value : undefined;
    }
    if (section === 'limits') return (b.limits || {}).max_json_chars;
    return undefined;
  };

  /** 控件值 vs 服务端值：实时比对，不依赖 sync 时机，编辑当下即标色。 */
  M.publicIsDiff = function (section, name, key, uiValue) {
    const bv = this.publicBackendValue(section, name, key);
    if (bv === undefined) return false;
    try { return JSON.stringify(uiValue) !== JSON.stringify(bv); }
    catch (e) { return false; }
  };

  /** 逐项还原：只把这一个控件改回服务端值，再同步进缓存；绝不整组刷。 */
  M.restorePublicItem = async function (section, name, key) {
    const bv = this.publicBackendValue(section, name, key);
    if (bv === undefined) return;
    if (section === 'tools') {
      if (!this.configTools[name]) this.configTools[name] = {};
      if (key === 'languages') this.configTools[name].languages = bv;
      else this.configTools[name].enabled = bv;
    } else if (section === 'system_config') {
      const row = (this.systemConfig || []).find(function (r) { return r.key === key; });
      if (row) row.value = bv;
    } else if (section === 'tool_config') {
      const row = ((this.toolConfig || {})[name] || []).find(function (r) { return r.key === key; });
      if (row) row.value = bv;
    } else if (section === 'limits') {
      this.maxJsonChars = bv;
    }
    await this.syncPublicToCache();
    this.toast('已按服务端还原 ' + section + (name ? '.' + name : '') + (key ? '.' + key : ''));
  };

  /** 渲染层装饰：差异色 class + 逐项还原按钮；缺方法时静默降级，老测试不炸。 */
  D.publicFieldClass = function (ctx, section, name, key, uiValue) {
    if (!ctx || !ctx.publicIsDiff) return '';
    return ctx.publicIsDiff(section, name, key, uiValue) ? ' sp-field-diff' : '';
  };
  D.publicRestoreBtn = function (ctx, section, name, key, uiValue) {
    if (!ctx || !ctx.publicIsDiff || !ctx.publicIsDiff(section, name, key, uiValue)) return null;
    return h('button', { class: 'sp-restore-btn',
      onClick: () => { if (ctx.restorePublicItem) ctx.restorePublicItem(section, name, key); }
    }, '还原');
  };
  /** 各公共配置区卡片头挂的小徽标，滚下去也看得见差异。 */
  D.renderConfigBadge = function (ctx, section) {
    if (!ctx || !ctx.configBackend || ctx.configOffline) return null;
    const pd = ctx.configPublicDiff || {};
    let keys;
    if (section === 'tools') keys = ['tools', 'tool_config'];
    else if (section === 'general') keys = ['limits', 'system_config', 'default_profile'];
    else keys = Object.keys(pd);
    const n = keys.filter(function (k) { return k in pd; }).length;
    // 只数本段：全局计数含站点档案与其它区块，挂局部头会串号。
    if (!n) return null;
    return h('span', { class: 'sp-diff-badge' }, n + ' 项未覆盖');
  };

  M.toggleSiteScope = function () { this.siteProfShowAll = !this.siteProfShowAll; };
  M.confirmConfigOverwrite = function () { this.siteProfConfirmOpen = true; };
  M.cancelConfigOverwrite = function () { this.siteProfConfirmOpen = false; };

  M.applyConfigOverwrite = async function () {
    try {
      const pending = ((this.configCache && this.configCache.pending) || []).slice()
        .sort(function (a, b) { return a.seq - b.seq; });
      for (let i = 0; i < pending.length; i++) {
        const w = pending[i];
        await D.apiFetch(this, w.path, { method: w.method, body: w.body, __commit: true });
      }
      await this.persistConfigCache();
      const cache = this.configCache || {};
      const body = D.configPublicToBody(D.configPublic(cache));
      const pid = this.currentProfileId();
      const out = D.serializeProfilesDraft(this.siteProfDraft || {});
      if (pid && out[pid]) body.profiles = { [pid]: out[pid] };
      const removed = (this._configRemovedSites || []).slice();
      if (removed.length) body.profiles_remove = removed;
      await D.apiFetch(this, '/config', { method: 'POST', body: body, __commit: true });
      cache.pending = [];
      if (D.clearBlockFields) D.clearBlockFields(this);
      this.configBackend = JSON.parse(JSON.stringify(cache));
      await D.configCacheSet(this.siteKey, cache);
      window.parent.postMessage({ type: 'profiles_refresh' }, '*');
      this.siteProfConfirmOpen = false;
      this.recomputeConfigDiff();
      this.toast('已覆盖服务端配置（含 ' + pending.length + ' 项其它配置）');
    } catch (e) {
      this.toast('覆盖失败：' + e);
    }
  };

  D.renderConfigStatusBar = function (ctx) {
    const offline = !!ctx.configOffline;
    const dirty = !!ctx.configDirty;
    const pubKeys = Object.keys(ctx.configPublicDiff || {});
    const blockIds = Object.keys(ctx.configBlockDirty || {});
    return h('div', { class: 'sp-config-bar' }, [
      offline ? h('span', {}, '（后端未连接：仅显示本地缓存，不做比对）')
        : (dirty ? h('span', {}, '有 ' + (ctx.configDiffCount || 0)
            + ' 项与服务端不一致，运行仍用服务端版本') : null),
      h('button', { onClick: () => { if (ctx.toggleSiteScope) ctx.toggleSiteScope(); } },
        ctx.siteProfShowAll ? '只看当前站点' : '显示全部站点'),
      h('button', { onClick: () => { if (ctx.confirmConfigOverwrite) ctx.confirmConfigOverwrite(); } }, '覆盖'),
      offline ? null : h('span', { class: 'sp-site-scope' },
        '当前站点：' + (ctx.currentProfileId ? ctx.currentProfileId() : '')),
      ...pubKeys.map(function (k) {
        return h('span', { key: k, class: 'sp-diff-badge' }, '公共差异：' + k);
      }),
      ...blockIds.map(function (id) {
        const b = (D.CONFIG_BLOCKS || []).filter(function (x) { return x.id === id; })[0];
        return h('span', { key: id, class: 'sp-diff-badge' }, [
          h('span', {}, ctx.configBlockDirty[id] + ' 项未覆盖：' + (b ? b.label : id) + ' '),
          h('button', { class: 'sp-restore-btn',
            onClick: () => { if (ctx.discardConfigBlock) ctx.discardConfigBlock(id); } }, '还原')
        ]);
      }),
      (pubKeys.length || blockIds.length) ? h('span', { class: 'sp-site-scope' },
        '（各控件旁可点【还原】逐项还原）') : null
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
        h('button', { onClick: () => { if (ctx.applyConfigOverwrite) ctx.applyConfigOverwrite(); } }, '确认覆盖'),
        h('button', { onClick: () => { if (ctx.cancelConfigOverwrite) ctx.cancelConfigOverwrite(); } }, '取消')
      ])
    ]);
  };
  /** 受管配置区块的待覆盖写入登记（由 00a_api.js 草稿拦截层调用）。 */
  D.queuePendingWrite = async function (ctx, block, path, method, body) {
    const cache = ctx.configCache || (ctx.configCache = {});
    // 同一路径只留最后一次：配置 POST 通常是整份覆盖，旧草稿无意义。
    const list = (cache.pending || []).filter(function (w) { return w.path !== path; });
    list.push({ seq: Date.now() + Math.random(), block: block.id,
      label: block.label, path: path, method: method, body: body });
    cache.pending = list;
    await D.configCacheSet(ctx.siteKey, cache);
    if (ctx.recomputeConfigDiff) ctx.recomputeConfigDiff();
  };

  /** 丢弃某区块的本地草稿；不写后端，重新展开后显示服务端值。 */
  M.discardConfigBlock = async function (id) {
    const cache = this.configCache || (this.configCache = {});
    cache.pending = (cache.pending || []).filter(function (w) { return w.block !== id; });
    if (D.resetBlockFields) D.resetBlockFields(this, id);
    await D.configCacheSet(this.siteKey, cache);
    this.recomputeConfigDiff();
    this.toast('已丢弃该区块的本地改动');
  };

  /** 区块卡片头徽标：一致 / 离线静默，仅存在未覆盖写入时亮。 */
  D.renderBlockBadge = function (ctx, id) {
    if (!ctx || !ctx.configBlockDirty || !ctx.configBlockDirty[id]) return null;
    return h('span', { class: 'sp-diff-badge' }, ctx.configBlockDirty[id] + ' 项未覆盖');
  };


  /** 站点配置块专属徽标：只数 configDiff 里的字段差异。 */
  D.renderSiteProfileBadge = function (ctx) {
    if (!ctx || !ctx.configBackend || ctx.configOffline) return null;
    const d = ctx.configDiff || {};
    let n = 0;
    Object.keys(d).forEach(function (pid) { n += Object.keys(d[pid]).length; });
    if (!n) return null;
    return h('span', { class: 'sp-diff-badge' }, n + ' 项未覆盖');
  };

})();
