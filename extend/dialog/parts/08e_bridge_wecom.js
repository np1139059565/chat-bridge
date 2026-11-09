// 模块：extend/dialog/parts/08e_bridge_wecom.js
// 用途：设置面板「企业微信通道」区块（企业微信 ↔ 网页 AI）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
//
// 与 QQ、微信两个区块并列但独立：企业微信走 WebSocket 长连接，
// 凭证是手工填的 BotID / Secret（不是扫码），支持主动推送与图片/文件。
(function () {
  'use strict';
  const D = window.AIMirrorDialog = window.AIMirrorDialog || {};
  const h = Vue.h;

  /**
   * 渲染连接状态标签。
   * @param {boolean} ok 是否正常
   * @param {string} text 显示文字
   * @returns {VNode} 状态节点
   */
  function statusDot(ok, text) {
    return h('span', { class: 'bridge-status ' + (ok ? 'on' : 'off') }, text);
  }

  /**
   * 企业微信通道区块。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderWecomBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', {
          title: '在企业微信里与网页 AI 对话：支持主动推送、图片与文件'
        }, '远程桥接（企业微信）'),
        h('button', { onClick: () => { ctx.wecomOpen = !ctx.wecomOpen; } },
          ctx.wecomOpen ? '▾' : '▸')
      ]),
      ctx.wecomOpen ? h('div', { class: 'bridge-body' }, [
        // 总开关 + 连接状态
        h('div', { class: 'bridge-row' }, [
          h('label', { class: 'bridge-toggle' }, [
            h('input', {
              type: 'checkbox',
              checked: ctx.wecomEnabled,
              onChange: (e) => { ctx.wecomEnabled = e.target.checked; ctx.saveWecomConfig(); }
            }),
            '启用企业微信通道'
          ]),
          statusDot(!!ctx.wecomConnected, ctx.wecomConnected ? '● 已连接' : '○ 未连接')
        ]),
        h('div', { class: 'hint' },
          '企业微信走长连接，无需公网地址。填好 BotID 与 Secret 后启用即可。'),
        // 凭证
        h('label', ['机器人 BotID', h('input', {
          type: 'text',
          value: ctx.wecomBotId,
        'data-diff': D.blockFieldClass ? D.blockFieldClass(ctx, 'wecom', 'bot_id', ctx.wecomBotId) : '',
          placeholder: '如 aibxxxxxxxxxxxx',
          onInput: (e) => { ctx.wecomBotId = e.target.value; D.markBlockField(ctx, 'wecom', 'bot_id', ctx.wecomBotId); }
        })]),
        h('label', ['机器人 Secret', h('input', {
          type: 'text',
          value: ctx.wecomSecret,
        'data-diff': D.blockFieldClass ? D.blockFieldClass(ctx, 'wecom', 'secret', ctx.wecomSecret) : '',
          // 明文显示：与 QQ 通道一致，用户可随时查看与修改已存密钥
          placeholder: '如 XPfC7Gxxxxxxxxxxxx',
          onInput: (e) => { ctx.wecomSecret = e.target.value; D.markBlockField(ctx, 'wecom', 'secret', ctx.wecomSecret); }
        })]),
        h('div', [
          h('button', { onClick: () => ctx.saveWecomConfig() }, '保存并重启通道'),
          h('span', { class: 'hint' }, '保存后自动重建长连接')
        ]),
        h('br'),
        // 能力说明：这是选企业微信的核心理由，直接摆在界面上
        h('div', { class: 'card-head' }, [h('span', '通道能力')]),
        h('div', { class: 'hint' },
          '✓ 主动推送（无需用户先发消息）　✓ 图片　✓ 文件　✓ 群聊'),
        h('div', { class: 'hint' },
          '当前会话：' + (ctx.wecomChatId || '（尚无，需用户先发一条消息）'))
      ]) : null
    ]);
  };
})();

// ctx.wecomBotId_TRACKED

// ctx.wecomSecret_TRACKED
