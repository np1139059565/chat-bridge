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
   * 修复 JSON 字符串字面量里「未转义的裸控制字符」。
   *
   * 背景：网页 markdown 渲染会把代码块里的 \n 还原成真实换行，导致工具调用 JSON
   * 的字符串内部出现裸换行 / 制表符等控制字符——这在 JSON 规范里非法，JSON.parse
   * 会抛 “Bad control character in string literal”。
   * 做法：状态机遍历，仅在「字符串内部」把裸控制字符替换为其转义形式；
   * 字符串外的换行（JSON 结构缩进）原样保留，不影响结构。
   * @param {string} src 可能含裸控制字符的 JSON 文本
   * @returns {string} 修复后的文本
   */
  M._repairJsonControlChars = function (src) {
    const s = String(src || '');
    let out = '';
    let inString = false;
    let escaped = false;
    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      if (inString) {
        if (escaped) { escaped = false; out += ch; continue; }
        if (ch === '\\') { escaped = true; out += ch; continue; }
        if (ch === '"') { inString = false; out += ch; continue; }
        const code = ch.charCodeAt(0);
        if (code < 0x20) {
          // 裸控制字符：替换为合法转义写法
          if (ch === '\n') out += '\\n';
          else if (ch === '\r') out += '\\r';
          else if (ch === '\t') out += '\\t';
          else out += '\\u' + ('000' + code.toString(16)).slice(-4);
          continue;
        }
        out += ch;
        continue;
      }
      if (ch === '"') inString = true;
      out += ch;
    }
    return out;
  };

  /**
   * 判断代码块是否为一次工具调用：内容是 { tool, parameters } 且带 bridge-chat-call 即算。
   * 安全性由调用方保证：只有「助手消息」里的代码块才会被判为工具调用。
   * 容错：首次解析失败时，先修复字符串内裸控制字符再解析一次（见 _repairJsonControlChars）。
   */
  M.parseToolCall = function (block) {
    if (!block || block.type !== 'code') return null;
    const src = String(block.code || '').trim();
    if (!src || src.charAt(0) !== '{') return null; // 快速排除非 JSON
    let obj = null;
    try {
      obj = JSON.parse(src);
    } catch (e) {
      // 首次失败：多半是网页渲染把 \n 还原成真实换行，导致字符串内出现裸控制字符。
      // 修复后再解析一次；仍失败则按普通代码块处理。
      try {
        obj = JSON.parse(this._repairJsonControlChars(src));
        if (obj) D.log('解析修复：裸控制字符已修复后解析成功');
      } catch (e2) {
        return null;
      }
    }
    if (obj && typeof obj === 'object' && obj.tool && obj.type === 'bridge-chat-call') {
      return { tool: String(obj.tool), parameters: obj.parameters || {} };
    }
    return null;
  };

  /**
   * 从一段文本里找出语音朗读块，返回其 text；无则空串。
   *
   * 用「定位 {"type":"bridge-voice" 标记 + 大括号配平」切出 JSON，
   * 与后端 extract_voice_from_blocks 的裸 JSON 兜底同一思路：
   * 语音块可能漂移成无围栏的裸 JSON（落在段落文本里），
   * 若只认代码块，检测就取不到、误报「语音缺失」。
   * @param {string} text 待扫描文本
   * @returns {string} 朗读文本；无则空串
   */
  function pickVoiceJson(text) {
    const s = String(text || '');
    const marker = '{"type":"bridge-voice"';
    let start = s.indexOf(marker);
    while (start >= 0) {
      let depth = 0, inStr = false, esc = false, end = -1;
      for (let i = start; i < s.length; i++) {
        const ch = s[i];
        if (inStr) {
          if (esc) esc = false;
          else if (ch === '\\') esc = true;
          else if (ch === '"') inStr = false;
          continue;
        }
        if (ch === '"') inStr = true;
        else if (ch === '{') depth++;
        else if (ch === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
      }
      if (end > 0) {
        try {
          const obj = JSON.parse(s.slice(start, end));
          if (obj && obj.type === 'bridge-voice') return String(obj.text || '').trim();
        } catch (e) { /* 继续找下一个标记 */ }
      }
      start = s.indexOf(marker, start + 1);
    }
    return '';
  }

  /**
   * 判断一个块是否为语音朗读块：内容为 {"type":"bridge-voice","text":...}。
   * 与工具调用块同一机制——认内容里的 type 字段，不看语言名、不要求围栏。
   * 兼容两种载体：代码块（标准形态）与段落文本（漂移成裸 JSON 时）。
   * @param {Object} block 块
   * @returns {string} 朗读文本；不是语音块返回空串
   */
  M.parseVoiceBlock = function (block) {
    if (!block) return '';
    if (block.type === 'code') {
      const src = String(block.code || '').trim();
      if (src.charAt(0) === '{') {
        try {
          const obj = JSON.parse(src);
          if (obj && obj.type === 'bridge-voice') return String(obj.text || '').trim();
        } catch (e) { /* 落到下面的扫描 */ }
      }
      return pickVoiceJson(src);
    }
    if (block.type === 'paragraph') return pickVoiceJson(block.text);
    return '';
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
