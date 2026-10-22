// 模块：extend/dialog/parts/06c_file_attach.js
// 用途：把 read_file 返回的文件项转成 File 并发粘贴。
//       两种来源统一产出 File：
//         - 整文件：按路径取原始字节，不经 base64 往返，也不生成副本；
//         - 分段：该片段的 dataURL 解码后构造。
//       全部就绪后合成一条消息，保证「一次工具结果只对应一条消息」。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、00c_sendqueue.js（D.enqueueSend）
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;
  const log = D.log;

  /**
   * 获取图片的 dataURL。
   * 如果传入的是本地链接（如 /api/web/screenshot-file/xxx.png），则通过 fetch 拉取并转成 base64；
   * 如果本身就是 dataURL，直接返回。
   * @param {string} shot 链接或 dataURL
   * @returns {Promise<string>} 图片 dataURL
   */
  M._getImageDataUrl = function (shot) {
    if (shot.indexOf('data:image/') === 0) return Promise.resolve(shot);
    let url = shot;
    if (url.charAt(0) === '/') {
      const base = (this.config.flaskUrl || '').replace(/\/+$/, '');
      url = base + url;
    }
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.blob();
    }).then(function (blob) {
      return new Promise(function (resolve) {
        const reader = new FileReader();
        reader.onloadend = function () { resolve(reader.result); };
        reader.readAsDataURL(blob);
      });
    });
  };

  /**
   * 把一个文件项转成可直接交给队列的 File 对象。
   * @param {Object} file 文件项 { source, path, content, name, mime }
   * @returns {Promise<File|null>} 构造好的 File；失败返回 null
   */
  M._toFileObject = function (file) {
    const base = this.config.flaskUrl || '';
    const name = file.name || 'file.txt';
    const mime = file.mime || 'text/plain';
    if (file.source) {
      const url = base + '/api/web/source-file?path=' + encodeURIComponent(file.path);
      return fetch(url)
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.blob();
        })
        .then(function (blob) { return new File([blob], name, { type: mime }); })
        .catch(function (e) {
          log('取源文件失败：' + name + ' ' + (e && e.message ? e.message : e));
          return null;
        });
    }
    // 分段：把该片段的 dataURL 转成 File
    try {
      const parts = String(file.content || '').split(',');
      const bin = atob(parts[1] || '');
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      return Promise.resolve(new File([arr], name, { type: mime }));
    } catch (e) {
      log('构造分段文件失败：' + name);
      return Promise.resolve(null);
    }
  };

  /**
   * 把一批文件并发取回，合成一条消息交给发送队列。
   * 个别文件失败不阻断其余文件，仅记录日志。
   * @param {Array} files 文件项数组
   * @param {string} mark 精简回传标记
   */
  /**
   * 重新粘贴一批文件到网页 AI 输入框（供消息上的「重新粘贴」按钮调用）。
   *
   * 与首次回传走同一条链路（_toFileObject → 发送队列），区别只在于：
   * 这里不追加正文标记，避免把同一个 bridge-chat-res 重复发一遍给 AI。
   * 整文件按路径重新取字节，分段按已存的 dataURL 重新解码。
   * @param {Array} descs 文件描述数组 [{ name, mime, source, path, content }]
   */
  M.repasteFiles = function (descs) {
    const list = Array.isArray(descs) ? descs : [];
    if (!list.length) { this.toast('没有可重新粘贴的文件'); return; }
    this.toast('正在重新粘贴 ' + list.length + ' 个文件…');
    // 复用同一套转换与入队逻辑；正文传空串，只贴文件不重复发标记
    this._enqueueFiles(list, '');
  };

  M._enqueueFiles = function (files, mark) {
    const self = this;
    Promise.all(files.map(function (f) { return self._toFileObject(f); }))
      .then(function (objs) {
        const ok = objs.filter(function (o) { return o instanceof File; });
        if (!ok.length) {
          self.toast('读取文件失败，未回传');
          return;
        }
        // 多个文件放进同一条消息：内容脚本会逐个粘贴后统一回车
        D.enqueueSend({ type: 'auto_send_file', files: ok, text: mark });
      });
  };
})();
