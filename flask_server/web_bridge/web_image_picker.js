/* ============================================================
 * 网页版机器人 —— 图片选择与预览
 * 职责：点按钮选图、多张读为 dataURL、渲染缩略图预览、移除与清空。
 *
 * 为什么单独成文件：选图涉及文件读取的异步回调、缩略图 DOM 重建、
 * 待发图片数组的增删，与轮询、发送流程无关。抽出来既便于阅读，
 * 也避免主模块超出行数上限。
 *
 * 对外接口（window.WebImagePicker）：
 *   init(opts)  注入依赖并绑定按钮
 *   list()      取当前待发图片的 dataURL 数组（副本）
 *   clear()     清空已选图片与预览
 * ============================================================ */
(function () {
  'use strict';

  var pendingImages = [];   // 已选图片的 dataURL 数组
  var clearCallback = null; // 清空后的回调（主模块用来重算输入框高度等）

  /**
   * 渲染已选图片预览：每张配缩略图与移除按钮。
   *
   * 每次都整段重建，而不是增量插入：图片数量很少（一般一到几张），
   * 重建的代价可忽略，却省掉了「删除后索引错位」这类易错处理。
   */
  function renderPreview() {
    var box = document.getElementById('preview');
    var list = document.getElementById('previewList');
    list.innerHTML = '';
    pendingImages.forEach(function (url, idx) {
      var wrap = document.createElement('span');
      wrap.className = 'thumb';
      var img = document.createElement('img');
      img.src = url;
      var rm = document.createElement('span');
      rm.className = 'rm';
      rm.textContent = '×';
      rm.addEventListener('click', function () {
        pendingImages.splice(idx, 1);   // 移除该张
        renderPreview();
      });
      wrap.appendChild(img);
      wrap.appendChild(rm);
      list.appendChild(wrap);
    });
    // 有图才显示预览条
    if (pendingImages.length) box.classList.add('on');
    else box.classList.remove('on');
  }

  /**
   * 读一张图片为 dataURL。
   *
   * @param {File}     file 图片文件
   * @param {Function} done 读完回调，参数为 dataURL
   */
  function readAsDataUrl(file, done) {
    var reader = new FileReader();
    reader.onload = function () { done(reader.result); };
    reader.readAsDataURL(file);
  }

  /**
   * 初始化：绑定「选图」按钮与文件输入框。
   *
   * @param {Object} opts { onClear }  onClear 在清空后调用，供主模块重算输入框高度
   */
  function init(opts) {
    opts = opts || {};
    clearCallback = opts.onClear || null;
    document.getElementById('btnImg').addEventListener('click', function () {
      document.getElementById('fileInput').click();
    });
    document.getElementById('fileInput').addEventListener('change', function (e) {
      // 多选：逐个读为 dataURL，全部读完再统一渲染预览
      var files = Array.prototype.slice.call(e.target.files || []);
      if (!files.length) return;
      var remain = files.length;
      files.forEach(function (f) {
        readAsDataUrl(f, function (url) {
          pendingImages.push(url);
          remain--;
          // 全部读完才渲染一次，避免每张各渲染一遍造成闪烁
          if (remain === 0) renderPreview();
        });
      });
      e.target.value = '';
    });
  }

  /** 取当前待发图片（返回副本，调用方改它不影响内部状态）。 */
  function list() {
    return pendingImages.slice();
  }

  /** 清空已选图片与预览。 */
  function clear() {
    pendingImages = [];
    renderPreview();
    if (clearCallback) clearCallback();
  }

  /**
   * 恢复一组图片并重绘预览。
   *
   * 用途：发送失败时把提交前的图片原样放回，避免用户重选。
   * 传入副本，调用方后续改动自己的数组不会影响内部状态。
   *
   * @param {Array<string>} urls 图片 dataURL 数组
   */
  function restore(urls) {
    pendingImages = Array.isArray(urls) ? urls.slice() : [];
    renderPreview();
    if (clearCallback) clearCallback();
  }

  window.WebImagePicker = { init: init, list: list, clear: clear, restore: restore };
})();
