// 模块：extend/dialog/parts/01d_bridge_md.js
// 用途：Markdown 原文采集 + 桥接动作辅助（会话列表、点击结果文案）。
//
// 背景：按 DOM 块拼出的纯文本会丢格式（标题、列表、加粗、代码围栏等）。
// 页面自带的「复制」按钮复制的就是原始 Markdown，最保真。
// 做法：AI 回复完成后点一下复制按钮，主世界 hook 截获剪贴板内容回传，
// 挂到消息树对应节点上；推 QQ 时优先用它，没有则退回纯文本。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 触发采集：请求内容脚本点击页面的复制按钮。
   * @param {string} msgId 目标消息 id（内容指纹）
   */
  M.captureMarkdown = function (msgId) {
    if (!msgId) return;
    if (!this.bridgeMdSelector) return;   // 未配置选择器，跳过
    this._mdCaptureTarget = msgId;
    window.parent.postMessage({
      type: 'bridge_copy_md',
      selector: this.bridgeMdSelector
    }, '*');
    // 兜底：3 秒没等到回传就清掉目标，避免内容误挂到别的消息上
    clearTimeout(this._mdCaptureTimer);
    this._mdCaptureTimer = setTimeout(() => { this._mdCaptureTarget = ''; }, 3000);
  };

  /**
   * 采集测试：用当前选择器试采一次，把结果提示给用户。
   * 便于确认选择器是否有效、是否命中了唯一按钮。
   */
  M.testMdSelector = function () {
    if (!this.bridgeMdSelector) { this.toast('请先填写选择器'); return; }
    this._mdTest = true;
    this._mdCaptureTarget = '__test__';
    window.parent.postMessage({
      type: 'bridge_copy_md',
      selector: this.bridgeMdSelector
    }, '*');
    clearTimeout(this._mdCaptureTimer);
    // 超时提示要区分阶段：按钮没点着 vs 点了但没截到剪贴板。
    // 两者混为一谈会让排查走弯路（本次就因此误判了一轮）。
    this._mdCaptureTimer = setTimeout(() => {
      if (!this._mdTest) return;
      this._mdTest = false;
      const phase = this._mdClicked
        ? '按钮已点击，但没截到剪贴板内容（hook 未生效）'
        : '没找到按钮（选择器未匹配到元素）';
      this._mdCaptureTarget = '';
      this._mdClicked = false;
      this.toast('采集失败：' + phase);
    }, 2000);
  };

  /**
   * 收到剪贴板内容：挂到目标消息节点上。
   * @param {string} text Markdown 原文
   */
  M._onClipCopied = function (text) {
    const target = this._mdCaptureTarget;
    if (!target || !text) return;
    this._mdCaptureTarget = '';
    clearTimeout(this._mdCaptureTimer);
    // 采集测试模式：不挂消息树，只回显前若干字符供用户确认
    if (this._mdTest) {
      this._mdTest = false;
      const head = String(text).slice(0, 60).replace(/\n/g, ' ');
      this.toast('采集成功（' + String(text).length + ' 字）：' + head + '…');
      return;
    }
    const tree = (this.curConv && this.curConv.msgTree) || {};
    const key = this.keyOfId(tree, target);
    if (!key || !tree[key]) return;
    // 挂到节点上，供推送时优先使用
    tree[key].md = text;
    if (this._persist) this._persist();
    // 采集完成：若正等它再上报，立即触发
    if (this._afterMd) { const f = this._afterMd; this._afterMd = null; f(); }
  };

  /**
   * 先采集 Markdown、再上报到桥接层。
   *
   * 为什么不能直接上报：上报后后端会按消息 id 记账，已推过的 id 不再推。
   * 若先上报、后采到 md，那份 md 就永远用不上了。
   * 因此这里先点复制按钮取 md，拿到（或超时）后再上报。
   * @param {string} reason 触发来源
   */
  M.reportToBridgeWithMd = function (reason) {
    // 非 generate、未配选择器、面板不可见：直接按原路走
    if (reason !== 'generate' || !this.bridgeMdSelector || !this.panelVisible) {
      this.reportToBridge(reason);
      return;
    }
    const conv = this.curConv || {};
    const tree = conv.msgTree || {};
    const keys = conv.visibleKeys || [];
    // 找最后一条 assistant 消息（最新回复）
    let lastId = '';
    for (let i = keys.length - 1; i >= 0; i--) {
      const node = tree[keys[i]];
      if (node && node.role === 'assistant') {
        lastId = window.AIMirrorDomUtils.messageFingerprint(node);
        break;
      }
    }
    if (!lastId) { this.reportToBridge(reason); return; }
    const self = this;
    // 采集完成后执行；执行前先清掉，保证只跑一次
    this._afterMd = function () { self.reportToBridge(reason); };
    this.captureMarkdown(lastId);
    // 兜底：1.2 秒内没等到回传（按钮缺失 / hook 失败）就照常上报
    clearTimeout(this._mdReportTimer);
    this._mdReportTimer = setTimeout(function () {
      if (self._afterMd) { const f = self._afterMd; self._afterMd = null; f(); }
    }, 1200);
  };

  /**
   * 列出会话列表并回传到 QQ。
   * 序号与 convList 的顺序一致，供 /ss 按序号切换时使用。
   * @param {string} requestId 待回传请求 id
   */
  M._bridgeListSessions = function (requestId) {
    const list = this.convList || [];
    if (!list.length) {
      this._postBridgeResult(requestId, '（暂无会话）');
      return;
    }
    const lines = list.map((c, i) => {
      const cur = c.id === this.activeConv ? ' [当前]' : '';
      const title = c.title || '（未命名）';
      const count = c.msgCount || 0;
      const date = c.updatedAt ? new Date(c.updatedAt).toLocaleDateString() : '';
      return (i + 1) + '.' + cur + ' ' + title
        + '\n   id: ' + c.id + '  ' + count + ' 条 ' + date;
    });
    this._postBridgeResult(requestId, '会话列表（用 /ss 序号 切换）：\n' + lines.join('\n'));
  };

  /**
   * 把点击结果翻译成给人看的文案。
   * 找不到或不唯一都要明确提示，让用户在 QQ 里知道失败原因。
   * @param {Object} d 内容脚本回传的结果
   * @returns {string} 提示文本
   */
  M._clickResultText = function (d) {
    const sel = d.selector || '';
    if (d.ok) return '已点击：' + sel;
    if (d.reason === 'not_found') {
      return '点击失败：页面上找不到元素\n' + sel + '\n（页面结构可能已变，请重新选择元素）';
    }
    if (d.reason === 'not_unique') {
      return '点击失败：该选择器命中 ' + (d.count || 0) + ' 个元素，无法确定点哪个\n' + sel
        + '\n（请重新选择更精确的元素）';
    }
    if (d.reason === 'invalid_selector') {
      return '点击失败：选择器语法无效\n' + sel;
    }
    if (d.reason === 'empty_selector') {
      return '点击失败：该指令没有绑定选择器';
    }
    return '点击失败：' + sel;
  };
})();
