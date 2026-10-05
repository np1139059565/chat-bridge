// 模块：extend/dialog/parts/05h_memory_bridge.js
// 用途：抽屉与后端记忆系统的桥接——消息树持久化由「浏览器本地存储」
//       改为「全部走后端查询」，后端是唯一权威。含一次性迁移补丁。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D、D.apiFetch）
//
// 迁移补丁说明（临时代码）：
//   改造前消息树存在 chrome.storage.local；改造后只存后端。
//   为不丢历史，切换会话时若后端无该会话，则从本地读一次并推送后端。
//   全部会话迁移完成、确认无误后，本补丁应删除。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const log = D.log;
  const M = D.methods;

  /** 本地存储 key（与改造前一致，供迁移读取）。 */
  M._localConvKey = function (convId) {
    return 'aiMirrorConv_' + (this.siteKey || '') + '__' + (convId || '__default__');
  };

  /**
   * 存一个会话到后端。失败不静默：提示用户并返回 false。
   * @param {string} convId 会话 id
   * @param {Object} conv 会话对象
   * @returns {Promise<boolean>} 是否写入成功
   */
  M.memSaveConv = async function (convId, conv) {
    try {
      await D.apiFetch(this, '/memory/conversation', {
        method: 'POST',
        body: { conv_id: convId, site_key: this.siteKey || '', conv: conv },
      });
      return true;
    } catch (e) {
      log('memSaveConv 失败：' + e);
      if (this.toast) this.toast('记忆写入失败，请检查后端连接');
      return false;
    }
  };

  /**
   * 从后端取一个会话；后端无此会话时返回 null。
   * @param {string} convId 会话 id
   * @returns {Promise<Object|null>} 会话对象
   */
  M.memLoadConv = async function (convId) {
    try {
      const url = '/memory/conversation?conv_id=' + encodeURIComponent(convId)
        + '&site_key=' + encodeURIComponent(this.siteKey || '');
      const r = await D.apiFetch(this, url, { headers: { 'Accept': 'application/json' } });
      return (r && r.conv) ? r.conv : null;
    } catch (e) {
      log('memLoadConv 失败：' + e);
      return null;
    }
  };

  /**
   * 从后端取会话摘要列表。
   * @returns {Promise<Array>} 会话摘要数组
   */
  M.memListConvs = async function () {
    try {
      const url = '/memory/conversations?site_key=' + encodeURIComponent(this.siteKey || '');
      const r = await D.apiFetch(this, url, { headers: { 'Accept': 'application/json' } });
      return (r && r.conversations) || [];
    } catch (e) {
      log('memListConvs 失败：' + e);
      return [];
    }
  };

  /**
   * 迁移补丁：后端无此会话时，从浏览器本地存储迁移一次并推送后端。
   * 这是过渡用临时代码，全部迁移完成后应删除。
   * @param {string} convId 会话 id
   * @returns {Promise<Object|null>} 迁移成功返回会话对象，本地也没有则 null
   */
  M.memMigrateConv = function (convId) {
    const self = this;
    return new Promise(function (resolve) {
      const key = self._localConvKey(convId);
      chrome.storage.local.get(key, function (res) {
        const saved = res && res[key];
        if (!saved) { resolve(null); return; }
        // 本地有：推送到后端（迁移），并返回该数据供本次使用
        const conv = {
          title: saved.title || '', page_url: saved.page_url || '',
          msgTree: saved.msgTree || {}, visibleKeys: saved.visibleKeys || [],
          branchKeys: saved.branchKeys || [], externalCards: saved.externalCards || [],
          orphanSlice: saved.orphanSlice || [],
        };
        self.memSaveConv(convId, conv).then(function (ok) {
          log('迁移会话 ' + convId + ' 到后端：' + (ok ? '成功' : '失败'));
          resolve(conv);
        });
      });
    });
  };

  /**
   * 取会话（后端优先）：后端有则用后端，没有则尝试迁移，再没有返回空。
   * @param {string} convId 会话 id
   * @returns {Promise<Object|null>} 会话对象或 null
   */
  M.memFetchConv = async function (convId) {
    const fromBackend = await this.memLoadConv(convId);
    if (fromBackend) return fromBackend;
    // 后端没有：尝试迁移补丁
    return await this.memMigrateConv(convId);
  };
})();
