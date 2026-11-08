// 模块：extend/dialog/parts/08g_site_profiles.js
// 用途：设置页「网页 AI 站点配置」区块——站点档案（真源 definition.yaml 的
//       app.profiles）的可视化编辑：逐字段展示（缺失项可见、可填、可留空）、
//       新增 / 删除站点、自定义字段、字段级试运行（定位 / 点击 / 试匹配）、
//       整体保存写回后端并通知内容脚本热更新。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
// 字段级试运行链路：抽屉把「当前编辑值（未保存也可测）」经 window.parent 发给
// 内容脚本（profiles_test_field），内容脚本按模式求值后回传
// profiles_test_result，本模块按 pid.field 键对号入座显示。点击模式与 QQ 指令
// 同一条求值链路（06_picker.execClick）；定位模式只统计命中并短暂高亮首个，
// 无点击副作用。回执监听独立注册在本模块（不经 05_messages 的分发链）。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;
  const M = D.methods;

  // 字段元表已拆至 parts/08h_profile_fields.js（元表随站点类型增长，拆分避免本文件超长）。
  // 分组、字段名、kind 与 defaultOn 全部在那里定义，本文件只消费。

  /**
   * 把编辑工作副本序列化为可提交后端的档案结构（纯函数，供单测）。
   * hosts 与 list 字段按行拆数组并剔除空行；split 保持布尔；其余转字符串
   * （空串=未配置，与后端 sanitize 的「空值保留」口径一致）。
   * @param {Object} draft 编辑工作副本
   * @returns {Object} 可直接 POST 的 {pid: 字段表}
   */
  D.serializeProfilesDraft = function (draft) {
    const out = {};
    const src = draft || {};
    Object.keys(src).forEach(function (pid) {
      const fields = src[pid] || {};
      const entry = {};
      Object.keys(fields).forEach(function (k) {
        const val = fields[k];
        if (k === 'split') { entry[k] = !!val; return; }
        if (k === 'hosts' || (D.PROFILE_FIELD_META[k] && D.PROFILE_FIELD_META[k].kind === 'list')) {
          entry[k] = String(val == null ? '' : val).split('\n')
            .map(function (s) { return s.trim(); }).filter(Boolean);
          return;
        }
        entry[k] = (val === true || val === false) ? val : String(val == null ? '' : val);
      });
      if (!entry.label) entry.label = pid;
      if (!entry.hosts) entry.hosts = [];
      out[pid] = entry;
    });
    return out;
  };

  /**
   * 渲染「网页 AI 站点配置」区块：站点卡片列表 + 新增表单 + 保存行。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderSiteProfilesBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', { title: '站点档案：每站一份完整清单，真源在后端配置文件；保存后当前页即时生效' }, '网页 AI 站点配置'),
        h('button', { onClick: () => { ctx.siteProfOpen = !ctx.siteProfOpen; } },
          ctx.siteProfOpen ? '▾' : '▸')
      ]),
      ctx.siteProfOpen ? h('div', { class: 'bridge-body' }, [renderProfilesBody(ctx)]) : null
    ]);
  };

  /** 区块主体：未连接后端的提示，或 新增表单 + 各站点卡片 + 保存行。 */
  function renderProfilesBody(ctx) {
    const ids = Object.keys(ctx.siteProfDraft || {});
    if (!ids.length && !Object.keys(ctx.siteProfiles || {}).length) {
      return h('div', { class: 'hint' }, '（未读取到站点档案，请先连接后端）');
    }
    return h('div', { class: 'sp-profiles' }, [
      renderNewSiteForm(ctx),
      ...ids.map((pid) => renderSiteCard(ctx, pid)),
    ]);
  }

  /** 新增站点表单：id + 显示名 + 域名（多行）。添加后进入编辑区，保存才落库。 */
  function renderNewSiteForm(ctx) {
    return h('div', { class: 'sp-new-site' }, [
      h('div', { class: 'hint' },
        '新增站点：填 id 与域名后添加，字段可留空；保存后新开该站页面即自动识别'),
      h('div', { class: 'sp-new-row' }, [
        h('input', { type: 'text', placeholder: '站点 id（字母/数字/下划线，如 kimi）',
          value: ctx.newSiteId, onInput: (e) => { ctx.newSiteId = e.target.value; } }),
        h('input', { type: 'text', placeholder: '显示名（如 Kimi）',
          value: ctx.newSiteLabel, onInput: (e) => { ctx.newSiteLabel = e.target.value; } }),
        h('button', { onClick: () => { ctx.addSiteProfile(); ctx.queueSiteProfSave(); } }, '添加')
      ]),
      h('textarea', { class: 'sp-area', rows: 2, placeholder: '域名，每行一个（如 kimi.com）',
        value: ctx.newSiteHosts, onInput: (e) => { ctx.newSiteHosts = e.target.value; } })
    ]);
  }

  /** 单个站点卡片：头部（id / 显示名 / 域名徽标 / 删除）+ 展开后的字段分组。 */
  function renderSiteCard(ctx, pid) {
    const draft = ctx.siteProfDraft[pid] || {};
    const expanded = !!ctx.siteProfExpanded[pid];
    const hosts = String(draft.hosts || '').split('\n')
      .map((s) => s.trim()).filter(Boolean);
    // 删除两步确认：3 秒内二次点击才生效（armed 态按钮变红提示）
    const delArm = ctx.siteProfDeleting[pid] &&
      (Date.now() - ctx.siteProfDeleting[pid] < 3000);
    return h('div', { class: 'sp-site-card', key: pid }, [
      h('div', { class: 'sp-site-head', onClick: () => { ctx.siteProfExpanded[pid] = !ctx.siteProfExpanded[pid]; } }, [
        h('span', { class: 'caret' }, expanded ? '▾' : '▸'),
        h('b', {}, pid),
        h('span', { class: 'desc' }, String(draft.label || '')),
        h('span', { class: 'sp-chips' },
          hosts.map((x) => h('span', { class: 'sp-chip', key: x }, x))),
        h('button', {
          class: 'sp-site-del' + (delArm ? ' armed' : ''),
          onClick: (ev) => { ev.stopPropagation(); ctx.deleteSiteProfile(pid); ctx.queueSiteProfSave(); }
        }, delArm ? '确认删除' : '删除')
      ]),
      expanded ? h('div', { class: 'tc-body' }, [
        ...D.PROFILE_FIELD_GROUPS.map((g) => renderFieldGroup(ctx, pid, g)),
        renderCustomGroup(ctx, pid),
        renderAddFieldRow(ctx, pid)
      ]) : null
    ]);
  }

  /** 一个字段分组：渲染该组全部已知字段（缺失项也显示，可填）。 */
  function renderFieldGroup(ctx, pid, group) {
    const meta = D.PROFILE_FIELD_META;
    const fields = Object.keys(meta).filter((f) => meta[f].group === group.id);
    if (!fields.length) return null;
    return h('div', { class: 'sp-group', key: group.id }, [
      h('div', { class: 'sp-group-title' }, group.title),
      ...fields.map((f) => renderProfileField(ctx, pid, f, meta[f]))
    ]);
  }

  /**
   * 单个已知字段行：label + hint + 控件（按 kind 选 input / textarea / checkbox）
   * + 试运行按钮 + 结果。测试用当前编辑值，未保存也可测。
   */
  function renderProfileField(ctx, pid, field, meta) {
    const draft = ctx.siteProfDraft[pid] || {};
    const val = draft[field];
    const key = pid + '.' + field;
    const kind = meta && meta.kind;
    const mode = kind === 'click' ? 'click' : (kind === 'regex' ? 'regex' : 'locate');
    let control;
    if (field === 'split') {
      control = h('input', { type: 'checkbox', checked: !!val,
        onChange: (e) => { ctx.siteProfDraft[pid][field] = e.target.checked; ctx.queueSiteProfSave(); } });
    } else if (kind === 'bool') {
      // 布尔开关：meta.defaultOn 为真的字段，缺省（未写过）按开启显示。
      // 判定口径与消费端一致——只有显式 false 才算关闭。
      const checked = val === undefined || val === null || val === ''
        ? !!meta.defaultOn : !!val;
      control = h('input', { type: 'checkbox', checked: checked,
        onChange: (e) => { ctx.siteProfDraft[pid][field] = e.target.checked; ctx.queueSiteProfSave(); } });
    } else if (field === 'hosts' || kind === 'list' || kind === 'click') {
      control = h('textarea', { class: 'sp-area', rows: kind === 'click' ? 3 : 2,
        placeholder: field === 'hosts' ? '每行一个域名'
          : (kind === 'click' ? '裸选择器或完整 JS 表达式' : '每行一条选择器'),
        value: val == null ? '' : String(val),
        onInput: (e) => { ctx.siteProfDraft[pid][field] = e.target.value; ctx.queueSiteProfSave(); } });
    } else {
      control = h('input', { type: 'text', class: 'sp-input', placeholder: '未配置（留空）',
        value: val == null ? '' : String(val),
        onInput: (e) => { ctx.siteProfDraft[pid][field] = e.target.value; ctx.queueSiteProfSave(); } });
    }
    const res = ctx.siteProfTestResult[key];
    const testing = !!ctx.siteProfTesting[key];
    return h('div', { class: 'tc-row', key: field }, [
      h('div', { class: 'tc-label' }, [
        h('span', {}, field),
        h('div', { class: 'tc-hint' }, (meta && meta.label ? meta.label : '自定义字段')
          + (meta && meta.hint ? '：' + meta.hint : ''))
      ]),
      h('div', { class: 'tc-control sp-field-control' }, [
        control,
        kind && kind !== 'hosts' ? h('button', {
          class: 'sp-test-btn', disabled: testing,
          onClick: () => ctx.testProfileField(pid, field, mode)
        }, testing ? '测试中…' : (mode === 'click' ? '点击测试'
          : (mode === 'regex' ? '试匹配' : '定位测试'))) : null,
        res ? h('span', { class: 'sp-test-result ' + (res.ok ? 'ok' : 'err') }, res.text) : null
      ])
    ]);
  }

  /** 自定义字段（不在元表内）分组：支持定位 / 点击两种测试与整行删除。 */
  function renderCustomGroup(ctx, pid) {
    const draft = ctx.siteProfDraft[pid] || {};
    const extra = Object.keys(draft).filter((k) => !D.PROFILE_FIELD_META[k]);
    if (!extra.length) return null;
    return h('div', { class: 'sp-group' }, [
      h('div', { class: 'sp-group-title' }, '自定义字段'),
      ...extra.map((f) => renderCustomField(ctx, pid, f))
    ]);
  }

  /** 单个自定义字段行。 */
  function renderCustomField(ctx, pid, field) {
    const val = (ctx.siteProfDraft[pid] || {})[field];
    const key = pid + '.' + field;
    const res = ctx.siteProfTestResult[key];
    const testing = !!ctx.siteProfTesting[key];
    const btn = (mode, label) => h('button', {
      class: 'sp-test-btn', disabled: testing,
      onClick: () => ctx.testProfileField(pid, field, mode)
    }, testing ? '测试中…' : label);
    return h('div', { class: 'tc-row', key: field }, [
      h('div', { class: 'tc-label' }, [
        h('span', {}, field),
        h('div', { class: 'tc-hint' }, '自定义字段：值按选择器 / 表达式处理')
      ]),
      h('div', { class: 'tc-control sp-field-control' }, [
        h('input', { type: 'text', class: 'sp-input', value: val == null ? '' : String(val),
          onInput: (e) => { ctx.siteProfDraft[pid][field] = e.target.value; ctx.queueSiteProfSave(); } }),
        h('div', { class: 'sp-btn-row' }, [
          btn('locate', '定位测试'),
          btn('click', '点击测试'),
          h('button', { class: 'sp-del-field',
            onClick: () => { ctx.removeProfileField(pid, field); ctx.queueSiteProfSave(); } }, '删字段')
        ]),
        res ? h('span', { class: 'sp-test-result ' + (res.ok ? 'ok' : 'err') }, res.text) : null
      ])
    ]);
  }

  /** 添加自定义字段行。 */
  function renderAddFieldRow(ctx, pid) {
    const nf = ctx.newField[pid] || {};
    return h('div', { class: 'sp-add-field' }, [
      h('input', { type: 'text', placeholder: '新字段名（如 answerWrap）',
        value: nf.name || '',
        onInput: (e) => {
          if (!ctx.newField[pid]) ctx.newField[pid] = {};
          ctx.newField[pid].name = e.target.value;
        } }),
      h('input', { type: 'text', placeholder: '字段值（选择器 / 表达式）',
        value: nf.value || '',
        onInput: (e) => {
          if (!ctx.newField[pid]) ctx.newField[pid] = {};
          ctx.newField[pid].value = e.target.value;
        } }),
      h('button', { onClick: () => { ctx.addProfileField(pid); ctx.queueSiteProfSave(); } }, '加字段'),
      h('span', { class: 'hint' }, '档案支持任意字段；已知字段按元表渲染，其余归入自定义')
    ]);
  }

  // ---- 方法（挂 D.methods，模板经 ctx 调用） ----

  /** 从 siteProfiles 快照重置编辑工作副本（list / hosts 转为按行文本）。 */
  M.resetSiteProfDraft = function () {
    const draft = {};
    const profs = this.siteProfiles || {};
    Object.keys(profs).forEach(function (pid) {
      const src = profs[pid] || {};
      const d = {};
      Object.keys(src).forEach(function (k) {
        const val = src[k];
        if (k === 'hosts' || (D.PROFILE_FIELD_META[k] && D.PROFILE_FIELD_META[k].kind === 'list')) {
          d[k] = Array.isArray(val) ? val.join('\n') : String(val == null ? '' : val);
          return;
        }
        d[k] = val;
      });
      draft[pid] = d;
    });
    this.siteProfDraft = draft;
  };

  /** 输入防抖自动保存：800ms 合并一次写回；成功静默，失败 toast。 */
  M.queueSiteProfSave = function () {
    if (this._spSaveTimer) clearTimeout(this._spSaveTimer);
    this._spSaveTimer = setTimeout(() => {
      this._spSaveTimer = null;
      this.saveSiteProfiles();
    }, 800);
  };

  /** 保存：序列化工作副本 → POST /config profiles 整体替换 → 通知内容脚本重拉。 */
  M.saveSiteProfiles = async function () {
    const out = D.serializeProfilesDraft(this.siteProfDraft);
    for (const pid of Object.keys(out)) {
      if (!/^[A-Za-z0-9_]+$/.test(pid)) {
        this.toast('站点 id 不合法：' + pid);
        return;
      }
    }
    try {
      await D.apiFetch(this, '/config', { method: 'POST', body: { profiles: out } });
      this.siteProfiles = out;
      // 通知当前页内容脚本重拉（热更新）；其它已开标签页在下次注入 / 刷新时取新值
      window.parent.postMessage({ type: 'profiles_refresh' }, '*');
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

  /**
   * 字段试运行：把当前编辑值发给内容脚本求值（未保存也可测）。
   * @param {string} pid 站点 id
   * @param {string} field 字段名
   * @param {string} mode click / locate / regex
   */
  M.testProfileField = function (pid, field, mode) {
    const val = (this.siteProfDraft[pid] || {})[field];
    if (val == null || String(val).trim() === '') {
      this.toast('该字段为空，测试前请先填写');
      return;
    }
    const key = pid + '.' + field;
    this.siteProfTesting[key] = true;
    this.siteProfTestResult[key] = null;
    window.parent.postMessage({
      type: 'profiles_test_field', key: key, mode: mode, value: String(val)
    }, '*');
    // 超时兜底：内容脚本未响应（旧版未重载扩展 / 页面无脚本）时给出明确提示
    setTimeout(() => {
      if (this.siteProfTesting[key]) {
        this.siteProfTesting[key] = false;
        this.siteProfTestResult[key] = { ok: false, text: '超时未回执（页面无内容脚本或需重载扩展）' };
      }
    }, 8000);
  };

  /** 试运行回执：按 key 对号入座。 */
  M.onProfilesTestResult = function (d) {
    const key = d.key || '';
    this.siteProfTesting[key] = false;
    this.siteProfTestResult[key] = { ok: !!d.ok, text: String(d.text || '') };
  };

  /** 新增站点：校验 id 唯一与字符集，加入编辑区（未保存）。 */
  M.addSiteProfile = function () {
    const pid = String(this.newSiteId || '').trim();
    if (!/^[A-Za-z0-9_]+$/.test(pid)) {
      this.toast('站点 id 只能含字母 / 数字 / 下划线');
      return;
    }
    if (this.siteProfDraft[pid]) {
      this.toast('站点 id 已存在：' + pid);
      return;
    }
    const hosts = String(this.newSiteHosts || '').split('\n')
      .map((s) => s.trim()).filter(Boolean);
    this.siteProfDraft[pid] = {
      label: String(this.newSiteLabel || '').trim() || pid,
      hosts: hosts.join('\n'),
      split: true
    };
    this.siteProfExpanded[pid] = true;
    this.newSiteId = '';
    this.newSiteLabel = '';
    this.newSiteHosts = '';
    this.toast('已添加站点 ' + pid + '（填写字段后点「保存」生效）');
  };

  /** 删除站点（两步确认，3 秒内二次点击才生效；仅移出编辑区，保存后落库）。 */
  M.deleteSiteProfile = function (pid) {
    const now = Date.now();
    if (!this.siteProfDeleting[pid] || now - this.siteProfDeleting[pid] > 3000) {
      this.siteProfDeleting[pid] = now;
      setTimeout(() => { this.siteProfDeleting[pid] = 0; }, 3100);
      return;
    }
    this.siteProfDeleting[pid] = 0;
    if (this.siteProfDraft[pid]) {
      delete this.siteProfDraft[pid];
      this.toast('已移除站点 ' + pid + '（点「保存」后从配置删除）');
    }
  };

  /** 添加自定义字段。 */
  M.addProfileField = function (pid) {
    const nf = this.newField[pid] || (this.newField[pid] = {});
    const name = String(nf.name || '').trim();
    if (!/^[A-Za-z0-9_]+$/.test(name)) {
      this.toast('字段名只能含字母 / 数字 / 下划线');
      return;
    }
    if (!this.siteProfDraft[pid]) return;
    if (this.siteProfDraft[pid][name] !== undefined) {
      this.toast('字段已存在：' + name);
      return;
    }
    this.siteProfDraft[pid][name] = String(nf.value || '');
    nf.name = '';
    nf.value = '';
  };

  /** 删除自定义字段（已知字段只能清空不能删键，避免误拆结构）。 */
  M.removeProfileField = function (pid, field) {
    const d = this.siteProfDraft[pid];
    if (d && d[field] !== undefined && !D.PROFILE_FIELD_META[field]) {
      delete d[field];
    }
  };

  // 独立监听内容脚本回执（不经 05_messages 的 onPageMessage，避免碰它的分发链）：
  // profiles_test_result = 字段试运行结果；profiles_applied = 档案热更新回执。
  window.addEventListener('message', function (e) {
    const d = e.data;
    if (!d || !d.type) return;
    const inst = D.instance;
    if (!inst) return;
    if (d.type === 'profiles_test_result' && inst.onProfilesTestResult) {
      inst.onProfilesTestResult(d);
    } else if (d.type === 'profiles_applied' && d.reason === 'refresh') {
      // 保存后的重拉回执给出明确反馈；注入时的首次拉取不提示，避免每次开页都弹
      inst.toast('页面已应用新档案（' + (d.count || 0) + ' 个站点）');
    }
  });
})();
