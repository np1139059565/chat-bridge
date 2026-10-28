// 模块：extend/dialog/parts/08d_bridge_weixin.js
// 用途：设置面板「微信通道」区块（微信 ↔ 网页 AI）。
// 依赖：extend/dialog/parts/00_data.js（命名空间 D）、Vue 全局构建
//
// 与 QQ 区块并列但独立：微信走扫码登录，推送受配额约束，
// 故界面上单独成块，不与 QQ 凭证混在一起。
(function () {
  'use strict';
  const D = window.AIMirrorDialog;
  const h = Vue.h;

  /**
   * 渲染一行状态标签（如「已连接 / 未连接」）。
   * @param {boolean} ok 是否为正常态
   * @param {string} text 显示文字
   * @returns {VNode} 状态节点
   */
  function statusDot(ok, text) {
    return h('span', { class: 'bridge-status ' + (ok ? 'on' : 'off') }, text);
  }

  /**
   * 渲染扫码登录区域：按登录状态展示不同内容。
   *
   * 状态来源：ctx.wxLogin（后端 /api/bridge/weixin/status 返回的 login 字段）。
   * 各状态对应界面：
   *   idle/failed     —— 显示「扫码登录」按钮
   *   waiting         —— 显示二维码，提示用手机扫
   *   scanned         —— 提示已在手机上确认
   *   need_verify     —— 显示验证码输入框
   *   confirmed       —— 显示成功
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 登录区域
   */
  function renderLoginArea(ctx) {
    const lg = ctx.wxLogin || {};
    const state = lg.state || 'idle';
    const children = [];

    // 已登录：只展示凭证信息与退出按钮
    if (ctx.wxHasCred && state !== 'waiting' && state !== 'need_verify') {
      children.push(h('div', { class: 'hint' }, '已扫码登录，微信通道可使用。'));
      children.push(h('div', [
        h('button', { onClick: () => ctx.wxLogout() }, '退出登录'),
        h('span', { class: 'hint' }, '退出后需重新扫码')
      ]));
      return h('div', children);
    }

    // 未登录：按状态展示
    if (state === 'waiting' || state === 'scanned') {
      children.push(renderQr(ctx, lg));
      children.push(h('div', { class: 'hint' }, lg.message || '请用手机微信扫描二维码'));
      return h('div', children);
    }

    if (state === 'need_verify') {
      children.push(h('div', { class: 'hint' }, '请输入手机微信上显示的数字：'));
      children.push(h('div', [
        h('input', {
          type: 'text',
          value: ctx.wxVerifyCode || '',
          placeholder: '手机上的数字',
          onInput: (e) => { ctx.wxVerifyCode = e.target.value; }
        }),
        h('button', { onClick: () => ctx.wxSubmitVerify() }, '提交')
      ]));
      return h('div', children);
    }

    // 空闲或失败
    if (state === 'failed') {
      children.push(h('div', { class: 'hint' }, lg.message || '登录失败'));
    }
    children.push(h('button', { onClick: () => ctx.wxStartLogin() }, '扫码登录微信'));
    children.push(h('span', { class: 'hint' }, '点击后显示二维码，用手机微信扫描即可'));
    return h('div', children);
  }

  /**
   * 渲染二维码图片。
   *
   * 后端返回的是一段 URL（微信的二维码内容），用第三方图表服务转成图片，
   * 避免在前端引入二维码生成库。同时给出可点击的原始链接作为兜底。
   * @param {Object} ctx Vue 实例
   * @param {Object} lg 登录状态
   * @returns {VNode} 二维码区域
   */
  function renderQr(ctx, lg) {
    const url = lg.qrcode_url || '';
    if (!url) return h('div', { class: 'hint' }, '二维码加载中…');
    return h('div', [
      h('img', {
        src: 'https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=' + encodeURIComponent(url),
        style: 'width:180px;height:180px;display:block;margin:8px 0;background:#fff;padding:6px;'
      }),
      h('a', { href: url, target: '_blank', class: 'hint' }, '二维码无法显示？点此打开链接')
    ]);
  }

  /**
   * 渲染配额提示行。
   *
   * 微信限制 24 小时内最多 10 条消息，配额用尽后消息发不出去。
   * 把剩余条数摆出来，用户能提前知道「为什么对方收不到」。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 配额行
   */
  function renderQuota(ctx) {
    const q = ctx.wxQuota || {};
    const remaining = q.remaining === undefined ? 10 : q.remaining;
    const used = q.used || 0;
    const limit = q.limit || 10;
    const warn = remaining <= 2;
    return h('div', { class: 'bridge-push-row' }, [
      h('span', { class: 'bridge-push-label' }, '今日剩余条数'),
      h('span', { style: warn ? 'color:#e57373;font-weight:600;' : '' },
        String(remaining) + ' / ' + String(limit) + '（已用 ' + String(used) + '）')
    ]);
  }

  /**
   * 微信通道区块。
   * @param {Object} ctx Vue 实例
   * @returns {VNode} 区块节点
   */
  D.renderWeixinBlock = function (ctx) {
    return h('div', { class: 'sp-block' }, [
      h('div', { class: 'card-head' }, [
        h('span', { title: '在微信里与网页 AI 对话：扫码即用，无需公网地址' }, '远程桥接（微信）'),
        h('button', { onClick: () => { ctx.wxOpen = !ctx.wxOpen; } },
          ctx.wxOpen ? '▾' : '▸')
      ]),
      ctx.wxOpen ? h('div', { class: 'bridge-body' }, [
        // 连接状态 + 总开关
        h('div', { class: 'bridge-row' }, [
          h('label', { class: 'bridge-toggle' }, [
            h('input', {
              type: 'checkbox',
              checked: ctx.wxEnabled,
              onChange: (e) => { ctx.wxEnabled = e.target.checked; ctx.saveWxConfig(); }
            }),
            '启用微信通道'
          ]),
          statusDot(!!ctx.wxConnected, ctx.wxConnected ? '● 已连接' : '○ 未连接')
        ]),
        h('div', { class: 'hint' },
          '微信通道走扫码登录，无需填 AppID。开启后需扫码一次，凭证保存在本机。'),
        // 登录区域
        h('div', { class: 'card-head' }, [h('span', '扫码登录')]),
        renderLoginArea(ctx),
        h('br'),
        // 配额提示
        h('div', { class: 'card-head' }, [h('span', '发送配额')]),
        renderQuota(ctx),
        h('div', { class: 'hint' },
          '微信规定：24 小时内最多 10 条消息，且不支持主动推送。' +
          '因此本通道会把同一轮的多条消息合并成一条发出，尽量节省配额。'),
      ]) : null
    ]);
  };
})();
