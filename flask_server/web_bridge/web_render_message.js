/* ============================================================
 * 网页版机器人 —— 单条消息渲染
 * 职责：把一条消息渲染成 DOM 节点，倒序插入列表；处理图片、语音与消息 key。
 *
 * 为什么单独成文件：渲染要处理图片单张/多张、图文混排、语音播放器绑定、
 * 倒序与懒加载两种插入位置，分支多且与轮询、发送等流程无关。
 * 抽出来既便于单独阅读，也避免主模块超出行数上限。
 *
 * 依赖由 init 注入，本模块不反向读取主模块的内部变量。
 * ============================================================ */
(function () {
  'use strict';

  // 运行时依赖（init 时注入）
  var listEl = null;      // 消息列表容器
  var seen = null;        // 已渲染消息 id 表，防重复
  var fmtTime = null;     // 时间格式化函数

  /**
   * 初始化：注入依赖。
   *
   * @param {Object} opts { listEl, seen, fmtTime }
   *   listEl  —— 消息列表容器（DOM 元素）
   *   seen    —— 已渲染 id 映射对象，本模块直接读写它
   *   fmtTime —— 把时间戳格式化为 HH:MM 的函数
   */
  function init(opts) {
    opts = opts || {};
    listEl = opts.listEl || null;
    seen = opts.seen || {};
    fmtTime = opts.fmtTime || function () { return ''; };
  }

  /**
   * 组装消息正文 HTML：图片、图文混排或纯文本三种情形。
   *
   * @param {Object} m 消息对象
   * @returns {string} 正文 HTML
   */
  function buildBody(m) {
    var renderMarkdown = window.WebRender.renderMarkdown;
    // 带 image 字段：渲染真实图片（网页发图 / 指令结果截图等），点击可看大图。
    // image 可能是单个文件名（字符串）或多张（数组），统一成数组处理。
    if (m.image && (!Array.isArray(m.image) || m.image.length)) {
      var imgs = Array.isArray(m.image) ? m.image : [m.image];
      var html = imgs.map(function (name) {
        var u = '/api/web/image-file/' + encodeURIComponent(name);
        // 不套 <a target="_blank">：新开标签页会重新请求图片。
        // 改为页面内浮层看大图，直接复用已加载的图片（同 src 走缓存，零请求）。
        return '<img class="msg-img" src="' + u + '" alt="图片">';
      }).join('');
      if (m.text && m.text !== '[截图]' && m.text !== '[图片]') html += renderMarkdown(m.text);
      return html;
    }
    if (m.kind === 'web-image' || m.text === '[图片]') {
      // 图文消息：图片标记 + 文字一并渲染，不能只画标记把文字吞掉。
      // 纯图片时 text 是「[图片]」，只显示标记；带文字时把文字正常渲染出来。
      var label = (m.text && m.text !== '[图片]') ? renderMarkdown(m.text) : '';
      return '<span class="img-badge">🖼 图片</span>' + label;
    }
    return renderMarkdown(m.text || '');
  }

  /**
   * 渲染单条消息并插入列表。
   *
   * @param {Object}  m         消息对象
   * @param {boolean} allowAuto 是否允许该条语音自动播放。
   *   历史加载（首次铺屏）传 false：已存在的语音不该一进页面就自动播；
   *   增量拉取传 true：解锁后新到的语音才自动播。
   * @param {boolean} atBottom  为真时插到列表末尾（懒加载更早的消息用）
   * @returns {boolean} 是否真的渲染了（已渲染过或数据无效返回 false）
   */
  function render(m, allowAuto, atBottom) {
    if (!m || seen[m.id]) return false;
    seen[m.id] = true;
    // 维护「DOM 中最早一条」的锚点：懒加载据此向前翻页
    if (window.WebDom) window.WebDom.note(m.seq);
    var role = m.role || 'ai';
    // 角色 → 显示名与样式类。system 为指令回执（如 /help 输出），单独配色。
    var who = role === 'user' ? '我' : (role === 'ai' ? 'AI' : (role === 'system' ? '系统' : '工具'));
    var cls = role === 'user' ? 'user' : (role === 'ai' ? 'ai' : (role === 'system' ? 'system' : 'tool'));
    var el = document.createElement('div');
    el.className = 'msg ' + cls;
    el.setAttribute('data-seq', m.seq);
    // 语音：交给独立语音模块渲染（已合成为播放器，未合成为「生成」按钮）
    var audio = window.WebVoice ? window.WebVoice.renderAudio(m) : '';
    // 消息 key（pid-id）：显示在角色名旁，供逐条核对消息块是否完整、有无缺块。
    // 旧数据可能没有该字段，缺省不显示，避免出现空标记。
    var keyTag = m.key ? '<span class="msg-key" title="消息 key（pid-id）">' + m.key + '</span>' : '';
    // 语音位置：思考之下、正文之上。组装细节见 WebRender.composeBody。
    el.innerHTML =
      '<div class="who">' + who + keyTag + '<span class="time">' + fmtTime(m.ts) + '</span></div>' +
      '<div class="body">' + window.WebRender.composeBody(buildBody(m), audio) + '</div>';
    // 倒序：最新插入到列表最前面；懒加载更早的消息时插到末尾
    if (atBottom) {
      listEl.appendChild(el);
    } else if (listEl.firstChild) {
      listEl.insertBefore(el, listEl.firstChild);
    } else {
      listEl.appendChild(el);
    }
    // 语音播放器：绑定解锁与自动播放（历史语音不自动播，见 allowAuto）
    var au = el.querySelector('audio');
    if (au && window.WebVoice) window.WebVoice.bind(au, !!allowAuto);
    return true;
  }

  window.WebMessage = { init: init, render: render };
})();
