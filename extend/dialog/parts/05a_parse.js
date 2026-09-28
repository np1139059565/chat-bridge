// 模块：extend/dialog/parts/05a_parse.js
// 用途：消息解析辅助：工具调用块识别、外部调用信封识别、消息 id、
//       助手回复质量检测、silent 工具判断。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
// 说明：本文件是 05_messages.js 的解析部分独立拆分，方法统一挂到 D.methods。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /** 判断某工具是否为 silent（仅不在抽屉生成工具卡片；结果照常回传）。 */
  M.toolSilent = function (name) {
    const t = (this.tools || []).find((x) => x.name === name);
    return !!(t && t.silent);
  };

  /**
   * 判断代码块是否为一次工具调用：内容是 { tool, parameters } 且带 bridge-chat-call 即算。
   * 安全性由调用方保证：只有「助手消息」里的代码块才会被判为工具调用。
   */
  M.parseToolCall = function (block) {
    if (!block || block.type !== 'code') return null;
    const src = String(block.code || '').trim();
    if (!src || src.charAt(0) !== '{') return null; // 快速排除非 JSON
    try {
      const obj = JSON.parse(src);
      if (obj && typeof obj === 'object' && obj.tool && obj.type === 'bridge-chat-call') {
        return { tool: String(obj.tool), parameters: obj.parameters || {} };
      }
    } catch (e) { /* 不是工具调用，按普通代码块渲染 */ }
    return null;
  };

  /**
   * 判断一条消息是否为外部调用信封（external-call）。
   * 外部卡片发送到网页后，会以一条 user 消息落在对话里；这条消息即卡片的
   * 本体，用于在镜像区还原为卡片、在列表里做颜色标记。
   * 信封可能被解析成 code 或 text 两种块形态，两者都识别。
   * @param {Object} m 消息对象
   * @returns {Object|null} { nonce, request }；非外部调用返回 null
   */
  M.parseExternalCall = function (m) {
    if (!m || m.role !== 'user') return null;
    const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (!b) continue;
      const src = String(b.code || b.text || '').trim();
      if (!src || src.charAt(0) !== '{') continue;
      try {
        const obj = JSON.parse(src);
        if (obj && typeof obj === 'object' && obj.type === 'external-call') {
          return {
            nonce: obj.nonce || '',
            request: obj.request || ''
          };
        }
      } catch (e) { /* 非信封内容，继续找下一个块 */ }
    }
    return null;
  };

  /** 消息 id：直接复用内容指纹。指纹以 'm' 开头、不含分隔符 '-'。 */
  M.msgId = function (m) {
    return this.messageFingerprint(m);
  };

  /**
   * 判定一条助手消息的质量问题。返回 null 表示无问题，否则返回问题描述。
   * @param {Object} m 消息对象
   * @returns {Object|null} { error, message }
   */
  M.assistantQualityIssue = function (m) {
    if (!m || m.role !== 'assistant') return null;
    const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
    if (!blocks.length) return null;
    // 问题一：只有代码块，没有任何文字说明
    const hasCode = blocks.some((b) => b && b.type === 'code');
    const hasText = blocks.some((b) => {
      if (!b || b.type === 'code' || b.type === 'thinking') return false;
      let s = '';
      if (b.text != null) s = String(b.text);
      else if (b.items) s = window.AIMirrorDomUtils.toArray(b.items).join(' ');
      else if (b.rows) s = JSON.stringify(b.rows);
      return s.trim().length > 0;
    });
    if (hasCode && !hasText) {
      return {
        error: 'code_only_reply',
        message: '本条回复只包含代码块，缺少文字说明，无法监控流程。'
          + '请在代码块之外补充说明再重新生成。'
      };
    }
    // 问题二：思考内容大段英文
    const think = blocks.find((b) => b && b.type === 'thinking');
    if (think) {
      const t = String(think.text || '');
      const letters = (t.match(/[A-Za-z]/g) || []).length;
      const total = t.replace(/\s/g, '').length;
      if (total > 200 && letters / total > 0.8) {
        return {
          error: 'thinking_english',
          message: '本条回复的思考内容以英文为主（约 ' + Math.round(letters / total * 100)
            + '% 为英文字符），无法监控流程。请用中文重新生成。'
        };
      }
    }
    return null;
  };
})();
