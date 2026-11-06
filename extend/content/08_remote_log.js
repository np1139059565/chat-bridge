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

  // 候选后端地址：按顺序尝试，第一个成功发出去的即被记住。
  //
  // 为什么需要候选：扩展存储里的地址（aiMirrorFlaskUrl）由设置页写入，
  // 若用户从没在设置页保存过，该项为空，只靠它会导致日志一条都发不出去。
  // 而内容脚本本来就跑在用户自己电脑上，本地服务默认就在这两个地址。
  const CANDIDATES = ['http://127.0.0.1:5000', 'http://localhost:5000'];
  // 当前生效的地址；空表示还没定下来
  let baseUrl = '';
  // 已确认可用的地址（发送成功后固化，避免每次都试错）
  let confirmedUrl = '';
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
   * 向指定地址发一批日志。
   *
   * @param {string} url   后端根地址
   * @param {Array}  batch 日志数组
   * @returns {Promise<boolean>} 是否发送成功（拿到 2xx 才算）
   */
  function postBatch(url, batch) {
    return fetch(url + '/api/web/client_log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(batch),
      // keepalive：页面跳转 / 关闭时也让请求发完
      keepalive: true
    }).then(function (r) { return r.ok; });
  }

  /**
   * 冲刷缓冲：把积累的日志一次性发出。
   *
   * 地址解析顺序：已确认的 > 外部注入的 > 内置候选。
   * 只靠外部注入不够——用户若从没在设置页保存过地址，该项为空，
   * 日志会一条都发不出去。内容脚本本就跑在用户自己电脑上，
   * 本地服务默认就在候选地址里，直接试即可。
   *
   * 失败丢弃，不重试：日志不能反过来拖累主流程。
   */
  function flush() {
    timer = null;
    if (!buf.length) return;
    const batch = buf;
    buf = [];
    // 待试地址：已确认的优先，其次外部注入，最后内置候选
    const tryList = [];
    if (confirmedUrl) tryList.push(confirmedUrl);
    if (baseUrl && baseUrl !== confirmedUrl) tryList.push(baseUrl);
    CANDIDATES.forEach(function (u) { if (tryList.indexOf(u) < 0) tryList.push(u); });

    /** 依次尝试，首个成功即固化地址。 */
    function attempt(i) {
      if (i >= tryList.length) return;   // 全部失败：丢弃本批
      const url = tryList[i];
      postBatch(url, batch).then(function (ok) {
        if (ok) {
          if (confirmedUrl !== url) {
            confirmedUrl = url;
            console.log('[AI-Mirror][content] [远程日志] 确认可用地址：' + url);
          }
        } else {
          attempt(i + 1);
        }
      }).catch(function () { attempt(i + 1); });
    }
    try { attempt(0); } catch (e) { /* 环境不支持 fetch 等：忽略 */ }
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
