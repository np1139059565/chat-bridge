// 模块：extend/dialog/parts/00c_sendqueue.js
// 用途：回传网页 AI 的统一发送队列。
//       所有「写进网页输入框并发送」的消息（工具卡片结果、质量告警、
//       外部卡片、图片）都必须经此排队，一次只发一条，发完留间隔再发下一条。
//       这样避免两条回传同时到达、互相顶掉，或密集刷屏触发网页风控。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;

  // 队列状态：items 待发条目，sending 是否正在发送。
  // 间隔按条目类型区分（毫秒）：
  //  - gap：普通文本条目，发后留出「写入输入框 → 回车 → 复位」的时间；
  //  - imageGap：图片条目，内容脚本贴图后要等约 1500ms 才回车提交，
  //    若仍按 gap 会让紧随其后的文本挤在图片提交前，导致顶掉或乱序。
  const Q = { items: [], sending: false, gap: 800, imageGap: 1800 };
  D.sendQueue = Q;

  /**
   * 把一个回传条目加入队列。
   * @param {Object} payload 条目：{ type, text } 或 { type, dataUrl, text }
   *   type='auto_send'       文本回传
   *   type='auto_send_image' 图片回传（可带 text 文字一并粘贴）
   */
  D.enqueueSend = function (payload) {
    if (!payload || !payload.type) return;
    Q.items.push(payload);
    log('发送队列入列：' + payload.type + '，待发=' + Q.items.length);
    // 空闲时才启动泵；忙碌时入列即返回，由正在进行的泵发完继续取。
    if (!Q.sending) D._pumpSendQueue();
  };

  /**
   * 队列泵：取出队首发送，间隔 gap 后继续取下一条，直到队列清空。
   */
  D._pumpSendQueue = function () {
    if (Q.sending) return;
    if (!Q.items.length) return;
    Q.sending = true;
    const item = Q.items.shift();
    log('发送队列出列：' + item.type + '，剩余=' + Q.items.length);
    // 本条的等待间隔：图片条目需更久（贴图后要等回车提交），文本用默认值。
    let wait = Q.gap;
    if (item.type === 'auto_send_image') {
      window.parent.postMessage({ type: 'auto_send_image', dataUrl: item.dataUrl, text: item.text || '' }, '*');
      wait = Q.imageGap;
    } else {
      window.parent.postMessage({ type: 'auto_send', text: item.text || '' }, '*');
    }
    // 发送后隔 wait 再取下一条：给网页留出「写入输入框 → 回车发送 → 复位」的时间。
    Q.timer = setTimeout(function () {
      Q.timer = null;
      Q.sending = false;
      D._pumpSendQueue();
    }, wait);
  };
})();
