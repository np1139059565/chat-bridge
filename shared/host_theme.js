// 宿主页面明暗主题探测 —— 共享真源（单一来源，请勿直接编辑副本）
//
// 背景：AI 工具调用镜像插件（extend）与 AI Style Debug Assistant
// （skills/debug_chrome/extension）是两个独立的 Chrome 扩展，各自运行在隔离环境，
// 运行时无法共用同一文件。此前两个扩展各写了一份完全相同的主题探测实现，
// 存在「改一处忘一处导致行为分叉」的风险。
//
// 解法：本文件为唯一真源，改这里后用 scripts/sync_host_theme.py 同步生成两份副本；
// 副本文件头会带「自动生成」标记，日常只需维护本文件。
//
// 依赖：无。挂到 window.HostThemeDetector，供各扩展的命名空间薄包装调用。
(function () {
  'use strict';

  /**
   * 解析颜色的感知亮度；无法判断时返回 null。
   * 网页常把 <html> 底色设为透明，此时返回 null，交给调用方回退到 <body>。
   * @param {string} color CSS 颜色字符串（rgb / rgba）
   * @returns {number|null} 0-255 的亮度值
   */
  function colorLuminance(color) {
    const m = /rgba?\(([^)]+)\)/.exec(color || '');
    if (!m) return null;
    const parts = m[1].split(',').map(function (s) { return parseFloat(s); });
    if (parts.length < 3) return null;
    // alpha 为 0 表示无底色，视为「读不到」，交由调用方回退
    if (parts.length === 4 && parts[3] === 0) return null;
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2];
  }

  /**
   * 读取宿主 <html> 的实际底色，判断明暗主题。
   * <html> 无有效底色时回退到 <body>；两者都读不到时默认亮色，避免误伤。
   * @returns {'dark'|'light'}
   */
  function detectHostTheme() {
    // 1) 属性信号优先：暗色 class / data-theme / data-color-mode / color-scheme。
    //    不少站点只靠 class 或 data-theme 切主题，<html> / <body> 自身背景色透明
    //    或恒为浅色，若只看背景色会永远判成亮色。
    const root = document.documentElement;
    const body = document.body;
    const themeAttr = String(
      (root && (root.getAttribute('data-theme') || root.getAttribute('data-color-mode'))) ||
      (body && (body.getAttribute('data-theme') || body.getAttribute('data-color-mode'))) || ''
    );
    const cls = String((root && root.className) || '') + ' ' + String((body && body.className) || '');
    const cs = root ? String(getComputedStyle(root).colorScheme || '') : '';
    // class 用「分隔符边界」匹配：命中 dark / dark-mode / theme-dark / dark_theme，
    // 又不误伤 darken 这类只是以 dark 开头的无关类名。
    const darkSignal = /dark/i.test(themeAttr) || /(^|[\s_-])dark([\s_-]|$)/i.test(cls) || /dark/i.test(cs);
    const lightSignal = /light/i.test(themeAttr) || /(^|[\s_-])light([\s_-]|$)/i.test(cls) || /light/i.test(cs);
    if (darkSignal && !lightSignal) return 'dark';
    if (lightSignal && !darkSignal) return 'light';
    // 2) 背景色兜底：属性信号缺失或互相矛盾时，按底色亮度判定。
    let lum = root ? colorLuminance(getComputedStyle(root).backgroundColor) : null;
    if (lum === null && body) {
      lum = colorLuminance(getComputedStyle(body).backgroundColor);
    }
    if (lum === null) return 'light';
    return lum < 128 ? 'dark' : 'light';
  }

  // 暴露给各扩展：colorLuminance 一并导出，便于有需要时单独复用
  window.HostThemeDetector = {
    colorLuminance: colorLuminance,
    detect: detectHostTheme,
  };
})();
