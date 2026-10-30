/* ============================================================
 * 网页版机器人 —— 文件上传
 *
 * 职责：把用户选中的文件读为 base64 后上传，并在失败时把后端给出的
 *       具体原因（如「不支持的文件类型」）直接告诉用户。
 *
 * 从 web_page.js 拆出，使该文件保持在行数上限内。
 * 依赖：调用方传入的 clientLog / onDone 两个回调，本模块不直接碰页面状态。
 * ============================================================ */
(function (global) {
  'use strict';

  var WebUpload = {};

  /**
   * 上传一个文件到 /api/web/file。
   *
   * 与图片的关键区别：文件不进输入框、不预览缩略图，选中即上传。
   * 上传成功后后端会把落盘路径投成卡片，AI 自己去读。
   *
   * @param {File}     file      用户选中的文件
   * @param {string}   text      随文件附带的说明文字
   * @param {Function} clientLog 日志回调（可为 null）
   * @param {Function} onDone    结束回调，参数 (ok, message)；成功时 message 为空
   */
  WebUpload.send = function (file, text, clientLog, onDone) {
    var log = clientLog || function () {};
    var done = onDone || function () {};
    if (!file) { done(false, '没有选中文件'); return; }

    var reader = new FileReader();
    reader.onload = function () {
      // dataURL 形如 data:xxx;base64,XXXX，取逗号后的部分
      var b64 = String(reader.result || '').split(',')[1] || '';
      fetch('/api/web/file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: file.name, data: b64, text: text || '' })
      }).then(function (r) {
        // 后端对不支持的类型返回 400 + message，据此给出准确提示
        return r.json().then(function (j) { return { status: r.status, body: j }; });
      }).then(function (res) {
        if (res.body && res.body.success) {
          log('file', 'ok name=' + file.name);
          done(true, '');
          return;
        }
        var msg = (res.body && (res.body.message || res.body.error)) || '上传失败';
        log('file', 'fail ' + msg);
        done(false, msg);
      }).catch(function (err) {
        log('file', 'fail ' + (err && err.name));
        done(false, '文件上传失败，请检查网络后重试');
      });
    };
    reader.readAsDataURL(file);
  };

  /**
   * 绑定文件选择按钮与隐藏输入框。
   *
   * 由页面脚本调用一次即可。事件绑定放在本模块内，
   * 使 web_page.js 保持在行数上限内。
   *
   * @param {Function} getText   取当前输入框文字（随文件一起发送）
   * @param {Function} clientLog 日志回调
   * @param {Function} onSuccess 上传成功后的回调（清空输入、刷新列表）
   */
  WebUpload.bind = function (getText, clientLog, onSuccess) {
    var btn = document.getElementById('btnFile');
    var input = document.getElementById('fileDoc');
    if (!btn || !input) return;
    btn.addEventListener('click', function () { input.click(); });
    input.addEventListener('change', function (e) {
      var f = (e.target.files || [])[0];
      if (!f) return;
      WebUpload.send(f, (getText && getText()) || '', clientLog, function (ok, message) {
        if (ok) { if (onSuccess) onSuccess(); return; }
        alert('文件未发送：' + message);
      });
      e.target.value = '';   // 清空，允许再次选同一个文件
    });
  };

  global.WebUpload = WebUpload;
})(window);
