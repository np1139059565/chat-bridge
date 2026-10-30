// 模块：extend/dialog/parts/00b_wecom_data.js
// 用途：企业微信通道的前端初始状态字段，独立成文件以控制 00_data.js 的行数。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）
//
// 为什么单列：与 00a_weixin_data.js 同理，避免主数据文件因持续叠加超长。
(function () {
  'use strict';
  // 兜底创建命名空间：本文件排在 00_data.js 之后加载，但为保证健壮性，
  // 仍做一次防御性检查（与微信数据文件保持一致的做法）。
  const D = window.AIMirrorDialog = window.AIMirrorDialog || {};

  /**
   * 企业微信通道的初始状态。
   *
   * 由 00_data.js 在构造 data 时展开合并。
   * 各字段含义：
   *   wecomOpen       —— 设置页区块是否展开
   *   wecomEnabled    —— 通道总开关；默认关，需填凭证后再启用
   *   wecomConnected  —— 长连接是否已订阅成功
   *   wecomHasSecret  —— 是否已保存密钥（页面不回显明文）
   *   wecomBotId      —— 机器人 ID
   *   wecomSecret     —— 用户新输入的密钥；提交后清空
   *   wecomChatId     —— 当前活跃会话，主动推送依赖它
   *   _wecomPollTimer —— 状态轮询定时器句柄
   *   _wecomLoaded    —— 配置是否已成功加载过
   * @returns {Object} 初始状态字典
   */
  D.wecomInitialState = function () {
    return {
      wecomOpen: false,
      wecomEnabled: false,
      wecomConnected: false,
      wecomHasSecret: false,
      wecomBotId: '',
      wecomSecret: '',
      wecomChatId: '',
      _wecomPollTimer: null,
      _wecomLoaded: false
    };
  };
})();
