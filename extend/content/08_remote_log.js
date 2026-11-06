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

  // 待发缓冲
  let buf = [];
  // 定时器
  let timer = null;
  // 冲刷间隔：1 秒一次，与网页版日志模块保持一致
  const FLUSH_MS = 1000;
  // 单批上限
  const MAX_BATCH = 50;

  /**
   * 冲刷缓冲：把积累的日志交给抽屉代发。
   *
   * 为什么不由内容脚本自己发：
   *   内容脚本跑在网页的源里（如 https://chat.deepseek.com），请求
   *   http://127.0.0.1:5000 会被混合内容策略拦截。而抽屉是扩展页面，
   *   不受该限制——工具调用正是经这条通道到达后端的，已被验证可行。
   *
   * 为什么不走后台 service worker：那是我最初的做法，绕了一圈。
   *   既然抽屉本来就开着（AI 与用户的对话全靠它转发），直接交给它
   *   代发即可，最少环节、最少失败点。
   *
   * 失败丢弃，不重试：日志不能反过来拖累主流程。
   */
  function flush() {
    timer = null;
    if (!buf.length) return;
    // 抽屉是否就绪：iframe 存在才可能把消息送进去。
    //
    // 页面刷新后的头几秒，内容脚本已经在打日志（模块加载、启动探针等），
    // 而抽屉往往还没打开。此时若照常发送，A.post 会因 iframe 不存在
    // 直接丢弃——这批最早、最关键的日志就永远看不到了。
    // 故未就绪时保留缓冲，稍后重试。
    if (!A.state || !A.state.iframe) {
      // 本页没有抽屉：改走后台转发。
      //
      // 为什么需要这条兜底：页面刷新后抽屉是关闭的（设计如此），
      // 而抽屉也可能开在别的标签页。此时本页内容脚本找不到接收方，
      // 若只等抽屉，这个页面的日志就永远发不出去。
      // 后台运行在扩展上下文，不受混合内容策略限制，可作为第二条路。
      fallbackViaBackground(buf);
      buf = [];
      return;
    }
    const batch = buf;
    buf = [];
    // 交给抽屉代发。
    //
    // 为什么不自己 fetch：内容脚本跑在网页的源里，请求本地 HTTP 服务
    // 会被混合内容策略拦截。抽屉是扩展页面，不受该限制——
    // 工具调用正是经这条通道到达后端的，已被验证可行。
    try {
      A.post({ type: 'ext_log', batch: batch });
    } catch (e) {
      console.warn('[AI-Mirror][content] [远程日志] 交给抽屉失败：' + (e && e.message ? e.message : e));
    }
  }

  /**
   * 兜底通道：本页没有抽屉时，改由后台转发。
   *
   * 后台 service worker 运行在扩展上下文，不受混合内容策略限制。
   * 它需要知道后端地址，故一并传过去；地址为空时后台用默认值。
   *
   * 失败静默：日志不能反过来拖累主流程。
   *
   * @param {Array} batch 日志数组
   */
  function fallbackViaBackground(batch) {
    if (!batch || !batch.length) return;
    try {
      chrome.runtime.sendMessage(
        { type: 'ext_remote_log', baseUrl: '', body: batch },
        function () { /* 忽略回包 */ }
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

  A.remoteLog = { send: send };

  console.log('[AI-Mirror][content] [远程日志] 模块加载完成');
})();
