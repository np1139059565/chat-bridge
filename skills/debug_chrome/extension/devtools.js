// 模块：devtools.js
// 用途：DevTools 打开时运行，采集 Network 面板记录，供 AI 做故障分析。
//
// 背景：
//  - chrome.devtools.* 只在 DevTools 面板打开、且扩展声明了 devtools_page 时才存在。
//  - Network 记录通过 chrome.devtools.network.onRequestFinished 实时捕获；
//    DevTools 不提供「历史回看」接口，因此本脚本必须常驻监听、边收边存。
//  - Console 记录同理无法回看，已在页面侧（08_injected_main.js）hook console 捕获，
//    不在此处处理。
//  - 采集到的数据经后台（service_worker）中转缓存，内容脚本按需查询。

(function () {
  'use strict';

  // 被调试标签页的 id：内容脚本据此确认「这份记录是不是我这个页面的」
  var tabId = chrome.devtools.inspectedWindow.tabId;
  // 网络记录环形缓冲上限，防止长期开着 DevTools 把内存撑爆
  var MAX_REQUESTS = 300;

  /**
   * 上报一条网络记录到后台缓存。
   * 通过 chrome.runtime.sendMessage 发给 service_worker，由它按 tabId 归类保存。
   * @param {Object} entry 网络记录
   */
  function report(entry) {
    try {
      chrome.runtime.sendMessage({
        type: 'devtools-network-record',
        tabId: tabId,
        entry: entry
      });
    } catch (e) { /* 后台不可达时忽略 */ }
  }

  // 监听每一个完成的网络请求，抽取关键字段上报
  chrome.devtools.network.onRequestFinished.addListener(function (request) {
    try {
      var entry = {
        // 请求方法、地址、状态码、耗时
        method: (request.request && request.request.method) || '',
        url: (request.request && request.request.url) || '',
        status: (request.response && request.response.status) || 0,
        statusText: (request.response && request.response.statusText) || '',
        mimeType: (request.response && request.response.content && request.response.content.mimeType) || '',
        // 耗时（毫秒）：从请求发起到响应完成
        time: request.time || 0,
        // 开始时刻（毫秒时间戳）：DevTools 提供 startedDateTime 为 ISO 字符串
        startedAt: request.startedDateTime || '',
        // 请求体（若有）：POST 等方法的提交内容
        requestBody: (request.request && request.request.postData && request.request.postData.text) || '',
      };
      report(entry);
    } catch (e) { /* 单条记录失败不影响后续 */ }
  });

  // 页面导航（刷新/跳转）时，通知后台清空本标签页的旧记录，
  // 否则新旧页面的请求会混在一起，分析时误导。
  chrome.devtools.network.onNavigated.addListener(function () {
    try {
      chrome.runtime.sendMessage({ type: 'devtools-network-clear', tabId: tabId });
    } catch (e) { /* 忽略 */ }
  });
})();
