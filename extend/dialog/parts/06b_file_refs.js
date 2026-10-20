// 模块：extend/dialog/parts/06b_file_refs.js
// 用途：工具结果携带正文（read_file 的 data.text）时的回传处理——
//       正文粘贴进对话，回传 AI 的只有精简的 bridge-chat-res 标记。
//       与截图链路对称：图片放 data.screenshot、正文放 data.text，
//       都由前端取出后粘贴，工具结果本身不进对话正文。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、00c_sendqueue.js（D.enqueueSend）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 从工具结果里取正文。
   *
   * read_file 的结果结构：{ data: { text: "..." }, path, lines, total_lines }。
   * 批量读取时 text 已由后端按「路径 行范围」拼好。
   * @param {Object} result 工具结果
   * @returns {string} 正文；没有则返回空串
   */
  D.extractText = function (result) {
    if (!result || !result.data || typeof result.data !== 'object') return '';
    const t = result.data.text;
    return (typeof t === 'string') ? t : '';
  };

  /**
   * 把正文粘贴进对话，正文前附精简标记。
   *
   * 标记只保留身份信息（tool/type/nonce/success），不含 result 与正文；
   * 正文紧接其后，作为一条消息发出，保证「一次工具结果只对应一条消息」。
   * @param {Object} card 工具卡片
   * @param {string} text 正文
   */
  M._emitText = function (card, text) {
    const nonce = this.ensureNonce(card);
    const mark = JSON.stringify({ tool: card.tool, type: 'bridge-chat-res', nonce: nonce, success: true });
    D.enqueueSend({ type: 'auto_send', text: mark + '\n\n' + text });
  };
})();
