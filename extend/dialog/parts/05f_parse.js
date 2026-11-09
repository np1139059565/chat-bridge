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
   * 去掉代码文本里的不可见字符：零宽空格 / 零宽连接符 / BOM 会被 JSON.parse 判为非法，
   * 不换行空格（U+00A0）则按普通空格处理。
   * @param {string} s 原始文本
   * @returns {string} 规整后的文本
   */
  M._stripInvisible = function (s) {
    let out = '';
    for (let i = 0; i < s.length; i++) {
      const c = s.charCodeAt(i);
      if ((c >= 0x200b && c <= 0x200f) || c === 0xfeff) continue;
      out += c === 0xa0 ? ' ' : s[i];
    }
    return out;
  };

  /**
   * 剥掉站点在代码块左侧渲染的行号栏。
   * 判定从严：只有每一行都以 1、2、3…… 连续数字开头且至少两行，才认定是行号栏，
   * 否则原样返回，避免误删正常 JSON 里的数字内容。
   * @param {string} s 文本
   * @returns {string} 去掉行号后的文本
   */
  M._stripLineNumbers = function (s) {
    const lines = String(s || '').split('\n');
    const kept = [];
    let expect = 1;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (!line.trim()) continue;
      const m = /^(\d{1,4})\s?(.*)$/.exec(line.trim());
      if (!m || Number(m[1]) !== expect) return s;
      expect += 1;
      kept.push(m[2]);
    }
    return expect > 2 ? kept.join('\n') : s;
  };

  /**
   * 去掉站点工具条混进正文的装饰行：首行的语言标签、末行的复制按钮文案。
   * @param {string} raw 原始文本
   * @returns {string} 去装饰后的文本
   */
  M._stripCodeDecor = function (raw) {
    const s = this._stripLineNumbers(this._stripInvisible(String(raw || '')));
    const lines = s.split('\n');
    if (lines.length > 1 && /^[A-Za-z0-9_+#.-]{1,12}$/.test(lines[0].trim())) lines.shift();
    while (lines.length && /^(复制代码|复制|copy)$/i.test(lines[lines.length - 1].trim())) lines.pop();
    return lines.join('\n').trim();
  };

  /**
   * 从文本中截取第一个「大括号配平」的 JSON 对象，字符串内的括号不计数。
   * @param {string} s 文本
   * @returns {string} JSON 片段；找不到返回空串
   */
  M._jsonSpan = function (s) {
    const text = String(s || '');
    const start = text.indexOf('{');
    if (start < 0) return '';
    let depth = 0;
    let inStr = false;
    let esc = false;
    for (let i = start; i < text.length; i++) {
      const ch = text[i];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === '\\') esc = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') inStr = true;
      else if (ch === '{') depth += 1;
      else if (ch === '}') {
        depth -= 1;
        if (depth === 0) return text.slice(start, i + 1);
      }
    }
    return '';
  };

  /**
   * 生成候选文本序列：原样、去装饰、截取配平对象。去重后交给逐一解析。
   * @param {string} raw 代码块原始文本
   * @returns {Array<string>} 候选列表
   */
  M._jsonCandidates = function (raw) {
    const out = [];
    const add = function (v) {
      const t = String(v || '').trim();
      if (t && out.indexOf(t) < 0) out.push(t);
    };
    add(raw);
    const cleaned = this._stripCodeDecor(raw);
    add(cleaned);
    add(this._jsonSpan(cleaned));
    return out;
  };

  /**
   * 解析单个候选：先直接解析，失败再修复字符串内裸控制字符后解析一次。
   * @param {string} s 候选文本
   * @returns {Object|null} 解析结果
   */
  M._tryParseJson = function (s) {
    if (!s || s.charAt(0) !== '{') return null;
    try {
      return JSON.parse(s);
    } catch (e) {
      try {
        const fixed = JSON.parse(this._repairJsonControlChars(s));
        if (fixed) D.log('解析修复：裸控制字符已修复后解析成功');
        return fixed || null;
      } catch (e2) {
        return null;
      }
    }
  };

  /**
   * 按候选顺序解析工具调用 JSON，任一候选成功即返回。
   * @param {string} raw 代码块原始文本
   * @returns {Object|null} 解析出的对象
   */
  M._parseToolJson = function (raw) {
    const cands = this._jsonCandidates(raw);
    for (let i = 0; i < cands.length; i++) {
      const obj = this._tryParseJson(cands[i]);
      if (obj) return obj;
    }
    return null;
  };

  /**
   * 判断代码块是否为一次工具调用：内容是 { tool, parameters } 且带 bridge-chat-call 即算。
   * 安全性由调用方保证：只有「助手消息」里的代码块才会被判为工具调用。
   * 容错：首次解析失败时，先修复字符串内裸控制字符再解析一次（见 _repairJsonControlChars）。
   */
  M.parseToolCall = function (block) {
    if (!block || block.type !== 'code') return null;
    // 代码块文本常被站点装饰污染：行号栏、语言标签、复制按钮文案、零宽字符。
    // 直接 JSON.parse 会整块失败，卡片随即退化成普通代码块（千问实测如此）。
    // 故不预设首字符，改为候选提取后逐个尝试：原样 / 去装饰 / 截取配平对象。
    const obj = M._parseToolJson(String(block.code || ''));
    if (!obj) return null;
    if (obj && typeof obj === 'object' && obj.tool && obj.type === 'bridge-chat-call') {
      return { tool: String(obj.tool), parameters: obj.parameters || {} };
    }
    // 原生形态：工具名作唯一顶层键（如 {"run_command": {...}}），不带信封字段。
    // 实测模型会直接以此形态发起调用，此前整体落在判定之外，被当普通代码块
    // 跳过：不建卡、不执行、不回传，链路静默中断（详见 docs/pending-tasks.md）。
    // 守卫：键名必须命中本机工具注册表（this.tools，与 toolSilent 同源），
    // 普通单键 JSON 示例（如 {"name": "张三"}）不受影响。
    if (obj && typeof obj === 'object' && !obj.tool && !obj.type) {
      const keys = Object.keys(obj);
      if (keys.length === 1 && (this.tools || []).some((t) => t && t.name === keys[0])) {
        const v = obj[keys[0]];
        // 普通对象直接作参数包；数组 / 原始值包一层，键名与工具名一致。
        const parameters = (v && typeof v === 'object' && !Array.isArray(v)) ? v : { [keys[0]]: v };
        D.log('原生形态工具调用：' + keys[0]);
        return { tool: keys[0], parameters: parameters };
      }
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
    // 代码块：先整段按 JSON 精确解析（标准形态），失败再退回扫描。
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
    // 其余「带文本的块」一律扫描：语音块漂移成裸 JSON 时，可能落在段落、
    // 标题、引用、列表等任意文本载体里。此前只扫 paragraph，导致落在其它
    // 文本块中的语音块取不到，被误报为「语音缺失」——与后端提取器口径不一致。
    const text = (block.text != null) ? String(block.text) : '';
    if (text) {
      const got = pickVoiceJson(text);
      if (got) return got;
    }
    // 列表块：元素数组，逐项扫描。
    if (block.items && block.items.length) {
      const list = window.AIMirrorDomUtils.toArray(block.items);
      for (let i = 0; i < list.length; i++) {
        const got = pickVoiceJson(String(list[i] == null ? '' : list[i]));
        if (got) return got;
      }
    }
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
