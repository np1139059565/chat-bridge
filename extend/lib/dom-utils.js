// 模块：extend/lib/dom-utils.js
// 用途：前端公共 DOM / 通用工具函数集合，供 content 脚本与 dialog 面板共用。
// 对外接口：window.AIMirrorDomUtils = { debounce, hashStr, textOf, messageFingerprint }
// 依赖：无（纯函数，不依赖任何宿主环境，也不引用 chrome API）
//
// 说明：本文件通过挂载到全局对象暴露接口，便于在同一扩展的不同执行环境
// （content script 沙箱与 dialog iframe）里以 <script> 方式直接引入，
// 不引入打包器依赖。
(function (global) {
  'use strict';

  /**
   * 防抖包装：在连续触发时，只执行最后一次调用。
   * @param {Function} fn 需要防抖的真实函数
   * @param {number} ms 静默间隔（毫秒）
   * @returns {Function} 包装后的防抖函数，保留原调用的 this 与参数
   */
  function debounce(fn, ms) {
    let t;
    return function () {
      const args = arguments;
      // 清除上一次尚未触发的定时器，实现“只执行最后一次”
      clearTimeout(t);
      // 重新计时，到点后以原 this 与参数调用真实函数
      t = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  /**
   * 稳定字符串哈希：把任意字符串映射为短字符串 id。
   * 用途：同一段代码内容在页面重绘后保持同一张卡片（保留执行结果）。
   * 注意：不能掺入下标，否则新消息插入会导致下标整体位移、卡片状态错位。
   * @param {string} s 输入字符串
   * @returns {string} 36 进制哈希串
   */
  function hashStr(s) {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
    return h.toString(36);
  }

  /**
   * 读取元素纯文本并去除首尾空白。
   * @param {Element|null} el 目标元素
   * @returns {string} 元素文本；元素为空时返回空串
   */
  function textOf(el) {
    return (el && (el.innerText || el.textContent) || '').trim();
  }

  /**
   * 数组归一化：把任意值安全转成数组。
   * 网页推送或旧存档可能把本该是数组的字段序列化成对象 / 字符串 / null，
   * 直接调用 join / map / forEach 会抛 TypeError。统一在这里收敛，
   * 调用方拿到的一定是数组，可安全遍历。
   * @param {*} v 任意值
   * @returns {Array} 数组；对象取其值列表，其余非数组值返回空数组
   */
  function toArray(v) {
    if (Array.isArray(v)) return v;
    if (v && typeof v === 'object') return Object.values(v);
    return [];
  }

  /**
   * 消息内容指纹：把一条消息的正文揉成一个稳定字符串。
   * 同一内容的两条消息得到同一指纹，内容不同则指纹不同。
   * 思考块不参与：思考区折叠时读不到文本，纳入会导致同一条消息算出不同指纹，
   * 进而让卡片编号变化、被误判成新卡片。
   * @param {Object} msg 消息对象，形如 { role, name, blocks }
   * @returns {string} 指纹字符串（'m' 开头）
   */
  function messageFingerprint(msg) {
    // 空消息给一个固定指纹，避免调用方拿到 undefined
    if (!msg) return 'm';
    // 角色与名称先入列，让同一段内容在用户 / AI 两种身份下也区分开
    const parts = [String(msg.role || ''), String(msg.name || '')];
    // 逐块收集内容：思考块跳过，其余按类型取关键字段
    // 块列表容错：blocks 字段可能缺失，或被序列化成非数组（对象 / 字符串）。
    // 归一化为数组后再遍历，避免 forEach 抛 TypeError 中断整条调用链。
    toArray(msg.blocks).forEach(function (b) {
      if (!b) return;
      if (b.type === 'thinking') return;   // 思考内容不参与指纹
      // 图片不参与指纹：图片 src（blob / 带签名的临时地址）常随重绘变化，
      // 纳入会让同一条消息反复算出不同指纹，进而误判成新消息、卡片编号漂移。
      if (b.type === 'image') return;
      if (b.type === 'code') parts.push('code|' + (b.lang || '') + '|' + (b.code || ''));
      else if (b.type === 'heading') parts.push('heading|' + (b.level || '') + '|' + (b.text || ''));
      // 列表块的 items 容错：可能被序列化成非数组（对象 / 字符串），
      // 先归一化为数组再 join，避免 join 抛 TypeError。
      else if (b.type === 'list') {
        parts.push('list|' + (b.ordered ? '1' : '0') + '|' + toArray(b.items).join('\u0002'));
      }
      else if (b.type === 'table') parts.push('table|' + JSON.stringify(b.rows || []));
      else parts.push((b.type || 'text') + '|' + (b.text || ''));
    });
    // 分隔符用不可见控制字符，避免正文里出现同样字符造成拼接歧义
    return 'm' + hashStr(parts.join('\u0001'));
  }

  /**
   * 解析「选择器表达式」，求值得到元素集合。
   * 支持两种写法，向后兼容：
   *   1) 完整调用表达式，如 document.querySelectorAll(".a.b")、
   *      document.querySelector("#x")，甚至带 JS 微调（如 [...].filter(...)）；
   *   2) 纯选择器，如 .a.b、#btn-go（旧数据），按 querySelectorAll 处理。
   * 判定策略：先当 JS 表达式求值；成功则把结果规整为元素数组；
   * 失败（纯选择器不是合法 JS）再退回 querySelectorAll。
   * 调用方据返回数组的长度判断「是否唯一元素」。
   * @param {string} expr 选择器表达式
   * @returns {{list: Array<Element>, error: string}} 元素数组与错误码（空串表示无错）
   */
  function resolveSelectorExpr(expr) {
    const s = String(expr == null ? '' : expr).trim();
    if (!s) return { list: [], error: 'empty' };
    let result;
    let evaluated = false;
    try {
      // 用 Function 求值：隔离世界的 document 与页面共享同一 DOM，可直接访问
      result = (new Function('return (' + s + ');'))();
      evaluated = true;
    } catch (e) {
      evaluated = false;   // 非合法 JS：多半是纯选择器，走下面回退
    }
    if (!evaluated) {
      try {
        return { list: Array.prototype.slice.call(document.querySelectorAll(s)), error: '' };
      } catch (e2) {
        return { list: [], error: 'invalid' };   // 选择器语法也非法
      }
    }
    // 规整：单个元素、类数组（NodeList/HTMLCollection/数组）分别处理
    let list = [];
    if (result && result.nodeType === 1) list = [result];
    else if (result && typeof result.length === 'number') list = Array.prototype.slice.call(result);
    // 过滤掉非元素项（表达式可能混入文本节点或其它值）
    list = list.filter(function (n) { return n && n.nodeType === 1; });
    return { list: list, error: list.length ? '' : 'not_found' };
  }

  // 暴露到全局，供 <script> 引入后直接使用
  global.AIMirrorDomUtils = {
    debounce: debounce,
    hashStr: hashStr,
    textOf: textOf,
    toArray: toArray,
    messageFingerprint: messageFingerprint,
    resolveSelectorExpr: resolveSelectorExpr
  };
})(typeof window !== 'undefined' ? window : this);
