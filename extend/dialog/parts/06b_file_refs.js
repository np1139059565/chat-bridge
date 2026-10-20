// 模块：extend/dialog/parts/06b_file_refs.js
// 用途：工具结果中「引用型文件」（file_ref）的处理——收集引用项、并发取回正文、
//       拼成一条消息经发送队列粘贴进对话。
//       正文由 read_file 移出工具结果后，由此模块取回，避免大段文本经 JSON 转义
//       占用对话空间。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、00c_sendqueue.js（D.enqueueSend）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 收集工具结果中的「引用型」文件项（file_ref）。
   *
   * read_file 读取大段正文时，正文不随工具结果回传，结果里只留
   * {file_ref:true, path, lines, preview}。这类项需要前端按路径取回正文，
   * 再经文本通道粘贴进对话，避免正文被 JSON 转义后占用对话空间。
   * @param {Object} result 工具结果
   * @returns {Array} 引用项数组；无引用时为空数组
   */
  M._collectFileRefs = function (result) {
    const out = [];
    if (!result || typeof result !== 'object') return out;
    // 单文件模式：结果本身就是引用项
    if (result.file_ref === true) {
      out.push(result);
      return out;
    }
    // 批量模式：files 数组里逐个判断
    if (Array.isArray(result.files)) {
      result.files.forEach(function (it) {
        if (it && it.file_ref === true) out.push(it);
      });
    }
    return out;
  };

  /**
   * 并发取回所有引用文件的正文。
   *
   * 多个文件同时发起请求（并发读取），全部返回后统一拼接发送，
   * 保证「一次工具结果只对应一条消息」。单个取回失败不影响其它项，
   * 失败原因写进该段正文，避免整条结果丢失。
   * @param {Object} card 工具卡片
   * @param {Array} refs 引用项数组
   */
  M._sendFileRefs = function (card, refs) {
    const self = this;
    const base = this.config.flaskUrl || '';
    const parts = new Array(refs.length);
    let pending = refs.length;
    // 取回单个文件正文；无论成败都会递减计数，保证最终一定发出消息
    const fetchOne = function (ref, i) {
      const path = ref.path || ref.file_path || '';
      const lines = ref.lines || [1, 0];
      const head = path + ' 行 ' + lines[0] + '-' + lines[1];
      const url = base + '/api/web/text-file?path=' + encodeURIComponent(path)
        + '&start=' + lines[0] + '&end=' + lines[1];
      fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.success) {
            parts[i] = '===== ' + head + ' =====\n' + (d.content || '');
          } else {
            parts[i] = '===== ' + head + ' =====\n（取回失败：' + ((d && d.error) || 'unknown') + '）';
          }
        })
        .catch(function (e) {
          parts[i] = '===== ' + head + ' =====\n（取回失败：' + (e && e.message ? e.message : e) + '）';
        })
        .then(function () {
          pending--;
          if (pending === 0) self._emitFileRefs(card, parts);
        });
    };
    // 并发发起：各文件互不等待
    refs.forEach(fetchOne);
  };

  /**
   * 把已取回的正文与精简标记拼成一条消息，经发送队列粘贴进对话。
   *
   * 标记只保留身份信息（tool/type/nonce/success），不含 result 与正文；
   * 正文各段自带「路径 行范围」头，便于区分来源。
   * @param {Object} card 工具卡片
   * @param {Array} parts 各文件的正文段
   */
  M._emitFileRefs = function (card, parts) {
    const nonce = this.ensureNonce(card);
    const mark = JSON.stringify({ tool: card.tool, type: 'bridge-chat-res', nonce: nonce, success: true });
    const body = parts.filter(function (s) { return s; }).join('\n\n');
    D.enqueueSend({ type: 'auto_send', text: mark + '\n\n' + body });
  };
})();
