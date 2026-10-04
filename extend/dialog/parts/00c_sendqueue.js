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
  // busySince：本轮「忙」的起始时刻；配合看门狗判断是否卡死。
  const Q = { items: [], sending: false, gap: 800, imageGap: 1800, busySince: 0 };
  // 看门狗阈值（毫秒）：正常一轮最长约 imageGap(1800)+余量；
  // 超过它仍停在「忙」，即视为异常卡死，强制复位，避免队列永久堵死。
  const STUCK_MS = 15000;
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
    // 看门狗：若「忙」状态已持续过久（异常未复位 / 定时器丢失），强制复位。
    // 这样队列即使曾被卡死，下一次入列也能自动救活，不再永久堵死。
    if (Q.sending && Q.busySince && (Date.now() - Q.busySince) > STUCK_MS) {
      log('发送队列检测到卡死，强制复位', 'items=' + Q.items.length);
      if (Q.timer) { clearTimeout(Q.timer); Q.timer = null; }
      Q.sending = false;
      Q.busySince = 0;
    }
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
    // 记录本轮开始时间：供看门狗判断「忙」是否卡得过久（异常未复位时兜底）
    Q.busySince = Date.now();
    const item = Q.items.shift();
    log('发送队列出列：' + item.type + '，剩余=' + Q.items.length);
    // 本条的等待间隔：图片条目需更久（贴图后要等回车提交），文本用默认值。
    let wait = Q.gap;
    try {
      if (item.type === 'auto_send_image') {
        // 多图兼容：优先传数组 dataUrls，同时保留单张 dataUrl 字段供旧消费端回退
        const urls = item.dataUrls || (item.dataUrl ? [item.dataUrl] : []);
        window.parent.postMessage({ type: 'auto_send_image', dataUrls: urls, dataUrl: urls[0] || '', text: item.text || '' }, '*');
        wait = Q.imageGap;
      } else {
        window.parent.postMessage({ type: 'auto_send', text: item.text || '' }, '*');
      }
    } catch (e) {
      // 关键加固：发送步骤一旦抛异常，过去会让 Q.sending 永久停在 true、
      // 整条队列死掉且不自愈（表现为图片发不出、工具结果不回传）。
      // 这里打印真凶并继续走下方定时器复位，保证队列自愈。
      log('发送队列出列异常（已自愈）：' + (e && e.message ? e.message : e), '条目=' + item.type);
    }
    // 发送后隔 wait 再取下一条：给网页留出「写入输入框 → 回车发送 → 复位」的时间。
    // 放在 try 之外：无论发送是否抛异常，都必定安排一次复位，杜绝死队列。
    Q.timer = setTimeout(function () {
      Q.timer = null;
      Q.sending = false;
      Q.busySince = 0;
      D._pumpSendQueue();
    }, wait);
  };
})();
