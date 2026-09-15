// 模块：extend/content/02_blocks.js
// 用途：把网页对话 DOM 解析成结构化块（段落 / 标题 / 列表 / 代码 / 引用 / 表格 / 思考），
//       并按站点规则区分用户与 AI 消息。
// 依赖：content/00_state.js（命名空间 A）、lib/dom-utils.js
(function () {
  'use strict';
  const A = window.AIMirrorContent;

  /**
   * 取代码块语言：优先 lang 属性，其次 language-xxx 类名，最后取工具条上的语言名。
   * @param {Element} host 代码块宿主元素
   * @returns {string} 语言名；无法判断返回空串
   */
  A.codeLangOf = function (host) {
    if (!host || !host.getAttribute) return '';
    const attr = host.getAttribute('lang');
    if (attr) return attr;
    const m = /language-([a-zA-Z0-9_+#-]+)/.exec(String(host.className || ''));
    if (m) return m[1];
    const pre = host.matches('pre') ? host : host.querySelector('pre');
    if (pre) {
      const mm = /language-([a-zA-Z0-9_+#-]+)/.exec(String(pre.className || ''));
      if (mm) return mm[1];
    }
    const box = host.closest ? host.closest('.code-no-artifacts') : null;
    if (box) {
      const lp = box.querySelector('.top-outer .language');
      if (lp) return A.textOf(lp);
    }
    return '';
  };

  /**
   * 判断一个元素是否「本质上就是一个代码块」。
   * 关键：代码块外层常包着工具条（语言名 / 复制按钮），这些装饰不算正文，
   * 必须排除，否则整段回答会被误判成一个代码块而丢掉段落文本。
   * @param {Element} el 待判断元素
   * @returns {Element|null} 代码块根节点；不是纯代码块则返回 null
   */
  A.findCodeRoot = function (el) {
    if (!el || el.nodeType !== 1) return null;
    if (el.matches('div.language[lang], pre')) return el;
    const code = el.querySelector('div.language[lang], pre');
    if (!code) return null;
    const BLOCK_SEL = 'p, ul, ol, h1, h2, h3, h4, h5, h6, blockquote, table, li';
    // 找出代码块之外是否还有正文块；有则说明该元素不是纯代码块
    const others = Array.prototype.filter.call(el.querySelectorAll(BLOCK_SEL), function (n) {
      if (code.contains(n) || n.contains(code)) return false;
      if (n.closest && n.closest('.top-outer')) return false;       // 工具条
      if (n.classList && n.classList.contains('language')) return false; // 语言名
      return true;
    });
    return others.length === 0 ? code : null;
  };

  /**
   * 把表格元素解析为二维数组。
   * @param {Element} t 表格元素
   * @returns {Array<Array<string>>} 每行单元格文本
   */
  A.tableRows = function (t) {
    const rows = [];
    Array.prototype.forEach.call(t.querySelectorAll('tr'), function (tr) {
      const cells = [];
      Array.prototype.forEach.call(tr.children, function (c) { cells.push(A.textOf(c)); });
      if (cells.length) rows.push(cells);
    });
    return rows;
  };

  /**
   * 把一个内容节点解析成结构化的块列表（段落 / 标题 / 列表 / 代码 / 引用 / 表格）。
   * @param {Element} node 内容容器
   * @param {Array} out 复用的输出数组（递归时传入）
   * @returns {Array} 块列表
   */
  A.parseBlocks = function (node, out) {
    out = out || [];
    Array.prototype.forEach.call(node.children || [], function (el) {
      if (el.nodeType !== 1) return;
      // chatglm 等站点代码块上方的工具条（语言名 + 复制按钮），不参与正文
      if (el.matches && el.matches('.top-outer')) return;
      // 思考区单独成块处理，禁止在正文解析里再次被当作段落重复收入
      const thinkSel = A.activeProfile().thinking;
      if (thinkSel && el.matches && el.matches(thinkSel)) return;
      const tag = el.tagName;

      const codeHost = A.findCodeRoot(el);
      if (codeHost) {
        const inner = codeHost.matches('pre') ? codeHost : (codeHost.querySelector('pre code') || codeHost.querySelector('code') || codeHost);
        const lang = A.codeLangOf(codeHost) || '';
        const code = A.textOf(inner);
        out.push({ type: 'code', lang: lang, code: code, id: 'c' + A.hashStr(lang + '|' + code) });
        return;
      }
      if (tag === 'P') {
        const t = A.textOf(el);
        if (t) out.push({ type: 'paragraph', text: t });
        return;
      }
      if (/^H[1-6]$/.test(tag)) {
        const t = A.textOf(el);
        if (t) out.push({ type: 'heading', level: Number(tag.charAt(1)), text: t });
        return;
      }
      if (tag === 'UL' || tag === 'OL') {
        const items = [];
        Array.prototype.forEach.call(el.children, function (li) {
          const t = A.textOf(li);
          if (t) items.push(t);
        });
        if (items.length) out.push({ type: 'list', ordered: tag === 'OL', items: items });
        return;
      }
      if (tag === 'BLOCKQUOTE') {
        const t = A.textOf(el);
        if (t) out.push({ type: 'quote', text: t });
        return;
      }
      if (tag === 'TABLE') {
        const rows = A.tableRows(el);
        if (rows.length) out.push({ type: 'table', rows: rows });
        return;
      }
      // 其它容器：递归下钻
      if (el.children.length) { A.parseBlocks(el, out); return; }
      const t = A.textOf(el);
      if (t) out.push({ type: 'paragraph', text: t });
    });
    return out;
  };

  /**
   * 生成块的摘要指纹，用于给代码块算稳定 id。
   * @param {Object} b 块对象
   * @returns {Object} 只含关键字段的摘要
   */
  A.blockDigest = function (b) {
    if (!b) return { type: '', text: '' };
    if (b.type === 'code') return { type: 'code', lang: b.lang || '', code: b.code || '' };
    if (b.type === 'heading') return { type: 'heading', level: b.level, text: b.text || '' };
    if (b.type === 'list') return { type: 'list', ordered: !!b.ordered, items: b.items || [] };
    if (b.type === 'table') return { type: 'table', rows: b.rows || [] };
    return { type: b.type || '', text: b.text || '' };
  };

  /**
   * 给每条消息内的代码块生成带消息指纹 + 块索引的稳定 id。
   * 只按代码内容做指纹在多轮对话中会大量重复：相同工具调用出现在不同轮次时，
   * 旧卡片会被复用，出现“没执行却显示旧结果”的问题。
   * @param {Object} msg 消息对象，就地修改其 blocks 内的 code.id
   */
  A.stampCodeBlockIds = function (msg) {
    const blocks = msg.blocks || [];
    const digest = blocks.map(A.blockDigest);
    const fp = A.hashStr(msg.role + '|' + (msg.name || '') + '|' + JSON.stringify(digest));
    blocks.forEach(function (b, i) {
      if (b.type === 'code') {
        b.id = 'c' + A.hashStr(fp + '|' + i + '|' + (b.lang || '') + '|' + (b.code || ''));
      }
    });
  };

  /**
   * 构造用户消息对象。
   * @param {Element} el 用户消息容器
   * @param {Object} P 站点规则
   * @returns {Object} 消息对象
   */
  A.makeUser = function (el, P) {
    const nameEl = P.userName ? el.querySelector(P.userName) : null;
    const bodyEl = P.userContent ? (el.querySelector(P.userContent) || el) : el;
    return { role: 'user', name: A.textOf(nameEl) || '用户', blocks: A.parseBlocks(bodyEl) };
  };

  /**
   * 构造 AI 消息对象，含思考区与正文区。
   * @param {Element} el AI 消息容器
   * @param {Object} P 站点规则
   * @returns {Object} 消息对象
   */
  A.makeAssistant = function (el, P) {
    const blocks = [];

    // 思考区（GLM 的「深度思考」/ DeepSeek 的「已思考」）单独成块，且只取一次
    const think = P.thinking ? el.querySelector(P.thinking) : null;
    if (think) {
      const area = P.thinkingArea ? (think.querySelector(P.thinkingArea) || think) : think;
      const t = A.textOf(area);
      if (t) blocks.push({ type: 'thinking', text: t });
    }

    // 真正的回答正文。两个坑，缺一不可：
    // 1) 思考区内部往往也有正文容器（GLM 的 .answer-content-wrap /
    //    DeepSeek 的 .ds-markdown），必须排除，否则会把思考内容当正文、
    //    又和上面独立的 thinking 块重复。
    // 2) 一个回答常被拆成多个容器（例如文字一段、代码块另起一段）。
    //    只取第一个会把代码块整段漏掉 —— 表现为「插件记录落后于网页」，
    //    更严重的是：AI 的 tool 代码块提取不到 → 不生成卡片 → 无法执行 →
    //    没有 [TOOL_RESULT] 回传，自愈流程直接断在这里。
    let wraps = [];
    if (P.answerWrap) {
      const host = P.answerContent ? (el.querySelector(P.answerContent) || el) : el;
      Array.prototype.forEach.call(host.querySelectorAll(P.answerWrap), function (w) {
        if (!w.closest(P.thinking)) wraps.push(w);
      });
    }
    if (!wraps.length) {
      // DeepSeek 这类没有 wrap 概念的站点：直接用正文容器选择器。
      // 必须用完整类名精确定位，否则会命中思考区内部的同类容器。
      const c = P.assistantContent ? (el.querySelector(P.assistantContent) || el) : el;
      wraps = [c];
    }
    // 去掉被其它待解析容器包裹的嵌套容器，避免内容重复解析
    wraps = wraps.filter(function (w) { return !wraps.some(function (o) { return o !== w && o.contains(w); }); });
    wraps.forEach(function (w) { A.parseBlocks(w, blocks); });

    const nameEl = P.assistantName ? el.querySelector(P.assistantName) : null;
    return { role: 'assistant', name: A.textOf(nameEl) || 'AI', blocks: blocks };
  };

  /**
   * 结构化提取整段对话：按「站点规则」区分角色与内容块，GLM / DeepSeek 结构完全不同。
   * @param {Element} root 对话容器；缺省为 document
   * @returns {Array} 消息数组
   */
  A.extractBlocks = function (root) {
    const messages = [];
    const base = root || document;
    const P = A.activeProfile();
    const items = base.querySelectorAll(P.item);
    const scopes = items.length ? items : [base];
    const pushedQ = new Set(); // 本轮提取内去重；不可跨调用保留在 DOM 上，否则用户消息会被永久丢弃

    scopes.forEach(function (item) {
      // —— 模式 A：一个消息项就是一条消息，用标记区分角色（DeepSeek）——
      if (!P.split) {
        const isAsst = !!(P.assistantMark && item.querySelector(P.assistantMark));
        messages.push(isAsst ? A.makeAssistant(item, P) : A.makeUser(item, P));
        return;
      }

      // —— 模式 B：一个 item 内同时含「提问」与「回答」两个子块（GLM）——
      // 用户提问：每个对话项各取一次，不依赖写在 DOM 元素上的粘性标记
      const q = item.querySelector(P.userItem);
      if (q && !pushedQ.has(q)) {
        pushedQ.add(q);
        messages.push(A.makeUser(q, P));
      }

      Array.prototype.forEach.call(item.querySelectorAll(P.assistantItem), function (ans) {
        messages.push(A.makeAssistant(ans, P));
      });
    });

    A.log('extractBlocks: 结构化提取到', messages.length, '条消息');
    messages.forEach(A.stampCodeBlockIds);
    return messages;
  };
})();
