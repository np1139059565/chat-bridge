// 模块：extend/content/08_remote_log.js
// 用途：把内容脚本的诊断日志一并送到本地工具服务，落到后端日志文件。
//
// 为什么需要：诊断日志若只打浏览器控制台，用户得手动开控制台才能看到，
// 手机端更是几乎不可能。送一份到后端后，排查时直接看后端日志即可。
//
// 与 web_clientlog.js 的关系：那个模块服务网页版聊天页（/web-bot），
// 本模块服务内容脚本（注入到各网页 AI 站点）。两者都往 /api/web/client_log 送，
// 后端按 tag 区分来源。
//
// 设计取舍：
//   · 缓冲 + 定时批量：逐条发会形成请求风暴，把 Flask 的请求线程占满。
//   · 失败不重试、直接丢：日志是诊断手段，不能反过来拖累主流程；
//     丢了顶多少一条记录，卡住主线程才是真问题。
//   · 地址可配：内容脚本不知道后端端口，需由外部注入（见 05_index.js）。
(function () {
  'use strict';
  const A = window.AIMirrorContent;
  if (!A) {
    console.error('[AI-Mirror][content] [远程日志] 命名空间不存在，模块中止');
    return;
  }

  // 后端地址：由 05_index.js 从扩展存储读出后注入
  let baseUrl = '';
  // 待发缓冲
  let buf = [];
  // 定时器
  let timer = null;
  // 冲刷间隔：1 秒一次，与网页版日志模块保持一致
  const FLUSH_MS = 1000;
  // 单批上限
  const MAX_BATCH = 50;

  /**
   * 设置后端地址。
   * @param {string} url 形如 http://127.0.0.1:5000
   */
  function setBaseUrl(url) {
    baseUrl = String(url || '').replace(/\/+$/, '');
  }

  /**
   * 冲刷缓冲：把积累的日志交给后台转发。
   *
   * 为什么不在内容脚本里直接 fetch：
   *   内容脚本跑在网页的源里（如 https://chat.deepseek.com），
   *   而工具服务是 http://127.0.0.1:5000。HTTPS 页面请求 HTTP 接口
   *   会被浏览器的混合内容策略直接拦截，请求根本发不出去。
   *   这解释了「工具接口能通、日志接口不通」——工具请求由抽屉
   *   （chrome-extension:// 页面）发出，不受该策略限制。
   *
   *   后台 service worker 运行在扩展上下文，无此限制，故交由它转发。
   *
   * 失败丢弃，不重试：日志不能反过来拖累主流程。
   */
  function flush() {
    timer = null;
    if (!buf.length) return;
    if (!baseUrl) {
      // 地址未知：保留本批，等地址注入后再发。
      // 地址由抽屉探测后写入，用户打开一次抽屉即会有值。
      // 但缓冲要有上限，否则长期不开抽屉会无限增长。
      if (buf.length > MAX_BATCH * 4) buf = buf.slice(buf.length - MAX_BATCH * 4);
      if (timer === null) timer = setTimeout(flush, FLUSH_MS * 5);
      return;
    }
    const batch = buf;
    buf = [];
    try {
      chrome.runtime.sendMessage(
        { type: 'ext_remote_log', url: baseUrl + '/api/web/client_log', body: batch },
        function () { /* 忽略响应与错误：日志不能拖累主流程 */ }
      );
    } catch (e) { /* 扩展上下文失效等：忽略 */ }
  }

  /**
   * 上报一条日志。
   * @param {string} tag 分类（如 风控恢复 / 生成态）
   * @param {string} msg 正文
   */
  function send(tag, msg) {
    buf.push({ tag: 'ext-' + tag, msg: String(msg || '') });
    if (buf.length >= MAX_BATCH) { flush(); return; }
    if (timer === null) timer = setTimeout(flush, FLUSH_MS);
  }

  A.remoteLog = { setBaseUrl: setBaseUrl, send: send };

  console.log('[AI-Mirror][content] [远程日志] 模块加载完成');
})();
