/* ============================================================
 * 网页版机器人 —— 站点切换器
 *
 * 解决的问题：一台电脑同时开多个网页 AI 时，手机端原本把所有站点的消息
 * 混在同一条时间线里，分不清哪条来自哪个 AI。本模块提供站点选择与本地记忆，
 * 让消息按站点隔离显示。
 *
 * 三件事：
 * 1. 从 /api/web/sites 拉可切换站点列表；
 * 2. 记住用户选的站点（localStorage），刷新后保持；
 * 3. 提供一个查询函数，供各处拼请求 URL 时带上 site 参数。
 *
 * 为什么用 localStorage 而非服务端：这是「这台手机当前看哪个站」的偏好，
 * 与账号无关，也不该影响其他设备；放在本地最省事、也最不容易串。
 * ============================================================ */
(function () {
  'use strict';

  var STORAGE_KEY = 'webActiveSite';
  var sites = [];          // 后端返回的站点列表 [{id, label, online}]
  var active = '';         // 当前选中的站点 id；空串表示「未知站点」
  var ready = false;       // 站点列表是否已拉取过

  /** 从本地存储恢复上次的选择。 */
  function restore() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      if (v) active = v;
    } catch (e) { /* 隐私模式下 localStorage 不可用，忽略 */ }
  }

  /** 保存当前选择到本地存储。 */
  function save() {
    try { localStorage.setItem(STORAGE_KEY, active || ''); } catch (e) { /* 忽略 */ }
  }

  /**
   * 拉取可切换的站点列表。
   * @param {Function} [done] 完成回调，入参为站点列表
   */
  function load(done) {
    fetch('/api/web/sites', { headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.success) return;
        sites = data.sites || [];
        ready = true;
        // 当前选中的站点若已不在列表里（配置被删），回落到第一个或未知站点
        var ids = sites.map(function (s) { return s.id; });
        if (active && ids.indexOf(active) === -1) {
          active = sites.length ? sites[0].id : '';
          save();
        }
        // 首次使用：默认选第一个站点，避免一进来看到的是「未知站点」空列表
        if (!active && sites.length) {
          active = sites[0].id;
          save();
        }
        if (typeof done === 'function') done(sites);
      })
      .catch(function () { /* 取不到时保持空列表，页面照常工作 */ });
  }

  /**
   * 拼到请求 URL 上的站点参数片段（含前导 &）。
   * 未选站点时返回空串，后端按「不过滤」处理——保持旧行为，不至于拉不到数据。
   * @returns {string} 如 '&site=qianwen'，或空串
   */
  function queryParam() {
    return active ? '&site=' + encodeURIComponent(active) : '';
  }

  /** 取当前站点 id（可能为空串）。 */
  function getActive() { return active; }

  /** 取站点列表。 */
  function list() { return sites; }

  /** 是否已加载过站点列表。 */
  function isReady() { return ready; }

  /**
   * 切换站点并保存；返回是否真的变了（变了才需要重新拉消息）。
   * @param {string} id 目标站点 id
   * @returns {boolean} 是否发生了变化
   */
  function setActive(id) {
    var v = String(id || '');
    if (v === active) return false;
    active = v;
    save();
    return true;
  }

  /**
   * 把站点选择器渲染到指定容器。
   * 每个站点一个按钮，带在线状态点；当前选中的高亮。
   * @param {Element} box 容器元素
   * @param {Function} onPick 选中回调，入参为站点 id
   */
  function render(box, onPick) {
    if (!box) return;
    box.innerHTML = '';
    if (!sites.length) {
      var empty = document.createElement('span');
      empty.className = 'site-empty';
      empty.textContent = '未配置站点';
      box.appendChild(empty);
      return;
    }
    sites.forEach(function (s) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'site-chip' + (s.id === active ? ' on' : '') + (s.online ? ' live' : '');
      btn.textContent = s.label || s.id;
      btn.title = s.id + (s.online ? '（在线）' : '（无在线页面）');
      btn.addEventListener('click', function () {
        if (typeof onPick === 'function') onPick(s.id);
      });
      box.appendChild(btn);
    });
  }

  // 启动即恢复上次选择，不等网络：这样首屏请求就能带上正确的站点
  restore();

  /**
   * 自启动：DOM 就绪后拉站点列表并渲染选择器。
   * 切换站点时整页重载——游标、DOM、去重状态全部按新站点重建，
   * 比逐处重置更不容易漏。
   */
  function boot() {
    var box = document.getElementById('siteBar');
    if (!box) return;
    load(function () {
      render(box, function (id) {
        if (setActive(id)) location.reload();
      });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.WebSite = {
    load: load,
    list: list,
    getActive: getActive,
    setActive: setActive,
    isReady: isReady,
    queryParam: queryParam,
    render: render
  };
})();
