// 模块：extend/dialog/parts/01f_bridge_weixin.js
// 用途：微信通道的全部前端逻辑（配置加载、扫码登录、状态轮询）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 与 QQ 逻辑（01b_bridge.js）并列但独立：微信没有 AppID/AppSecret，
// 登录靠扫码，状态靠轮询，故单独成文件。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const M = D.methods;

  /**
   * 加载微信通道配置与状态。
   *
   * 一次取齐三样：通道状态（是否连接、是否已登录）、登录进度、配额余量。
   * 失败时保持默认值，由状态轮询兜底重试。
   */
  M.loadWeixin = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/weixin/status', {
        headers: { 'Accept': 'application/json' }
      });
      this._applyWeixinStatus(data);
      this._wxLoaded = true;
    } catch (e) {
      // 后端不可达：标记未加载，交由轮询重试，避免开关永久停在默认值
      this._wxLoaded = false;
      log('微信通道状态加载失败（将由轮询重试）：' + e);
    }
  };

  /**
   * 把后端返回的状态写进 Vue 实例。
   *
   * 抽出成独立方法：轮询与各操作接口都会返回同一份结构，统一在此落地，
   * 避免每处各写一遍字段赋值、漏掉新字段。
   * @param {Object} data 后端返回体
   */
  M._applyWeixinStatus = function (data) {
    const ch = (data && data.channel) || {};
    this.wxEnabled = !!ch.enabled;
    this.wxConnected = !!ch.connected;
    this.wxHasCred = !!ch.hasCred;
    this.wxBotId = ch.botId || '';
    this.wxLogin = (data && data.login) || null;
    this.wxQuota = (data && data.quota) || { used: 0, limit: 10, remaining: 10 };
  };

  /**
   * 保存微信通道开关。
   *
   * 开关变化需要后端重启长轮询，故保存后重新拉一次状态。
   */
  M.saveWxConfig = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/weixin/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: this.wxEnabled })
      });
      this._applyWeixinStatus(data);
      this.toast(this.wxEnabled ? '微信通道已开启' : '微信通道已关闭');
    } catch (e) {
      this.toast('保存失败：' + e);
    }
  };

  /**
   * 发起扫码登录。
   *
   * 接口立即返回二维码，不等用户扫完；随后靠轮询推进状态。
   */
  M.wxStartLogin = async function () {
    this.wxVerifyCode = '';
    try {
      const data = await D.apiFetch(this, '/api/bridge/weixin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (!data || !data.success) {
        this.toast('获取二维码失败：' + ((data && data.error) || '未知错误'));
        return;
      }
      this._applyWeixinStatus(data);
      // 拿到二维码后启动轮询：扫码是异步的，必须持续查状态
      this.startWxStatusPoll();
    } catch (e) {
      this.toast('获取二维码失败：' + e);
    }
  };

  /**
   * 提交手机微信上显示的验证码。
   */
  M.wxSubmitVerify = async function () {
    const code = String(this.wxVerifyCode || '').trim();
    if (!code) {
      this.toast('请先输入手机上的数字');
      return;
    }
    try {
      const data = await D.apiFetch(this, '/api/bridge/weixin/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
      });
      if (!data || !data.success) {
        this.toast('提交失败：' + ((data && data.error) || '未知错误'));
        return;
      }
      this.wxVerifyCode = '';
      this._applyWeixinStatus(data);
      this.toast('验证码已提交');
    } catch (e) {
      this.toast('提交失败：' + e);
    }
  };

  /**
   * 退出微信登录：清除本机凭证。
   */
  M.wxLogout = async function () {
    try {
      const data = await D.apiFetch(this, '/api/bridge/weixin/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      this._applyWeixinStatus(data);
      this.toast('已退出微信登录');
    } catch (e) {
      this.toast('退出失败：' + e);
    }
  };

  /**
   * 启动微信状态轮询（幂等）。
   *
   * 扫码期间每 2 秒查一次，登录成功后降为 10 秒的常规心跳。
   * 用一个定时器统一处理，避免扫码与常规各起一个、互相干扰。
   */
  M.startWxStatusPoll = function () {
    if (this._wxPollTimer) return;
    const tick = async () => {
      try {
        const data = await D.apiFetch(this, '/api/bridge/weixin/status', {
          headers: { 'Accept': 'application/json' }
        });
        this._applyWeixinStatus(data);
        this._wxLoaded = true;
      } catch (e) {
        this.wxConnected = false;
      }
      // 动态调整间隔：扫码中（waiting/scanned/need_verify）用 2 秒，
      // 其余状态用 10 秒，减少无谓请求。
      const st = (this.wxLogin || {}).state || 'idle';
      const fast = (st === 'waiting' || st === 'scanned' || st === 'need_verify');
      const next = fast ? 2000 : 10000;
      this._wxPollTimer = setTimeout(tick, next);
    };
    this._wxPollTimer = setTimeout(tick, 0);
  };

  /**
   * 停止微信状态轮询。
   */
  M.stopWxStatusPoll = function () {
    if (this._wxPollTimer) {
      clearTimeout(this._wxPollTimer);
      this._wxPollTimer = null;
    }
  };
})();
