// 模块：extend/lib/dialects.js
// 用途：翻译员的「语言包 + 方言处理函数」层（规格 4.1 / 4.2，决策 1）。
//       一个本体配多套方言：按站点 id 分派，不为每站新建翻译员。
// 对外接口：window.AIMirrorDialects = { pick, list, resolve, languagePack, handlers }
// 依赖：无。纯分派层，不碰 DOM —— 输入框定位/写入/发送/生成态判定的真实
//       动作交给调用方注入的 dom 适配层，与 content 侧既有实现保持同源。
//
// 背景：语言包由翻译员所有、寄存在 /api/clients 的 custom_config，服务端不解释
//       字段。本模块只在「取回之后」按约定键读取选择器数据，缺省时回退出厂值，
//       后端未注册/不可达时功能不中断（阶段 2 验收：行为与改造前一致）。
(function (global) {
  'use strict';

  // 出厂兜底选择器：语言包缺键时用它，和 content/00_state.js 的 PROFILES 同源。
  var FALLBACK = {
    inputSelector: 'textarea, [contenteditable="true"]',
    sendButton: 'button[type="submit"]',
    container: '.chat, [class*=message-list]',
    generatingSelectors: ['[disabled]', '[class*=generating]']
  };

  /** 把可能是单串/数组的值统一成去空字符串数组。 */
  function asList(v) {
    if (Array.isArray(v)) return v.map(function (x) { return String(x || '').trim(); }).filter(Boolean);
    var s = String(v == null ? '' : v).trim();
    return s ? [s] : [];
  }

  /** 从语言包里取一个选择器键；缺键或类型异常回退出厂值。 */
  function resolve(pack, key) {
    var p = (pack && typeof pack === 'object') ? pack : {};
    var val = p[key];
    if (typeof val === 'string' && val.trim()) return val.trim();
    if (Array.isArray(val) && val.length) return asList(val);
    return FALLBACK[key];
  }

  /** 从 custom_config 原样取出语言包本体：服务端不解释字段，这里也不改写。 */
  function languagePack(customConfig) {
    if (!customConfig || typeof customConfig !== 'object') return null;
    // 约定：整份 custom_config 即该站档案；若其中显式带「语言包」子对象则取它。
    var inner = customConfig['语言包'];
    return (inner && typeof inner === 'object') ? inner : customConfig;
  }

  /**
   * 四支方言处理函数的默认实现（规格 4.1）。
   * 每支都接收一个 ctx：{ pack, dom, el, text }；dom 由浏览器侧注入，
   * 提供 query / setValue / click / press / disabled 五个原语。
   * 本体只负责「按语言包选元素 + 调原语」，不重复实现站点 DOM 细节。
   */
  function defaultHandlers() {
    return {
      locate: function (c) {
        return c.dom.query(resolve(c.pack, 'inputSelector'));
      },
      write: function (c) {
        return c.dom.setValue(c.el || c.dom.query(resolve(c.pack, 'inputSelector')), c.text);
      },
      send: function (c) {
        var btn = c.dom.query(resolve(c.pack, 'sendButton'));
        if (btn && !c.dom.disabled(btn)) return c.dom.click(btn);
        return c.dom.press(c.el || c.dom.query(resolve(c.pack, 'inputSelector')));
      },
      generating: function (c) {
        var sels = asList(resolve(c.pack, 'generatingSelectors'));
        for (var i = 0; i < sels.length; i++) {
          if (c.dom.query(sels[i])) return true;
        }
        return false;
      }
    };
  }

  // 站点 → 方言覆盖表。每项只写「与默认不同的那一两支」，其余复用本体默认实现，
  // 这正是决策 1「一个本体 + 多套方言」：换站点只换覆盖，不复制整份处理代码。
  var OVERRIDES = {
    glm: {},
    qianwen: {},
    deepseek: {},
    kimi: {},
    yuanbao: {},
    wenxin: {},
    xinghuo: {}
  };

  /** 按站点 id 组装一份方言策略；未登记站点落默认实现（不为每站新建本体）。 */
  function pick(siteKey) {
    var id = String(siteKey || '').toLowerCase();
    var base = defaultHandlers();
    var over = OVERRIDES[id] || {};
    var out = {};
    for (var k in base) {
      if (Object.prototype.hasOwnProperty.call(base, k)) out[k] = over[k] || base[k];
    }
    return { id: id, handlers: out };
  }

  /** 已登记方言 id 列表，供诊断与测试核对「多套」确实存在。 */
  function list() {
    return Object.keys(OVERRIDES).sort();
  }

  var api = {
    pick: pick, list: list, resolve: resolve,
    languagePack: languagePack, handlers: defaultHandlers,
    FALLBACK: FALLBACK
  };
  global.AIMirrorDialects = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
