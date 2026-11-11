// 模块：受管配置区块的输入态追踪。
// 拦截层只在「点保存发 POST」时登记 pending，输入框改值当下不会标色也不会亮徽标。
// 此处在渲染时记下后端读回值作 baseline，onInput 立即比对并计入差异。
// N1 口径：不设版本基准，自己改的也标色；【还原】擦回 baseline。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  function state(ctx) {
    const cache = ctx.configCache || (ctx.configCache = {});
    return cache.blockFields || (cache.blockFields = {});
  }
  /** 渲染时调用：首次见该字段记 baseline；返回 data-diff 值（1=有差异）。 */
  D.blockFieldClass = function (ctx, blockId, key, val) {
    if (!ctx) return '';
    const bf = state(ctx);
    const bb = bf[blockId] || (bf[blockId] = {});
    if (!(key in bb)) {
      bb[key] = { baseline: val, current: val };
      if (D.configCacheSet) D.configCacheSet(ctx.siteKey, ctx.configCache);
      return '';
    }
    return String(bb[key].current) !== String(bb[key].baseline) ? '1' : '';
  };
  /** onInput 调用：登记当前值并立刻刷新徽标，不等重渲染。 */
  D.markBlockField = function (ctx, blockId, key, val) {
    if (!ctx) return;
    const bf = state(ctx);
    const bb = bf[blockId] || (bf[blockId] = {});
    if (!(key in bb)) bb[key] = { baseline: val, current: val };
    else bb[key].current = val;
    if (D.configCacheSet) D.configCacheSet(ctx.siteKey, ctx.configCache);
    if (ctx.recomputeConfigDiff) ctx.recomputeConfigDiff();
  };
  /** 点保存后：把差异转为 pending，避免同一改动双算。 */
  D.settleBlockFields = function (ctx, blockId) {
    const bb = state(ctx)[blockId];
    if (!bb) return;
    Object.keys(bb).forEach(function (k) { bb[k].baseline = bb[k].current; });
    if (D.configCacheSet) D.configCacheSet(ctx.siteKey, ctx.configCache);
    if (ctx.recomputeConfigDiff) ctx.recomputeConfigDiff();
  };
  /** 【还原】：把输入框擦回服务端读回值。 */
  D.resetBlockFields = function (ctx, blockId) {
    const bb = state(ctx)[blockId];
    if (!bb) return;
    Object.keys(bb).forEach(function (k) { bb[k].current = bb[k].baseline; });
    if (D.configCacheSet) D.configCacheSet(ctx.siteKey, ctx.configCache);
    if (ctx.recomputeConfigDiff) ctx.recomputeConfigDiff();
  };
  /** 覆盖成功后：本地与服务端对齐，清空全部输入态。 */
  D.clearBlockFields = function (ctx) {
    if (ctx.configCache) ctx.configCache.blockFields = {};
    if (D.configCacheSet) D.configCacheSet(ctx.siteKey, ctx.configCache);
  };
  D.setBlockFieldBaseline = function (ctx, blockId, key, val) {
    const bf = state(ctx);
    const bb = bf[blockId] || (bf[blockId] = {});
    bb[key] = { baseline: val, current: val };
  };

  const BASE = new WeakMap();
  const SKIP = '.tc-row, .lang-checks, [data-cfg-skip], .sp-new-site, .sp-add-field';
  function capture(el) {
    if (!el || !el.tagName || typeof el.closest !== 'function') return;
    const block = el.closest('[data-cfg-block]');
    if (!block) return;
    const id = block.getAttribute('data-cfg-block');
    if (id === 'site_profiles' || el.closest(SKIP)) return;
    const nodes = block.querySelectorAll('input, textarea, select');
    const idx = Array.prototype.indexOf.call(nodes, el);
    const key = el.getAttribute('data-cfg-key') || el.name || el.id || ('f' + idx);
    const val = (el.type === 'checkbox' || el.type === 'radio') ? !!el.checked : el.value;
    BASE.set(el, { id: id, key: key, baseline: val });
  }
  function onEdit(ev) {
    const el = ev.target;
    let rec = BASE.get(el);
    if (!rec) { capture(el); rec = BASE.get(el); }
    if (!rec || typeof el.closest !== 'function' || el.closest(SKIP)) return;
    const cur = (el.type === 'checkbox' || el.type === 'radio') ? !!el.checked : el.value;
    if (String(cur) !== String(rec.baseline)) el.setAttribute('data-diff', '1');
    else el.removeAttribute('data-diff');
    const ctx = D._cfgCtx;
    if (!ctx) return;
    D.setBlockFieldBaseline(ctx, rec.id, rec.key, rec.baseline);
    D.markBlockField(ctx, rec.id, rec.key, cur);
    if (ctx.$forceUpdate) ctx.$forceUpdate();
  }
  D.installConfigFieldTracking = function (ctx) {
    D._cfgCtx = ctx;
    if (D._cfgFieldTrackingInstalled || typeof document === 'undefined') return;
    D._cfgFieldTrackingInstalled = true;
    document.addEventListener('focusin', function (ev) { capture(ev.target); });
    document.addEventListener('pointerdown', function (ev) { capture(ev.target); }, true);
    document.addEventListener('input', onEdit);
    document.addEventListener('change', onEdit);
  };

})();
