// 模块：extend/dialog/parts/01h_bridge_wecom.js
// 用途：企业微信通道的前端逻辑（配置加载、保存、状态轮询）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 与微信逻辑（01f_bridge_weixin.js）并列但独立：
// 企业微信没有扫码流程，凭证是手工填的，逻辑简单得多。
(function () {
  'use strict';
  const D = window.AIMirrorDialog = window.AIMirrorDialog || {};
  const M = D.methods = D.methods || {};

  /**
   * 加载企业微信通道配置与状态。
   *
   * 一次取齐：通道状态、BotID、是否已填密钥、当前会话。
   * 失败时保持默认值，由状态轮询兜底重试。
   */
  M.loadWecom = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/wecom/status', {
        headers: { 'Accept': 'application/json' }
      });
      this._applyWecomStatus(data);
      this._wecomLoaded = true;
    } catch (e) {
      this._wecomLoaded = false;
      log('企业微信状态加载失败（将由轮询重试）：' + e);
    }
  };

  /**
   * 把后端返回的状态写进 Vue 实例。
   *
   * 抽出成独立方法：加载与轮询都会返回同一份结构，统一在此落地。
   * @param {Object} data 后端返回体
   */
  M._applyWecomStatus = function (data) {
    const ch = (data && data.channel) || {};
    this.wecomEnabled = !!ch.enabled;
    this.wecomConnected = !!ch.connected;
    this.wecomHasSecret = !!(data && data.hasSecret);
    this.wecomBotId = (data && data.botId) || '';
    // 密钥明文回填：设置页需要能直接看到并修改它。
    // 后端始终回传该字段，故这里无条件覆盖，避免残留上一次的值。
    this.wecomSecret = (data && data.secret) || '';
    this.wecomChatId = (data && data.chatid) || '';
  };

  /**
   * 保存企业微信通道配置。
   *
   * 密钥留空表示不修改：用户可能只想改开关。
   * 保存后后端会重建长连接，故再拉一次状态（回填的密钥随之刷新）。
   */
  M.saveWecomConfig = async function () {
    try {
      const body = {
        enabled: this.wecomEnabled,
        bot_id: this.wecomBotId,
      };
      // 只有用户真的输入了新密钥才提交，避免用空值覆盖已存密钥
      if (this.wecomSecret) body.secret = this.wecomSecret;
      const data = await D.apiFetch(this, '/api/bridge/wecom/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (data && data.success) {
        // 不再清空输入框：密钥以明文常驻显示，用户随时可查看与修改。
        // _applyWecomStatus 会用后端回传的最新值刷新它。
        this._applyWecomStatus(data);
        this.toast(this.wecomEnabled ? '企业微信通道已保存并重启' : '企业微信通道已关闭');
      } else {
        this.toast('保存失败：' + ((data && data.error) || '未知错误'));
      }
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

  /**
   * 启动企业微信状态轮询（幂等）。
   *
   * 长连接建立需要几秒，轮询让状态灯能反映真实变化。
   * 间隔 10 秒：状态变化不频繁，无需更高频率。
   */
  M.startWecomStatusPoll = function () {
    if (this._wecomPollTimer) return;
    const tick = async () => {
      try {
        const data = await D.apiFetch(this, '/api/bridge/wecom/status', {
          headers: { 'Accept': 'application/json' }
        });
        this._applyWecomStatus(data);
        this._wecomLoaded = true;
      } catch (e) {
        this.wecomConnected = false;
      }
      this._wecomPollTimer = setTimeout(tick, 10000);
    };
    this._wecomPollTimer = setTimeout(tick, 0);
  };

  /**
   * 停止企业微信状态轮询。
   */
  M.stopWecomStatusPoll = function () {
    if (this._wecomPollTimer) {
      clearTimeout(this._wecomPollTimer);
      this._wecomPollTimer = null;
    }
  };
})();
