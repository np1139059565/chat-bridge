// 模块：extend/dialog/parts/06b_execute_ui.js
// 用途：卡片上的两个点击入口——「执行」与「复制结果」。
//       从 06_execute.js 抽出，使该文件保持在行数上限内。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;

  /** 点击执行：跳过倒计时立即执行。 */
  D.onExecuteClick = function (card) {
    if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
    card.countdown = 0;
    card.phase = '';
    this.executeCard(card);
  };

  /**
   * 点击「复制结果」按钮：
   *  · 正处于回传倒计时 → 跳过等待，立即把结果回传到网页 AI；
   *  · 否则 → 照常复制结果文本到剪贴板。
   * @param {Object} card 工具卡片
   */
  D.onResultClick = function (card) {
    if (card.phase === 'send' && card.countdown > 0) {
      // 跳过倒计时立即回传：先清掉计时器，再手动触发一次回传
      if (card._cdTimer) { clearTimeout(card._cdTimer); card._cdTimer = null; }
      card.countdown = 0;
      card.phase = '';
      this.postCardResult(card);
      this.toast('已回传结果到网页 AI');
      return;
    }
    // 结果是图片时复制图片；文本附件与普通结果照常复制结果文本。
    const shot = D.extractScreenshot(card.result);
    if (shot) {
      this._getImageDataUrl(shot).then((dataUrl) => {
        this.copyImage(dataUrl);
      }).catch((e) => {
        this.toast('获取图片失败：' + e.message);
      });
      return;
    }
    this.copy(this.resultText(card));
  };
})();
