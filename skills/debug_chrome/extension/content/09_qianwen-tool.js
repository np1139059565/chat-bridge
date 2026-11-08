// qianwen 适配器原生工具注册 —— 把适配器挂成扩展工具，免除每次经 exec_js 手动注入。
// 适配器本体唯一来源是 adapters/qianwen-adapter.js（已列入 web_accessible_resources），
// 本文件只做两件事：按需把适配器源码送进主世界执行（安装幂等），并把两个处理器
// 登记进 A.TOOL_HANDLERS 表（分发逻辑在 05_tool-handlers.js，无需改动）。
// 工具清单：
//   send_to_qianwen  { text, page_url?, wait_done? } → 注入并发送消息
//   qianwen_state    { page_url? }                  → 查询生成态（idle | generating）
(function () {
  const A = window.AIStyleDebug;

  // 适配器源码缓存：首次使用时取一次，之后复用。适配器是幂等 IIFE，
  // 重复执行无害；取文失败则清缓存允许下次重试。
  let adapterSrcPromise = null;
  function loadAdapterSrc() {
    if (!adapterSrcPromise) {
      adapterSrcPromise = fetch(chrome.runtime.getURL('adapters/qianwen-adapter.js'))
        .then((r) => {
          if (!r.ok) throw new Error('ADAPTER_FETCH_' + r.status);
          return r.text();
        });
      adapterSrcPromise.catch(() => { adapterSrcPromise = null; });
    }
    return adapterSrcPromise;
  }

  // page_url 路由校验：与 exec_js 口径一致，仅支持顶层文档主世界。
  // qianwen 以顶层页运行时传顶层 URL 即可；iframe 路由需点选补丁支持
  // 对应消息类型，目前未支持，故明确报 TOP_ONLY 并附可用文档列表。
  function checkTopOnly(params) {
    const url = (params && params.page_url) || '';
    if (url && A.normalizeUrl(url) !== A.normalizeUrl(location.href)) {
      return {
        success: false,
        error: 'TOP_ONLY',
        page_url: url,
        available: A.frameUrls(),
        hint: '该工具仅支持顶层文档主世界；请传入顶层页面的 URL（见 available 列表）。'
      };
    }
    return null;
  }

  // 在主世界执行：先确保适配器已安装，再执行调用片段。
  // execJs 把代码包成 async 函数体，片段必须以 return 交出结果。
  async function runWithAdapter(returnSnippet) {
    try {
      const src = await loadAdapterSrc();
      return await A.execJs(src + '\n' + returnSnippet);
    } catch (e) {
      return { success: false, error: 'ADAPTER_LOAD_FAILED', message: String((e && e.message) || e) };
    }
  }

  // 工具 send_to_qianwen：注入文本并点击发送。
  // text 消息正文（必填）；wait_done=true 时同步等生成结束（受 exec_js 15s 上限，
  // 长生成请保持默认关闭，改用 qianwen_state 轮询）。
  A.TOOL_HANDLERS.send_to_qianwen = async function (params) {
    const blocked = checkTopOnly(params);
    if (blocked) return blocked;
    const text = params && typeof params.text === 'string' ? params.text : '';
    if (!text.trim()) {
      return { success: false, error: 'MISSING_TEXT', hint: 'send_to_qianwen 需要非空的 text 参数（消息正文）。' };
    }
    const opts = params.wait_done === true ? ', { waitDone: true }' : '';
    const res = await runWithAdapter(
      'return await window.__qianwenAdapter.send(' + JSON.stringify(text) + opts + ');'
    );
    if (!res || !res.success) {
      return { success: false, error: (res && res.error) || 'SEND_FAILED' };
    }
    return { success: true, data: res.result };
  };

  // 工具 qianwen_state：查询生成态，供调用方在 send 后轮询直至完成。
  A.TOOL_HANDLERS.qianwen_state = async function (params) {
    const blocked = checkTopOnly(params);
    if (blocked) return blocked;
    const res = await runWithAdapter('return window.__qianwenAdapter.state();');
    if (!res || !res.success) {
      return { success: false, error: (res && res.error) || 'STATE_FAILED' };
    }
    return { success: true, data: { state: res.result } };
  };
})();
