// 模块：extend/content/03_bridge.js
// 用途：会话身份识别、结构化对话推送、以及把文本回传到网页 AI 输入框。
// 依赖：content/00_state.js、content/02_blocks.js（extractBlocks）

(function () {
  'use strict';

  // 注：回传粘贴守卫（生成期挂起/空闲冲刷）已拆至 content/03b_paste.js
  //（2026-11-08，原文件 489 行超出仓库 450 行上限，hygiene/quality 拦截）。
  const A = window.AIMirrorContent;

  /**
   * 判断链接是否与当前路径对应。
   * 用 URL 解析把相对 / 绝对 href 统一成 pathname 再比（DeepSeek 的会话项是 <a> 链接）。
   * @param {string} href 链接地址
   * @param {string} path 当前 location.pathname
   * @returns {boolean} 是否匹配
   */
  A.hrefMatchesPath = function (href, path) {
    if (!href || !path) return false;
    if (href === path) return true;
    try {
      return new URL(href, location.href).pathname === path;
    } catch (e) {
      return href.indexOf(path) !== -1;
    }
  };

  /**
   * 找出左侧会话列表中当前被选中的那一项。
   * 不同站点的「会话 id 来源」与「选中项判定」完全不同，全部由 activeProfile() 驱动：
   * - GLM ：URL 带 ?cid=...；选中项是带 .selected 类的 .history-item
   * - DeepSeek：URL 路径为 /a/chat/s/<uuid>；选中项 = href 与当前 location.pathname 一致的 <a>
   * @returns {Element|null} 选中项元素
   */
  A.selectedHistoryItem = function () {
    const P = A.activeProfile();
    if (!P.historyItem) return null;
    // 选择器非法（如配置里写了含空格的属性值又没加引号）时 querySelectorAll 会抛
    // SyntaxError。历史项选择器只服务于「取会话标题」这一辅助信息，绝不能因为
    // 它写错就把整次推送炸掉——推送里的消息体才是主产物。故此处兜住异常，
    // 取不到标题就当没有标题。
    let items;
    try {
      items = document.querySelectorAll(P.historyItem);
    } catch (e) {
      A.warn('selectedHistoryItem: 历史项选择器非法，已忽略（' + P.historyItem + '）：' + (e && e.message));
      return null;
    }
    if (!items.length) return null;
    const path = location.pathname;
    // 优先：href 与当前路径一致（DeepSeek 这类用 <a> 承载会话的站点，完全不依赖易变的哈希类）
    for (let i = 0; i < items.length; i++) {
      const href = items[i].getAttribute && items[i].getAttribute('href');
      if (A.hrefMatchesPath(href, path)) return items[i];
    }
    // 其次：带选中标记类（GLM 的 .selected）
    if (P.historySelectedMark) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].matches && items[i].matches(P.historySelectedMark)) return items[i];
      }
    }
    return null;
  };

  /**
   * 取当前会话 id。
   * @returns {string} 会话 id；无法判断返回空串
   */
  A.getConversationId = function () {
    const P = A.activeProfile();
    // 会话 id 只从 URL 提取（各站正则不同，写在 profile 里）。
    // 不使用「左侧选中项标题指纹」作为退路：标题文本会随未读标记、时间等变化，
    // 同一会话刷新后会算出不同指纹，存档键随之漂移，导致历史与卡片执行状态
    // 读不回来。取不到 id 时返回空串，由上层落到 __default__，
    // 待 URL 给出真实 id 后再把 __default__ 的记录迁移过去。
    if (P.convIdUrl) {
      const m = new RegExp(P.convIdUrl).exec(location.href);
      if (m && m[1]) return 'cid:' + m[1];
    }
    return '';
  };

  /**
   * 取当前会话标题（截断到 80 字）。
   * @returns {string} 标题；无选中项返回空串
   */
  A.getConversationTitle = function () {
    const sel = A.selectedHistoryItem();
    return sel ? A.textOf(sel).slice(0, 80) : '';
  };

  /**
   * 结构化提取当前对话并推送给对话框。
   * 每次推送都重新算会话 id，避免切会话后内容仍被归到上一个会话名下。
   * @param {boolean} force 是否强制推送（忽略内容未变化判断）
   * @param {string} [reason] 触发来源：'generate'（AI 新增对话）/ 
   * 'scroll'（可视区滚动）/ 'switch'（切换会话）/ 'manual'（手动解析）。
   * 仅作标签透传给消费端，不改变推送内容本身。
   */
  A.sendPage = function (force, reason) {
    // 面板未打开：不解析也不推送。打开时会由 activate() 主动补一次全量解析。
    if (!A.state.active) return;
    if (!A.state.containerEl) return;

    const convId = A.getConversationId();
    const convChanged = !!convId && convId !== A.state.currentConvId;
    if (convChanged) A.state.currentConvId = convId;

    const messages = A.extractBlocks(A.state.containerEl);
    if (!messages.length) {
      // 空快照不锁死：补发会话身份同步并排递增复查，等 DOM 挂载后重推（实现见 03d）。
      A.onEmptySnapshot(convId, reason);
      return;
    }
    // 已拿到非空快照：作废本会话仍在排队的空快照复查。
    A.cancelEmptyRetry();

    // 快速去重键：按「原始解析结果」先算一次，命中即返回，避免滚动时反复做
    // 图片转换这类重活。blob 地址在同一页面会话内稳定，用它做第一道闸可靠。
    const rawKey = convId + '|' + JSON.stringify(messages);
    if (!force && !convChanged && rawKey === A.state.lastRawKey) return;
    A.state.lastRawKey = rawKey;
    A.state.lastPageConvId = convId;

    // 图片归一化：把 blob: / http(s) 地址转成自包含的 dataURL，
    // 使抽屉镜像、抽屉消息列表、服务端三处都能取到同一张图。
    // 无图片时同步回调，行为与改造前一致。
    A.normalizeImageBlocks(messages, function (msgs) {
      // 正式去重键：用「图片已归一化」的最终内容算。
      // 不能用归一化前的 rawKey 锁死：首次推送若 toDataUrl 失败（跨域、blob 失效），
      // 内容里留的是 blob 地址；下次推送原始内容相同，rawKey 命中即返回，
      // 那张图永远失去第二次转换机会，表现为图片时有时无。
      // 用最终内容做键，转换成功后键值随之变化，能正常再推一次。
      const finalKey = convId + '|' + JSON.stringify(msgs);
      if (!force && !convChanged && finalKey === A.state.lastPageKey) return;
      A.state.lastPageKey = finalKey;
      // 逐条算消息指纹并打印：与 dialog 侧的 msgId 同源，便于对齐两边日志、
      // 区分「同一会话的多次推送」（仅凭消息条数无法分辨）。
      const fpList = msgs.map(function (m) {
        return window.AIMirrorDomUtils.messageFingerprint(m);
      });
      // 视口是否停在最新处：仅滚动轮次的自动执行复检需要，其余来源仅作日志
      const atBottom = A.isAtBottom();
      A.log('sendPage: 推送结构化对话 force=' + !!force,
        '会话=' + convId, '消息数=' + msgs.length,
        'ids=' + JSON.stringify(fpList), 'atBottom=' + atBottom);
      A.post({
        type: 'page_blocks',
        messages: msgs,
        page_url: location.href,
        siteKey: A.state.siteKey,
        // 按站点隔离数据与设置
        profileId: A.state.profileId,
        conversationId: convId,
        conversationTitle: A.getConversationTitle(),
        reason: reason || 'manual',            // 触发来源标签，供消费端分流
        atBottom: atBottom,                    // 视口是否在底部（滚动轮次自动执行复检用）
        // 推送时刻 AI 是否仍在生成：抽屉侧据此拦截自动执行与回传。
        // 抽屉与内容脚本分离，拿不到本页的生成态，只能随推送一并带过去。
        isGenerating: !!A.state.isGenerating
      });
    });
  };

  /**
   * 找到网页 AI 的输入框（选择器按站点规则取）。
   * @returns {Element|null} 输入框元素
   */
  A.findInputBox = function () {
    const sel = A.activeProfile().inputSelector;
    if (!sel) return null;
    return document.querySelector(sel);
  };

  /**
   * 自动回传：把文本写回网页 AI 的输入框并触发发送。
   * 输入框选择器按站点规则取（glm / deepseek 的 DOM 结构不同），
   * 设值走原生 setter（兼容 Vue/React 的响应式），再派发 input 事件，
   * 等状态同步后派发 Enter 键事件触发发送。
   * @param {string} text 要回传的文本
   */

  /**
   * 把文本一次性写入输入框（复制粘贴式写值，非逐字输入）。
   * 按输入框类型分流：textarea / input 用原生 setter；富文本编辑器用 paste 事件。
   * 抽成公共函数，供「纯文本」与「图文合一」两条路径复用。
   * @param {Element} ta 输入框
   * @param {string} text 文本
   * @returns {boolean} 是否已写入
   */
  A.writeInputValue = function (ta, text) {
    if (!ta) return false;
    const value = String(text || '');
    ta.focus();
    // 富文本编辑器（contenteditable）：千问的 Slate、元宝的 Quill 都属此类。
    // 它们没有 value 属性，原生 setter 会直接抛 Illegal invocation，必须走 paste 事件。
    if (A.isRichEditor(ta)) return A.writeRichEditor(ta, value);
    // 传统表单控件：用原生 setter 写值，触发框架的响应式更新
    try {
      const desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')
        || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
      if (!desc || !desc.set) return false;
      desc.set.call(ta, value);
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      return true;
    } catch (e) {
      A.warn('writeInputValue: 原生 setter 写入失败，改走 paste：' + (e && e.message));
      return A.writeRichEditor(ta, value);
    }
  };

  // 富文本编辑器相关函数（isRichEditor / writeRichEditor / clearRichEditor）
  // 已拆至 content/03c_rich_editor.js（原文件超出 450 行上限）。
  // 同挂 A 命名空间，本文件在运行期按名字调用，不依赖加载先后。

  /**
   * 自动回传：把文本写回网页 AI 的输入框并触发发送。
   * 输入框选择器按站点规则取（glm / deepseek 的 DOM 结构不同），
   * 设值走原生 setter（兼容 Vue/React 的响应式），再派发 input 事件，
   * 等状态同步后派发 Enter 键事件触发发送。
   * @param {string} text 要回传的文本
   * @param {boolean} [autoSend] 是否写完后自动回车发送；false 表示只写值
   * （图文合一流程自行控制发送时机，避免图文各发一条）
   */
  A.pasteToWebpageAI = function (text, autoSend) {
    const ta = A.findInputBox();
    if (!ta) {
      A.warn('pasteToWebpageAI: 未找到网页 AI 输入框');
      A.post({ type: 'auto_send_result', ok: false, msg: '未找到网页 AI 输入框' });
      return;
    }

    // 守卫一：AI 生成中不得写输入框——写值本身就会打断输出流。
    if (A.state.isGenerating) {
      A._suspendPaste({ kind: 'text', text: text, autoSend: autoSend, label: '文本回传' });
      return;
    }

    A.writeInputValue(ta, text);

    // 只写值不发送：交给调用方（图文合一）统一回车
    if (autoSend === false) return;

    // 两步走：先等发送按钮就绪，再延迟 500ms，然后回车发送。
    // 就绪信号见 waitSendReady：档案配了 sendButtonDisabledMark 的站点等类名消失，
    // 未配置的站点仅确认按钮存在，其余由延时兜底（比读输入框值可靠：值是
    // 原生 setter 写入的，写入即相等，证明不了框架状态已更新）。
    A.waitSendReady(function () {
      setTimeout(function () {
        // 守卫二：写值与回车之间隔了 waitSendReady（最长 3 秒）+ 500ms，
        // 期间 AI 可能已开始生成——此刻回车同样会打断输出。值已在输入框里，
        // 不能整体重放（会写出两份），故只挂起「补回车」条目（kind='enter_only'），
        // 冲刷时先确认输入框仍有内容，再重新取输入框引用补一次回车。
        if (A.state.isGenerating) {
          A._suspendPaste({ kind: 'enter_only', label: '文本回传（回车前拦截）' });
          return;
        }
        A.pressEnter(ta);
      }, 500);
    });
  };

  /**
  /**
   * 轮询等待发送按钮就绪：就绪即回调，超时（3 秒）也回调。
   *
   * 就绪信号来自站点档案的 sendButtonDisabledMark：发送按钮未就绪时带的
   * 类名，就绪后该类消失。这是框架自己给出的可靠信号，比读输入框值靠谱
   * ——值是用原生 setter 直接写进去的，写入即相等，证明不了框架内部状态。
   * 档案未配置该字段（如 glm / wenxin）时跳过禁用检查，仅检查按钮存在，
   * 由后续延时兜底，与站点多态原则一致：不再共享代码里写死任何站点类名。
   * @param {Function} done 就绪（或超时）后的回调
   */
  A.waitSendReady = function (done) {
    const profile = A.activeProfile();
    const sel = profile.sendButton;
    // 站点没配发送按钮选择器：无从判断，直接放行，由后续延时兜底。
    if (!sel) { done(); return; }
    const mark = profile.sendButtonDisabledMark || '';
    const deadline = Date.now() + 3000;
    (function check() {
      let btn = null;
      try { btn = document.querySelector(sel); } catch (e) { btn = null; }
      // 按钮不存在，或（站点有禁用标记时）仍带该类：视为未就绪，继续等
      const disabled = !btn || (mark && btn.className && String(btn.className).indexOf(mark) >= 0);
      if (!disabled || Date.now() > deadline) { done(); return; }
      setTimeout(check, 100);
    })();
  };
  /**
   * 派发 Enter 键，触发网页 AI 发送。
   * @param {Element} ta 输入框
   */
  A.pressEnter = function (ta) {
    const key = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true };
    ta.dispatchEvent(new KeyboardEvent('keydown', key));
    ta.dispatchEvent(new KeyboardEvent('keyup', key));
  };

  /**
   * 把图片贴进网页 AI 输入框并发送。
   * 做法：把 dataURL 转成 File，构造带该文件的 DataTransfer，
   * 再在输入框上派发 paste 事件——多数支持图片上传的输入框会据此接收图片。
   * 图片写入依赖站点实现，失败时回传提示，由用户手动粘贴。
   * @param {string} dataUrl 图片 dataURL
   */

  // MIME → 扩展名映射：决定附件文件名，图片与文本各按真实类型命名
  const MIME_EXT = {
    'image/png': 'png', 'image/jpeg': 'jpg', 'image/gif': 'gif',
    'image/webp': 'webp', 'image/bmp': 'bmp',
    'text/plain': 'txt', 'application/json': 'json', 'text/markdown': 'md'
  };

  /**
   * 把单个 dataURL 转成 File 对象；解析失败返回 null。
   * 图片与文本同一套转换：文本附件按 txt 命名，使 AI 收到的是文件而非正文。
   * @param {string} dataUrl dataURL（图片或文本）
   * @param {number} idx 序号，用于无文件名时兜底命名
   * @param {string} [name] 指定文件名（如原文件名），缺省按类型生成
   */
  A._dataUrlToFile = function (dataUrl, idx, name) {
    try {
      const parts = String(dataUrl).split(',');
      const mime = (parts[0].match(/:(.*?);/) || [])[1] || 'image/png';
      const bin = atob(parts[1] || '');
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const ext = MIME_EXT[mime] || (mime.indexOf('jpeg') >= 0 ? 'jpg' : 'png');
      const fileName = name || ('file_' + idx + '.' + ext);
      return new File([arr], fileName, { type: mime });
    } catch (e) {
      return null;
    }
  };

  /**
   * 底层：把一组 File 逐个派发 paste 事件贴进输入框，随后写入文字并回车一次。
   *
   * 只做「贴文件 + 写文字 + 发送」这一件机械事，不含任何业务判断。
   * 图片与文本文件各自的上层入口负责构造 File，互不感知对方语义。
   * @param {File[]} files 待粘贴的文件列表
   * @param {string} text 随附件写入输入框的文字（通常是精简标记，可空）
   * @param {string} label 日志与提示用的名称（如「图片」「文件」）
   */
  A._pasteFilesToWebpageAI = function (files, text, label) {
    // 守卫三：AI 生成中不得贴附件——「逐个贴文件（800ms/个）+ 等 1.5 秒 + 写文字 +
    // 回车」链路长达数秒，全程都会干扰输出。文件尚未贴入，挂起整体重放
    //（kind='files'，File 数组为内存引用，冲刷时直接重调本函数即可）。
    if (A.state.isGenerating) {
      A._suspendPaste({ kind: 'files', files: files, text: text, label: label });
      return;
    }

    const ta = A.findInputBox();
    if (!ta) {
      A.warn('_pasteFilesToWebpageAI: 未找到网页 AI 输入框');
      A.post({ type: 'auto_send_result', ok: false, msg: '未找到网页 AI 输入框' });
      return;
    }
    const list = (files || []).filter(Boolean);
    if (!list.length) {
      A.post({ type: 'auto_send_result', ok: false, msg: '没有可粘贴的' + label });
      return;
    }

    try {
      // 逐个粘贴，而不是一次全塞。
      // 原因：部分站点（如 DeepSeek）的粘贴处理只取剪贴板里的第一个文件，
      // 一次塞多个最终只会成一个。改成逐个单独派发 paste 事件、留出间隔，
      // 让每个都各自被接收一次，从而累积成多个。
      const GAP = 800;   // 每个文件之间的间隔（毫秒）
      const TAIL = 1500; // 全部贴完后、写文字之前的等待（等预览/上传就绪）
      ta.focus();
      let idx = 0;
      const step = function () {
        if (idx >= list.length) {
          // 全部贴完：等预览就绪后写文字，再等发送按钮就绪、回车发送一次
          setTimeout(function () {
            // 贴文件是异步过程（逐个间隔 + 收尾等待），期间站点可能重建输入框，
            // 函数开头取的 ta 会脱离 DOM，导致文字写进已不在页面的元素，
            // 消息只剩附件而无 bridge-chat-res 标记，被镜像端误判为用户发言。
            // 故写文字与回车前，重新查找当前真实输入框（查不到再退回旧引用）。
            const taNow = A.findInputBox() || ta;
            if (text) A.writeInputValue(taNow, text);
            A.waitSendReady(function () {
              setTimeout(function () {
                if (A.state.isGenerating) {
                  // 守卫四：附件逐个贴入（800ms/个）+ 1.5 秒收尾 + waitSendReady，
                  // 链路数秒，途中 AI 可能已开始生成。附件已在输入框预览中，
                  // 整体重放会把同一批附件再贴一遍——只挂起「补回车」条目，
                  // 冲刷时重新取输入框引用、确认仍有内容后补一次回车。
                  A._suspendPaste({ kind: 'enter_only', label: (label || '附件') + '回传（回车前拦截）' });
                  return;
                }
                A.pressEnter(taNow);
              }, 300);
            });
          }, TAIL);
          return;
        }
        const f = list[idx];
        idx++;
        const dt = new DataTransfer();
        dt.items.add(f);
        ta.focus();
        ta.dispatchEvent(new ClipboardEvent('paste', {
          clipboardData: dt, bubbles: true, cancelable: true
        }));
        setTimeout(step, GAP);
      };
      step();
      A.post({ type: 'auto_send_result', ok: true, msg: text ? '已尝试粘贴图文并发送' : '已尝试粘贴' + label + '并发送' });
    } catch (e) {
      A.warn('_pasteFilesToWebpageAI 失败', e && e.message);
      A.post({ type: 'auto_send_result', ok: false, msg: '粘贴' + label + '失败：' + (e && e.message) });
    }
  };

  /**
   * 把一或多张图片贴进网页 AI 输入框并发送，可附一段文字。
   * 只负责把图片 dataURL 转成图片 File，随后交给底层粘贴。
   * @param {string|string[]} dataUrlOrList 单张 dataURL 或 dataURL 数组
   * @param {string} text 随图文字（可空）
   */
  A.pasteImageToWebpageAI = function (dataUrlOrList, text) {
    const list = Array.isArray(dataUrlOrList) ? dataUrlOrList : (dataUrlOrList ? [dataUrlOrList] : []);
    const files = [];
    for (let i = 0; i < list.length; i++) {
      files.push(A._dataUrlToFile(list[i], i, ''));
    }
    A._pasteFilesToWebpageAI(files, text, '图片');
  };

  /**
   * 把文本文件作为附件贴进网页 AI 输入框并发送，可附一段文字。
   * 与图片各自独立：入参是文件信息（内容 dataURL、文件名、MIME），
   * 只负责构造文件并交给底层粘贴，不关心图片来源与截图逻辑。
   * @param {Object} fileInfo { content, name, mime }
   * @param {string} text 随附件文字（可空）
   */
  A.pasteFileToWebpageAI = function (files, text) {
    // files 为现成的 File 数组：整文件来自源文件原始字节，分段来自片段解码，均未再编码
    const list = Array.isArray(files) ? files.filter(function (f) { return f instanceof File; }) : [];
    if (!list.length) {
      A.post({ type: 'auto_send_result', ok: false, msg: '没有可粘贴的文件' });
      return;
    }
    A._pasteFilesToWebpageAI(list, text, '文件');
  };
})();
