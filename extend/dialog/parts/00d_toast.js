// 模块：extend/dialog/parts/00d_toast.js
// 用途：轻提示（toast）—— 显示一条短消息，至少 2 秒后自动消失；
//       鼠标悬浮其上时暂停消失，移开后再计时，便于用户从容阅读。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 从 01_backend.js 拆出：该文件承担后端交互主职，行数已近上限，
// 轻提示是独立小功能，单独成文件更清晰。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /** 轻提示：显示一条短消息，至少 2 秒后自动消失；鼠标悬浮其上时不消失。 */
  M.toast = function (msg) {
    this.toastMsg = msg;
    this._toastHover = false;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      // 鼠标正停在提示上：不消失，等移开后再走计时（见 toastLeave）
      if (this._toastHover) return;
      this.toastMsg = '';
    }, 2000);
  };

  /** 鼠标移入轻提示：暂停自动消失计时，便于用户从容阅读。 */
  M.toastEnter = function () {
    this._toastHover = true;
    clearTimeout(this._toastTimer);
  };

  /** 鼠标移出轻提示：重新开始计时，2 秒后消失。 */
  M.toastLeave = function () {
    this._toastHover = false;
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => { this.toastMsg = ''; }, 2000);
  };
})();
