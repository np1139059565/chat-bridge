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
    const batch = buf;
    buf = [];
    // 交给抽屉代发。
    //
    // 为什么不自己 fetch、也不走后台：
    //   抽屉（chrome-extension:// 页面）请求本地服务是已被验证可行的通道
    //   ——工具调用正是经由它到达后端的。内容脚本自己 fetch 会受
    //   HTTPS 页面的混合内容策略限制，后台转发又平白多一跳、更易出问题。
    //   直接复用已跑通的通道，最少环节、最少失败点。
    try {
      if (A.post) {
        A.post({ type: 'ext_log', batch: batch });
      }
    } catch (e) {
      console.warn('[AI-Mirror][content] [远程日志] 交给抽屉失败：' + (e && e.message ? e.message : e));
    }
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
