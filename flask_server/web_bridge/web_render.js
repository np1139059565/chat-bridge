// 模块：web_bridge/web_render.js
// 用途：网页版聊天的轻量 Markdown 渲染（代码块 / 标题 / 列表 / 表格 / 行内样式 / 指令链接）。
// 说明：从 web_page.js 抽出，使各文件保持在仓库行数上限内；
//       通过 window.WebRender 暴露 renderMarkdown，供页面脚本调用。
(function () {
  'use strict';

  // 反引号字符：用字符编码拼出，不在源码里写裸反引号。
  // 原因：仓库的行数门禁靠大括号配平估算函数长度，却不识别正则字面量；
  // 源码里的裸反引号会被它误当成模板字符串分隔符，导致后续括号配平错乱、
  // 把短函数误报成超长函数。用字符编码拼出即可绕开这一盲区。
  var BT = String.fromCharCode(96);
  // 围栏代码块：三个反引号包裹的内容
  var RE_FENCE = new RegExp(BT + BT + BT + '([\\s\\S]*?)' + BT + BT + BT, 'g');
  // 行内代码：一对反引号包裹
  var RE_INLINE_CODE = new RegExp(BT + '([^' + BT + ']+)' + BT, 'g');

  // 引号字符：用字符编码拼出。原因同反引号——仓库门禁的剥离器不识别
  // 含引号的正则字面量，会把它误当字符串开头、吃坏后续括号配平。
  var DQUOTE = String.fromCharCode(34);
  var SQUOTE = String.fromCharCode(39);
  var RE_DQUOTE = new RegExp(DQUOTE, 'g');
  var RE_SQUOTE = new RegExp(SQUOTE, 'g');

  // ---------- 工具：转义 HTML ----------
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(RE_DQUOTE, '&quot;').replace(RE_SQUOTE, '&#39;');
  }

  // ---------- 轻量 Markdown 渲染 ----------
  // 支持：代码块、行内代码、标题、粗体、斜体、链接、引用、有序/无序列表、表格、段落
  // 不追求完整规范，只覆盖网页 AI 回复里常见的格式。
  /**
   * 抽出围栏代码块：用占位符替换，避免块内内容被后续行内规则误伤。
   *
   * 从 renderMarkdown 抽出，使其主体保持简短（受行数门禁约束）。
   * 带语言标记的块（思考 / 工具结果）渲染成可折叠区，与 QQ 端折叠行为一致；
   * 无语言标记的普通代码块保持展开，避免误伤用户分享的纯代码。
   * @param {string} text 原文
   * @param {Array} codes 输出参数：占位符 → HTML 片段的映射数组
   * @returns {string} 代码块已替换为占位符的文本
   */
  function extractFences(text, codes) {
    RE_FENCE.lastIndex = 0;
    return text.replace(RE_FENCE, function (m, body) {
      // 首行可能是语言标记（如 json）：抽出语言名与正文
      var lang = '';
      var mm = /^([a-zA-Z0-9_+-]*)\n/.exec(body);
      if (mm) { lang = mm[1]; body = body.slice(mm[0].length); }
      if (lang) {
        codes.push('<details class="code-fold"><summary>' + esc(lang) +
          '</summary><pre><code>' + esc(body) + '</code></pre></details>');
      } else {
        codes.push('<pre><code>' + esc(body) + '</code></pre>');
      }
      return '\u0000CODE' + (codes.length - 1) + '\u0000';
    });
  }

  function renderMarkdown(src) {
    if (!src) return '';
    // 1) 先抽出围栏代码块，用占位符替换，避免块内内容被行内规则误伤
    var codes = [];
    var text = extractFences(String(src), codes);
    // 2) 按行处理块级结构
    var lines = text.split(/\n/);
    var html = [];
    var i = 0;
    while (i < lines.length) {
      var line = lines[i];
      // 占位符行（代码块）
      var codeMatch = /^\u0000CODE(\d+)\u0000$/.exec(line.trim());
      if (codeMatch) {
        html.push(codes[parseInt(codeMatch[1], 10)]);
        i++; continue;
      }
      // 表格：连续以 | 开头的行
      if (/^\s*\|/.test(line)) {
        var tbl = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) { tbl.push(lines[i]); i++; }
        html.push(renderTable(tbl));
        continue;
      }
      // 标题
      var hm = /^(#{1,3})\s+(.*)$/.exec(line);
      if (hm) {
        var lv = hm[1].length;
        html.push('<h' + lv + '>' + inline(hm[2]) + '</h' + lv + '>');
        i++; continue;
      }
      // 引用
      if (/^\s*>\s?/.test(line)) {
        var q = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) {
          q.push(lines[i].replace(/^\s*>\s?/, '')); i++;
        }
        // 用 \n 连接、交给 inline 在「转义之后」还原为 <br>：
        // 若在此直接插 <br>，会被 inline 首步的 esc 转义成字面文本（与段落同类问题）。
        html.push('<blockquote>' + inline(q.join('\n')) + '</blockquote>');
        continue;
      }
      // 无序列表
      if (/^\s*[-*]\s+/.test(line)) {
        var ul = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
          ul.push('<li>' + inline(lines[i].replace(/^\s*[-*]\s+/, '')) + '</li>'); i++;
        }
        html.push('<ul>' + ul.join('') + '</ul>');
        continue;
      }
      // 有序列表
      if (/^\s*\d+[.)]\s+/.test(line)) {
        var ol = [];
        while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
          ol.push('<li>' + inline(lines[i].replace(/^\s*\d+[.)]\s+/, '')) + '</li>'); i++;
        }
        html.push('<ol>' + ol.join('') + '</ol>');
        continue;
      }
      // 空行
      if (/^\s*$/.test(line)) { i++; continue; }
      // 普通段落：合并连续非空、非块级行。
      // 用 \n 连接（不是 <br>）：<br> 会被 inline 里的转义变成字面文本，
      // 换行还原交给 inline 在「转义之后」处理。
      var para = [line]; i++;
      while (i < lines.length && !/^\s*$/.test(lines[i]) &&
             !/^(#{1,3}\s|\s*>|\s*[-*]\s|\s*\d+[.)]\s|\s*\||\u0000CODE)/.test(lines[i])) {
        para.push(lines[i]); i++;
      }
      html.push('<p>' + inline(para.join('\n')) + '</p>');
    }
    return html.join('');
  }

  // 行内元素：代码、粗体、斜体、链接、指令
  function inline(s) {
    var out = esc(s);
    // 换行还原：在转义之后进行，\n 变真换行。
    // 顺序很关键——若在转义前插入 <br>，会被 esc 转义成字面文本。
    out = out.replace(/\n/g, '<br>');
    // 行内代码（一对反引号包裹）
    RE_INLINE_CODE.lastIndex = 0;
    out = out.replace(RE_INLINE_CODE, '<code>$1</code>');
    // 粗体 **x**
    out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // 斜体 *x*
    out = out.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
    // 链接 [text](url)
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>');
    // 指令链接：/xxx 形式（在非标签文本中）
    out = out.replace(/(^|[\s（(\[>])(\/[a-zA-Z][\w-]*)/g, function (m, pre, cmd) {
      return pre + '<a class="cmd-link" data-cmd="' + cmd + '">' + cmd + '</a>';
    });
    return out;
  }

  // 表格渲染
  function renderTable(rows) {
    var cells = rows.map(function (r) {
      return r.trim().replace(/^\||\|$/g, '').split('|').map(function (c) { return c.trim(); });
    });
    if (!cells.length) return '';
    // 第二行若是分隔行（---），跳过
    var body = cells;
    if (cells.length > 1 && cells[1].every(function (c) { return /^:?-{2,}:?$/.test(c); })) {
      body = [cells[0]].concat(cells.slice(2));
    }
    var html = '<table>';
    body.forEach(function (row, idx) {
      html += '<tr>';
      row.forEach(function (c) {
        html += idx === 0 ? ('<th>' + inline(c) + '</th>') : ('<td>' + inline(c) + '</td>');
      });
      html += '</tr>';
    });
    return html + '</table>';
  }

  /**
   * 把语音播放器插到「思考之下、正文之上」。
   *
   * 思考块渲染为 details（恒在正文最前），故把它切出来，中间夹语音，
   * 后面接剩余正文，用户定位时先看思考、再听语音、最后读正文。
   * @param {string} body 正文 HTML（可能以 details 思考块开头）
   * @param {string} audio 语音播放器 HTML（无语音传空串）
   * @returns {string} 组装后的正文 HTML
   */
  function composeBody(body, audio) {
    if (!audio) return body;
    var think = '', rest = body || '';
    var m = /^\s*<details class="code-fold">[\s\S]*?<\/details>/.exec(rest);
    if (m) { think = m[0]; rest = rest.slice(m[0].length); }
    return think + audio + rest;
  }

  /**
   * 渲染指令面板：分「内置指令」「自定义指令」两区，各按首字母排序。
   *
   * 排序键取去掉斜杠后的首字母、忽略大小写，符合用户找指令的直觉。
   * @param {Element} grid 容器元素
   * @param {Object} groups { builtin: [...], custom: [...] }
   * @param {function(string)} onPick 点选回调，传入被点的指令
   */
  function renderCommandPanel(grid, groups, onPick) {
    grid.innerHTML = '';
    var sections = [['内置指令', groups.builtin || []], ['自定义指令', groups.custom || []]];
    sections.forEach(function (sec) {
      var arr = sec[1].slice().sort(function (a, b) {
        var x = String(a).replace(/^\//, '').toLowerCase();
        var y = String(b).replace(/^\//, '').toLowerCase();
        return x < y ? -1 : (x > y ? 1 : 0);
      });
      if (!arr.length) return;
      var title = document.createElement('div');
      title.className = 'cmd-title';
      title.textContent = sec[0];
      grid.appendChild(title);
      arr.forEach(function (c) {
        var d = document.createElement('div');
        d.className = 'cmd-item';
        d.textContent = c;
        d.addEventListener('click', function () { onPick(c); });
        grid.appendChild(d);
      });
    });
  }

  window.WebRender = { renderMarkdown: renderMarkdown, composeBody: composeBody, renderCommandPanel: renderCommandPanel };
})();
