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

  /** 悬浮明细单行：能取到母本值的原子项显示「键=母本值」，其余显示原标签。 */
  D.diffTipLine = function (it) {
    if (!it) return '';
    return it.backend ? it.key + '=' + it.backend : it.label;
  };

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
    function norm(draft) {
      const o = {};
      Object.keys(draft || {}).forEach(function (k) { o[k] = D.configValueToText(draft[k]); });
      return o;
    }
    Object.keys(ids).forEach(function (pid) {
      const d = D.profileFieldDiff(norm(D.profileToDraft(cp[pid])), norm(D.profileToDraft(bp[pid])));
      if (Object.keys(d).length) diff[pid] = d;
    });
    const pl = D.configPublic(cache), pb = D.configPublic(backend), pd = {};
    Object.keys(pl).concat(Object.keys(pb)).forEach(function (k) {
      if (JSON.stringify(pl[k]) !== JSON.stringify(pb[k])) pd[k] = pb[k];
    });
    const PUB_LABEL = {
      tools: '工具上下线 / run_command 支持语言',
      tool_config: '工具内部配置', system_config: '系统资源上限',
      limits: '工具结果体积上限', default_profile: '默认站点档案',
      flask: '服务端口 / 地址'
    };
    function blockLabel(id) {
      const b = (D.CONFIG_BLOCKS || []).filter(function (x) { return x.id === id; })[0];
      return b ? b.label : id;
    }
    // 单一明细源：顶部计数 / 各徽标 / 弹框列表全从这里取，数目不会再对不上。
    const items = [], seen = {};
    function add(block, section, label, detail, key, backend) {
      const k = block + '|' + label;
      if (seen[k]) return;
      seen[k] = 1;
      items.push({ block: block, section: section, label: label, detail: detail || '',
        key: key || label, backend: backend == null ? '' : String(backend) });
    }
    Object.keys(diff).forEach(function (pid) {
      Object.keys(diff[pid]).forEach(function (f) {
        add('site_profiles', 'site_profiles', '网页 AI 站点配置 · ' + pid + '.' + f,
          '本地草稿与服务端不一致', pid + '.' + f, D.configValueToText(diff[pid][f]));
      });
    });
    Object.keys(pd).forEach(function (k) {
      const sec = (k === 'tools' || k === 'tool_config') ? 'tools' : 'general';
      add(sec, sec, '公共配置 · ' + (PUB_LABEL[k] || k), '整份提交，影响所有页面与电脑',
        k, D.configValueToText(pd[k]));
    });
    (cache.pending || []).forEach(function (w) {
      add(w.block, w.block, blockLabel(w.block) + ' · 待覆盖写入', w.path);
    });
    const bf = cache.blockFields || {};
    Object.keys(bf).forEach(function (bid) {
      Object.keys(bf[bid] || {}).forEach(function (k) {
        const e = bf[bid][k];
        if (String(e.current) !== String(e.baseline)) {
          add(bid, bid, blockLabel(bid) + ' · ' + k, '输入未保存',
            bid + '.' + k, D.configValueToText(e.baseline));
        }
      });
    });
    const byBlock = {};
    items.forEach(function (it) { byBlock[it.block] = (byBlock[it.block] || 0) + 1; });
    this.configDiff = diff;
    this.configPublicDiff = pd;
    this.configDiffItems = items;
    this.configBlockDirty = byBlock;
    this.configDirty = items.length > 0;
    this.configDiffCount = items.length;
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
    return h('button', { class: 'sp-restore-btn', title: '还原为服务端值',
      onClick: () => { if (ctx.restorePublicItem) ctx.restorePublicItem(section, name, key); }
    }, [h('span', { class: 'sp-restore-icon' }, '↺'), ' 还原']);
  };
  /** 各公共配置区卡片头挂的小徽标，滚下去也看得见差异。 */

  D.renderConfigBadge = function (ctx, section) {
    if (!ctx || !ctx.configBackend || ctx.configOffline) return null;
    const list = (ctx.configDiffItems || []).filter(function (it) { return it.section === section; });
    if (!list.length) return null;
    const tip = list.map(function (it) { return D.diffTipLine ? D.diffTipLine(it) : it.label; }).join(String.fromCharCode(10));
    return h('span', { class: 'sp-diff-badge', title: tip, 'data-warn-icon': '1' }, list.length + ' 项未覆盖（悬浮看具体项）');
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
    const items = ctx.configDiffItems || [];
    const n = items.length;
    const tip = items.slice(0, 24).map(function (it) {
      const line = D.diffTipLine ? D.diffTipLine(it) : '';
      return line && line !== it.label ? it.label + ' · ' + line : it.label;
    }).join(String.fromCharCode(10));
    return h('div', { class: 'sp-config-bar' }, [
      offline ? h('span', {}, '（后端未连接：仅显示本地缓存，不做比对）')
        : (n ? h('span', { class: 'sp-diff-badge', title: tip },
            n + ' 项未覆盖（悬浮看具体项）') : null),
      h('button', { onClick: () => { if (ctx.toggleSiteScope) ctx.toggleSiteScope(); } },
        ctx.siteProfShowAll ? '只看当前站点' : '显示全部站点'),
      h('button', { onClick: () => {
        if (ctx.confirmConfigOverwrite) ctx.confirmConfigOverwrite();
        else ctx.siteProfConfirmOpen = true;
      } }, '查看差异 / 覆盖'),
      offline ? null : h('span', { class: 'sp-site-scope' },
        '当前站点：' + (ctx.currentProfileId ? ctx.currentProfileId() : ''))
    ]);
  };



  D.renderConfigConfirmBar = function (ctx) {
    if (!ctx.siteProfConfirmOpen) return null;
    const items = ctx.configDiffItems || [];
    const pid = ctx.currentProfileId ? ctx.currentProfileId() : '';
    const groups = {};
    items.forEach(function (it) {
      (groups[it.block] || (groups[it.block] = [])).push(it);
    });
    const rows = [];
    Object.keys(groups).forEach(function (bid) {
      rows.push(h('div', { class: 'sp-modal-group', key: 'g:' + bid },
        (groups[bid][0].label.split(' · ')[0] || bid)));
      groups[bid].forEach(function (it, i) {
        rows.push(h('div', { class: 'sp-modal-row', key: bid + i }, [
          h('span', {}, '· ' + it.label),
          it.detail ? h('span', { class: 'sp-site-scope' }, it.detail) : null
        ]));
      });
    });
    if (!rows.length) rows.push(h('div', { class: 'sp-modal-row' }, '没有待覆盖项。'));
    return h('div', { class: 'sp-modal-mask' }, [
      h('div', { class: 'sp-modal' }, [
        h('b', {}, '确认覆盖服务端配置？以下 ' + items.length + ' 项将被写入'),
        h('div', { class: 'sp-modal-list' }, rows),
        h('div', { class: 'sp-modal-scope' }, [
          h('div', {}, '【公共配置】整份提交：以上「公共配置」各项会影响其它页面、其它电脑。'),
          h('div', {}, '【网页 AI 站点配置】只提交当前页面【' + pid + '】的档案；其它站点不受影响，但其它电脑上同一个页面会被覆盖。'),
          h('div', { class: 'sp-site-scope' }, '两台几乎同时覆盖仍后写胜；回放为多次请求、非原子，中途失败不自动回滚。')
        ]),
        h('div', { class: 'sp-modal-actions' }, [
          h('button', { onClick: () => { if (ctx.applyConfigOverwrite) ctx.applyConfigOverwrite(); } }, '确认覆盖'),
          h('button', { onClick: () => { ctx.siteProfConfirmOpen = false; } }, '取消')
        ])
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
    const list = (ctx.configDiffItems || []).filter(function (it) { return it.block === id; });
    const tip = list.map(function (it) { return D.diffTipLine ? D.diffTipLine(it) : it.label; }).join(String.fromCharCode(10));
    return h('span', { class: 'sp-diff-badge', title: tip, 'data-warn-icon': '1' }, list.length + ' 项未覆盖（悬浮看具体项）');
  };



  /** 站点配置块专属徽标：只数 configDiff 里的字段差异。 */

  D.renderSiteProfileBadge = function (ctx) {
    if (!ctx || !ctx.configBackend || ctx.configOffline) return null;
    const list = (ctx.configDiffItems || []).filter(function (it) { return it.block === 'site_profiles'; });
    if (!list.length) return null;
    const tip = list.map(function (it) { return D.diffTipLine ? D.diffTipLine(it) : it.label; }).join(String.fromCharCode(10));
    return h('span', { class: 'sp-diff-badge', title: tip, 'data-warn-icon': '1' }, list.length + ' 项未覆盖（悬浮看具体项）');
  };


  /** 任意配置值稳定转文本：数组按行、对象取 hosts/value 或 JSON，杜绝 [object Object]。 */
  D.configValueToText = D.configValueToText || function (v) {
    if (v == null) return '';
    if (typeof v === 'string') return v;
    if (typeof v === 'number' || typeof v === 'boolean') return String(v);
    if (Array.isArray(v)) return v.map(D.configValueToText).join(String.fromCharCode(10));
    if (typeof v === 'object') {
      if ('hosts' in v) return D.configValueToText(v.hosts);
      if ('value' in v) return D.configValueToText(v.value);
      try { return JSON.stringify(v); } catch (e) { return ''; }
    }
    return String(v);
  };
  // 覆盖 08h 旧实现：所有草稿字段一律走上面的归一化。
  D.configFieldToText = function (v) { return D.configValueToText(v); };
})();
