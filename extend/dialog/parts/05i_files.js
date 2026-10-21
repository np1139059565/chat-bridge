// 模块：extend/dialog/parts/05i_files.js
// 用途：消息附带的「文件」相关逻辑，从 05_messages.js 与 07_cards.js 抽出，
//       使这两个文件保持在仓库行数上限内。
// 背景：文件附件（read_file 的产物）与图片不同——块类型里没有「文件」这一种，
//       故用消息的 files 字段承载描述，并由渲染层单独给出「重新粘贴」按钮。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;
  const log = D.log;
  // 渲染函数与其它渲染模块同一来源（Vue 的 h）
  const h = Vue.h;

  /**
   * 把登记过的文件描述按「文字关联」挂到对应消息的 files 字段。
   *
   * 与 _attachPendingImages 同一思路，但落点不同：块类型里没有「文件」，
   * 故写在消息的 files 字段上，由渲染层据此给出「重新粘贴」按钮。
   * 必须在入树之前调用：入树后节点已按 makeNode 拷过字段，再改原对象不生效。
   * @param {Object} conv 会话对象（含 pendingFiles 关联表）
   * @param {Array} incoming 本轮入树的消息
   */
  M._attachPendingFiles = function (conv, incoming) {
    const pend = (conv && conv.pendingFiles) || [];
    if (!pend.length) return;
    const used = [];
    (incoming || []).forEach((m) => {
      if (!m || m.role !== 'user') return;
      // 取该消息的文字：文件回传的是 bridge-chat-res 标记，可能落在 code 块
      const text = (m.blocks || []).filter(function (b) {
        return b && (b.type === 'paragraph' || b.type === 'code');
      }).map(function (b) { return b.text || b.code || ''; }).join(' ').trim();
      if (!text) return;
      for (let i = 0; i < pend.length; i++) {
        if (used.indexOf(i) >= 0) continue;
        const p = pend[i];
        // 按文字包含匹配：网页回显的标记与卡片标记一致即可命中
        if (p.text && text.indexOf(p.text) >= 0) {
          used.push(i);
          m.files = (p.files || []).slice();
          // 同步到已在树中的同一条消息节点（消息可能先于文件卡片入树）
          try {
            const tk = this.keyOfId(conv.msgTree, this.msgId(m));
            const tn = tk && conv.msgTree[tk];
            if (tn && tn !== m) tn.files = (p.files || []).slice();
          } catch (e) { log('文件描述同步到树失败：' + e); }
          break;
        }
      }
    });
    // 命中的关联移除，避免同一批文件被重复挂到后续消息上
    if (used.length) {
      conv.pendingFiles = pend.filter(function (_, i) { return used.indexOf(i) < 0; });
    }
  };

  /**
   * 渲染「重新粘贴」按钮；消息没有附带文件时返回 null（不占位）。
   *
   * 文件只存描述不存内容：整文件按路径现取，分段按已存 dataURL 解码。
   * 点击时阻止冒泡，避免误触消息的展开 / 收起。
   * @param {Object} ctx Vue 实例
   * @param {Object} m 消息对象（含 files 字段）
   * @returns {VNode|null} 按钮节点
   */
  D.renderRepasteButton = function (ctx, m) {
    const files = (m && m.files) || [];
    if (!files.length) return null;
    return h('span', {
      class: 'file-repaste',
      title: '重新把 ' + files.length + ' 个文件贴进输入框',
      onClick: (ev) => {
        if (ev && ev.stopPropagation) ev.stopPropagation();
        if (ctx.repasteFiles) ctx.repasteFiles(files);
      }
    }, '重新粘贴(' + files.length + ')');
  };
})();
