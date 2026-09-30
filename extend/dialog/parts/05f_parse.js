// 模块：extend/dialog/parts/05f_parse.js
// 用途：消息与代码块的解析判定：工具调用、外部调用信封、silent 工具、消息 id。
//       从 05_messages.js 抽出，使该文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
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
   * 判定一条消息的来源，返回第三方角色标记：'user' | 'assistant' | 'tool'。
   *
   * 为什么要它：工具结果等机器产物此前都伪装成 user 落地，各处只能靠
   * 「内容里有没有 bridge-chat-res 字样」反推，脆弱且分散。这里把来源判定
   * 收敛成唯一入口：建节点时算一次、存到节点上，之后所有地方读字段即可。
   *
   * 约定：
   *   - assistant 消息 → 'assistant'（AI）；
   *   - 含 bridge-chat-res 的 user 消息 → 'tool'（工具结果，第三方角色）；
   *   - 其余 user 消息（含外部卡片 / QQ 消息）→ 'user'（用户本人）。
   * @param {Object} m 消息对象
   * @returns {string} 'user' | 'assistant' | 'tool'
   */
  M.msgSource = function (m) {
    if (!m) return 'user';
    if (m.role === 'assistant') return 'assistant';
    if (m.role !== 'user') return 'user';
    const blocks = window.AIMirrorDomUtils.toArray(m.blocks);
    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      if (!b) continue;
      const s = String(b.code || b.text || '');
      if (s.indexOf('bridge-chat-res') >= 0) return 'tool';
    }
    return 'user';
  };
})();
