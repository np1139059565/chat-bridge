// 模块：extend/lib/dom-utils.js
// 用途：前端公共 DOM / 通用工具函数集合，供 content 脚本与 dialog 面板共用。
// 对外接口：window.AIMirrorDomUtils = { debounce, hashStr, textOf }
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

  // 暴露到全局，供 <script> 引入后直接使用
  global.AIMirrorDomUtils = { debounce: debounce, hashStr: hashStr, textOf: textOf };
})(typeof window !== 'undefined' ? window : this);
