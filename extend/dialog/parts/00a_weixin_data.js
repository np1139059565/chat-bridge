// 模块：extend/dialog/parts/00a_weixin_data.js
// 用途：微信通道的前端初始状态字段，独立成文件以控制 00_data.js 的行数。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D 必须先建立）
//
// 为什么单列：微信通道有登录进度、配额、轮询定时器等一组状态，
// 与 QQ 的状态彼此独立。集中在此，新增字段时只改这一处，
// 也避免主数据文件因持续叠加而超出长度上限。
(function () {
  'use strict';
  // 兜底创建命名空间：本文件必须能独立于 00_data.js 工作。
  // 若直接取 window.AIMirrorDialog 而不创建，一旦加载顺序变化
  // （本文件排在 00_data.js 之前）就会拿到 undefined，
  // 随后给 undefined 挂属性会抛 TypeError，导致整个抽屉脚本链中断。
  const D = window.AIMirrorDialog = window.AIMirrorDialog || {};

  /**
   * 微信通道的初始状态。
   *
   * 由 00_data.js 在构造 data 时展开合并（见其 wxInitialState 引用）。
   * 各字段含义：
   *   wxOpen        —— 设置页区块是否展开
   *   wxEnabled     —— 通道总开关；默认关，需扫码登录拿到凭证后才启用
   *   wxConnected   —— 长轮询是否真正在跑
   *   wxHasCred     —— 本机是否已有登录凭证
   *   wxBotId       —— 登录后的机器人标识，便于排查连的是哪个号
   *   wxLogin       —— 登录进度 {state, qrcode_url, message, need_verify}
   *   wxVerifyCode  —— 用户输入的数字验证码
   *   wxQuota       —— 发送配额余量 {used, limit, remaining}
   *   _wxPollTimer  —— 状态轮询定时器句柄
   *   _wxLoaded     —— 配置是否已成功加载过（失败时由轮询重试）
   * @returns {Object} 初始状态字典
   */
  D.weixinInitialState = function () {
    return {
      wxOpen: false,
      wxEnabled: false,
      wxConnected: false,
      wxHasCred: false,
      wxBotId: '',
      wxLogin: null,
      wxVerifyCode: '',
      wxQuota: { used: 0, limit: 10, remaining: 10 },
      _wxPollTimer: null,
      _wxLoaded: false
    };
  };
})();
